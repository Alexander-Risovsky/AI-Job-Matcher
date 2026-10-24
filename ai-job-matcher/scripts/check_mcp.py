"""Diagnostics for live MCP handshake. Never print fetched page content or credentials."""
import asyncio
import sys
import traceback
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    params = StdioServerParameters(command=sys.executable, args=["-m", "mcp_server_fetch"])
    try:
        async with asyncio.timeout(30):
            async with stdio_client(params) as (rd, wr):
                async with ClientSession(rd, wr) as session:
                    response = await session.initialize()
                    print("MCP handshake:", response.server_info.name, response.server_info.version)
                    methods = await session.list_tools()
                    print("MCP tools:", [t.name for t in methods.tools])
                    result = await session.call_tool("fetch", {"url": "https://example.com/"})
                    print("MCP tool success:", not result.is_error)
                    print("MCP content lengths:", [len(getattr(part, "text", "")) for part in result.content])
    except Exception:
        traceback.print_exc(limit=12)


if __name__ == "__main__":
    asyncio.run(main())
