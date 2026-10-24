"""Existing stdio MCP fetch server, guarded against untrusted Telegram URLs."""
import asyncio
import ipaddress
import logging
import socket
import time
from urllib.parse import urlsplit
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

log = logging.getLogger(__name__)


def validate_public_url(url: str, allowed_domains: str = "") -> str:
    parsed = urlsplit(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Unsupported external URL")
    hostname = parsed.hostname.lower().rstrip(".")
    if hostname in {"localhost", "localhost.localdomain"} or hostname.endswith((".local", ".internal")):
        raise ValueError("Private host forbidden")
    domains = [x.strip().lower() for x in allowed_domains.split(",") if x.strip()]
    if not domains or not any(hostname == d or hostname.endswith("." + d) for d in domains):
        raise ValueError("Host not in configured MCP_FETCH_ALLOWED_DOMAINS")
    for info in socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM):
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global:
            raise ValueError("Resolved address is non-public")
    return url


class MCPFetcher:
    def __init__(self, settings):
        self.settings = settings

    async def fetch(self, url: str) -> tuple[str, dict]:
        start = time.monotonic()
        log_data = {"tool": "fetch", "url": url, "status": "failure"}
        try:
            validate_public_url(url, self.settings.mcp_fetch_allowed_domains)
            args = StdioServerParameters(command=self.settings.mcp_fetch_command, args=self.settings.mcp_fetch_args)
            async with asyncio.timeout(self.settings.mcp_fetch_timeout):
                async with stdio_client(args) as (read, write):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        tools = await session.list_tools()
                        if not any(tool.name == "fetch" for tool in tools.tools):
                            raise RuntimeError("MCP tool fetch missing")
                        result = await session.call_tool("fetch", {"url": url})
                        if result.is_error:
                            raise RuntimeError("MCP fetch reported error")
                        text = "\n".join(
                            getattr(part, "text", "") for part in result.content if getattr(part, "type", "") == "text"
                        )[:self.settings.mcp_fetch_max_chars]
                        if not text:
                            raise RuntimeError("MCP fetch returned empty text")
                        log_data["status"] = "success"
                        return text, log_data
        except Exception as exc:
            log_data["error"] = f"{type(exc).__name__}: {str(exc)[:250]}"
            log.warning("MCP fetch failed: %s", log_data["error"])
            return "", log_data
        finally:
            log_data["duration_ms"] = round((time.monotonic() - start) * 1000)
            log.info("MCP tool call: %s", log_data)
