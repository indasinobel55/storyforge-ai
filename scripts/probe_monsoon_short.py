from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent.providers.taaft import TaaftProvider

SHORT_PROMPT = (
    "Create an 8-second cinematic shot of a small motorized expedition boat carrying several "
    "human researchers along a wide winding river through an enormous Amazon rainforest, seen "
    "from above. Dense emerald-green canopy, morning mist, shafts of sunlight, realistic water "
    "reflections and wake. Cinematic realistic 3D animation, high-end theatrical quality. "
    "Camera: smooth FPV flight descending into a wide crane reveal behind the boat. "
    "No text, no subtitles, no logos, no watermarks."
)


async def main() -> None:
    provider = TaaftProvider(
        enabled=True,
        profile_dir=Path(".taaft_chrome_profile"),
        headless=False,
        poll_seconds=20,
        job_timeout_seconds=3600,
        tier="quality",
        orientation="landscape",
    )
    print(f"short prompt length: {len(SHORT_PROMPT)} chars", flush=True)
    result = await provider.submit_generation(
        prompt=SHORT_PROMPT,
        tier="quality",
        orientation="landscape",
        duration=8.0,
        idempotency_key="monsoon-probe-short",
    )
    print(f"ACCEPTED: job {result.generation_id} ({result.status})", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
