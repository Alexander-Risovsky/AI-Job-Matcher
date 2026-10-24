"""Launch the production API and Telegram reader directly in the current Python venv.

No containers are created or controlled by this script. The pre-existing
Qdrant server must be reachable at the URL configured in .env.

Usage:
    python -m scripts.start_local           # API + Telethon
    python -m scripts.start_local --api-only # API only
    python -m scripts.start_local --check    # connection checks, no side effects
"""
import argparse
import logging
import signal
import subprocess
import sys
import time
from pathlib import Path

import httpx
from app.config import get_settings


ROOT = Path(__file__).resolve().parents[1]


def check_connections(settings) -> bool:
    checks = (
        ("Ollama", f"{settings.ollama_base_url.rstrip('/')}/api/tags"),
        ("Qdrant", f"{settings.qdrant_url.rstrip('/')}/collections"),
    )
    good = True
    with httpx.Client(timeout=5, trust_env=False) as client:
        for label, url in checks:
            try:
                response = client.get(url)
                response.raise_for_status()
                print(f"[OK] {label}: HTTP {response.status_code}", flush=True)
            except (httpx.HTTPError, ValueError) as exc:
                print(f"[ERROR] {label}: {type(exc).__name__}: {exc}", flush=True)
                good = False
    return good


def ready(host: str, port: int, process: subprocess.Popen, seconds: float = 25.0) -> bool:
    url = f"http://{host}:{port}/health"
    end = time.monotonic() + seconds
    with httpx.Client(timeout=1.5, trust_env=False) as client:
        while time.monotonic() < end:
            if process.poll() is not None:
                return False
            try:
                if client.get(url).status_code == 200:
                    return True
            except httpx.HTTPError:
                pass
            time.sleep(0.3)
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Run AI Job Matcher locally without Compose")
    parser.add_argument("--api-only", action="store_true", help="Start API only; do not read Telegram")
    parser.add_argument("--check", action="store_true", help="Check Ollama and Qdrant URLs, then exit")
    args = parser.parse_args()

    settings = get_settings()
    if args.check:
        return 0 if check_connections(settings) else 1

    if not check_connections(settings):
        print("Start Ollama and Qdrant, then try again.", file=sys.stderr)
        return 1

    processes: list[subprocess.Popen] = []
    try:
        api_cmd = [
            sys.executable, "-m", "uvicorn", "app.main:app",
            "--host", settings.ingest_host, "--port", str(settings.ingest_port),
            "--workers", "1", "--log-level", "info",
        ]
        print("[START] FastAPI + LangGraph", flush=True)
        api = subprocess.Popen(api_cmd, cwd=ROOT)
        processes.append(api)

        if not ready(settings.ingest_host, settings.ingest_port, api):
            print("[ERROR] FastAPI did not become ready; inspect logs above.", file=sys.stderr)
            return 1
        print(f"[READY] http://{settings.ingest_host}:{settings.ingest_port}/docs", flush=True)

        if not args.api_only:
            if not settings.tg_api_id or not settings.tg_api_hash:
                print("[ERROR] Telegram API ID/hash are missing in .env", file=sys.stderr)
                return 1
            if not Path(settings.tg_session + ".session").is_file():
                print("[ERROR] Telegram session not found: " + settings.tg_session + ".session",
                      file=sys.stderr)
                return 1
            print("[START] Telethon reader; reading configured chats/topics.", flush=True)
            reader = subprocess.Popen([sys.executable, "-m", "app.telegram.reader"], cwd=ROOT)
            processes.append(reader)

        print("[RUNNING] Press Ctrl+C to stop.", flush=True)
        while True:
            for proc in processes:
                rc = proc.poll()
                if rc is not None:
                    print(f"[STOP] Component PID {proc.pid} exited with {rc}", file=sys.stderr)
                    return rc if rc != 0 else 1
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[STOP] Ctrl+C received.", flush=True)
        return 0
    finally:
        for proc in reversed(processes):
            if proc.poll() is None:
                proc.terminate()
        for proc in reversed(processes):
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()


if __name__ == "__main__":
    sys.exit(main())
