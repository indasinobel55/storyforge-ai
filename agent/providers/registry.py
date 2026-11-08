from __future__ import annotations

from pathlib import Path

from agent.core.errors import ProviderDisabledError
from agent.providers.base import VideoProvider
from agent.providers.simulated import SimulatedProvider
from agent.providers.taaft import FEASIBILITY_MESSAGE, TaaftProvider
from agent.providers.test_vision_adapter import TestVisionProvider


def provider_catalog(*, taaft_enabled: bool) -> list[dict]:
    return [
        {
            "provider": "simulated",
            "display_name": "Simulated Provider",
            "description": "Local deterministic provider that renders real MP4 test clips for development and tests.",
            "connectable": True,
            "requires_consent": False,
            "notes": "Clearly labeled simulation. Never presented as real TAAFT output.",
        },
        {
            "provider": "taaft",
            "display_name": "TAAFT (gated)",
            "description": "Per-user TAAFT video generator automation via Playwright.",
            "connectable": taaft_enabled,
            "requires_consent": True,
            "notes": None if taaft_enabled else FEASIBILITY_MESSAGE,
        },
    ]


def build_provider(
    name: str,
    *,
    cache_dir: Path,
    simulated_generation_seconds: float,
    simulated_clip_seconds: float,
    taaft_enabled: bool,
    taaft_storage_state: Path | None = None,
    taaft_chrome_path: str | None = None,
    taaft_headless: bool = True,
    taaft_poll_seconds: int = 20,
    taaft_job_timeout: int = 3600,
    test_vision_adapter: bool = False,
) -> VideoProvider:
    if name == "simulated":
        provider = SimulatedProvider(
            cache_dir=cache_dir,
            generation_seconds=simulated_generation_seconds,
            clip_seconds=simulated_clip_seconds,
        )
        if test_vision_adapter:
            provider = TestVisionProvider(
                cache_dir=cache_dir,
                generation_seconds=simulated_generation_seconds,
                clip_seconds=simulated_clip_seconds,
            )
        return provider
    if name == "taaft":
        if not taaft_enabled:
            raise ProviderDisabledError(FEASIBILITY_MESSAGE)
        return TaaftProvider(
            enabled=taaft_enabled,
            storage_state_path=taaft_storage_state,
            chrome_path=taaft_chrome_path,
            headless=taaft_headless,
            poll_seconds=taaft_poll_seconds,
            job_timeout_seconds=taaft_job_timeout,
        )
    raise ProviderDisabledError(f"Unknown provider: {name}")
