from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent.providers.taaft import TaaftProvider


async def main() -> None:
    provider = TaaftProvider(
        enabled=True,
        profile_dir=Path(".taaft_chrome_profile"),
        headless=False,
        poll_seconds=20,
        job_timeout_seconds=3600,
        tier="fast",
    )
    print("Opening TAAFT in Chrome (persistent profile)...")
    account = await provider.verify_account()
    print("account:", account)
    usage = await provider.get_usage()
    print("quota:", usage.credits_remaining, "/", usage.credits_total, "plan:", usage.plan)
    print("detail:", usage.detail)


if __name__ == "__main__":
    asyncio.run(main())
