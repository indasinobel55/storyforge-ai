from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from pathlib import Path

import requests

from .client import LocalApiClient, LocalApiError
from .pipeline import LocalConfig, LocalRunner

BANNER = (
    "Local execution mode: jobs run on THIS computer using the shared agent core.\n"
    "Keep this process and the machine powered on while videos are being generated.\n"
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m local_agent",
        description="Claim and execute AI video jobs from the studio backend on this machine.",
    )
    parser.add_argument("--api-url", default=os.environ.get("STUDIO_API_URL", "http://127.0.0.1:8000"))
    parser.add_argument(
        "--token",
        default=os.environ.get("LOCAL_EXECUTION_TOKEN"),
        help="Local execution token (prefer the LOCAL_EXECUTION_TOKEN env var)",
    )
    parser.add_argument("--work-dir", default=os.environ.get("LOCAL_WORK_DIR", "local_work"))
    parser.add_argument("--once", action="store_true", help="Claim and run at most one job")
    parser.add_argument("--drain", action="store_true", help="Run until no jobs remain, then exit")
    parser.add_argument("--interval", type=float, default=5.0, help="Idle poll interval in seconds")
    parser.add_argument("--timeout", type=int, default=60, help="HTTP timeout in seconds")
    return parser


def _verify_server_mode(client: LocalApiClient, api_url: str) -> bool:
    try:
        response = requests.get(f"{api_url.rstrip('/')}/api/execution/health", timeout=10)
        response.raise_for_status()
        mode = response.json().get("execution_mode")
    except Exception as error:  # noqa: BLE001
        print(f"Cannot reach backend at {api_url}: {error}")
        return False
    if mode != "local":
        print(
            f"Backend execution mode is '{mode}'. Start the backend with EXECUTION_MODE=local to use a local worker."
        )
        return False
    print(f"Backend execution mode: {mode}")
    return True


async def _run(args: argparse.Namespace) -> int:
    if not args.token:
        print("Missing token. Create one in the app (Settings -> Local execution) or set LOCAL_EXECUTION_TOKEN.")
        return 2
    client = LocalApiClient(args.api_url, args.token, timeout=args.timeout)
    if not _verify_server_mode(client, args.api_url):
        return 2

    config = LocalConfig(work_dir=Path(args.work_dir))
    runner = LocalRunner(client, config)

    if args.once:
        worked = await runner.run_once()
        if not worked:
            print("No queued jobs for this account.")
        return 0
    if args.drain:
        processed = await runner.run_until_idle()
        print(f"Processed {processed} job(s).")
        return 0

    print(BANNER)
    try:
        while True:
            worked = await runner.run_once()
            if not worked:
                time.sleep(max(1.0, args.interval))
    except KeyboardInterrupt:
        print("Local worker stopped.")
        return 0
    except LocalApiError as error:
        print(f"Local worker stopped after API error: {error}")
        return 1


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        return asyncio.run(_run(args))
    except LocalApiError as error:
        print(f"Local worker failed: {error}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
