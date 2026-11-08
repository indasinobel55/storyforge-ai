from __future__ import annotations

import random
from pathlib import Path

from agent.core.errors import VisionModelError
from agent.providers.base import _ImageAnalysis, VideoProvider
from agent.providers.simulated import SimulatedProvider


class TestVisionProvider(SimulatedProvider):
    """Deterministic vision test double used only by automated verification.

    Subclasses SimulatedProvider so that submit_generation, get_generation_status,
    extend_generation and download_generation behave exactly like the simulated
    provider (rendering real MP4 clips). Only analyze_image is overridden with
    the deterministic test analysis.
    """

    name = "test_vision"
    display_name = "Test Vision Adapter"
    requires_consent = False

    def __init__(
        self,
        *,
        fail_rate: float = 0.0,
        blocked: bool = False,
        cache_dir: Path | None = None,
        generation_seconds: float = 1.5,
        clip_seconds: float = 2.0,
    ) -> None:
        if cache_dir is None:
            cache_dir = Path(".test_vision_cache")
        cache_dir = cache_dir.resolve()
        cache_dir.mkdir(parents=True, exist_ok=True)
        super().__init__(cache_dir=cache_dir, generation_seconds=generation_seconds, clip_seconds=clip_seconds)
        self._fail_rate = float(fail_rate)
        self._blocked = bool(blocked)

    async def verify_account(self) -> dict:
        return {"provider": self.name, "status": "connected", "simulated": True}

    async def get_usage(self) -> dict:
        return {"provider": self.name, "simulated": True, "plan": "test"}

    async def submit_generation(
        self,
        *,
        prompt: str,
        tier: str,
        orientation: str,
        duration: float,
        reference_image_path: Path | None = None,
        idempotency_key: str | None = None,
    ):
        # Delegates to SimulatedProvider.submit_generation (same signature)
        return await super().submit_generation(
            prompt=prompt,
            tier=tier,
            orientation=orientation,
            duration=duration,
            reference_image_path=reference_image_path,
            idempotency_key=idempotency_key,
        )

    async def get_generation_status(self, generation_id: str):
        # Delegates to SimulatedProvider.get_generation_status
        return await super().get_generation_status(generation_id=generation_id)

    async def extend_generation(
        self,
        *,
        parent_generation_id: str,
        prompt: str,
        tier: str,
        orientation: str,
        duration: float,
        reference_image_path: Path | None = None,
    ):
        # Delegates to SimulatedProvider.extend_generation
        return await super().extend_generation(
            parent_generation_id=parent_generation_id,
            prompt=prompt,
            tier=tier,
            orientation=orientation,
            duration=duration,
            reference_image_path=reference_image_path,
        )

    async def download_generation(self, generation, destination: Path) -> Path:
        # Delegates to SimulatedProvider.download_generation
        return await super().download_generation(generation=generation, destination=destination)

    async def cancel_generation(self, generation_id: str) -> bool:
        return False

    async def find_generation_by_idempotency(self, idempotency_key: str):
        return None

    async def analyze_image(
        self,
        *,
        image_path: Path,
        project_title: str,
        reference_description: str,
    ) -> _ImageAnalysis:
        if self._blocked:
            return _ImageAnalysis(
                description="",
                blocked=True,
                error="Vision adapter is not available in this environment",
            )
        if self._fail_rate > 0:
            import random

            if random.random() < self._fail_rate:
                raise VisionModelError("Simulated vision adapter failure")
        description = (
            f"The previous frame of \"{project_title}\" shows the established scene. "
            f"Review of the reference description: {reference_description}. "
            f"The shot continues the same world, lighting, and characters."
        )
        return _ImageAnalysis(description=description, blocked=False)
