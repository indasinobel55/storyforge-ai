from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class GenerationResult:
    generation_id: str
    status: str
    video_url: str | None = None
    mode: str | None = None
    parent_generation_id: str | None = None
    segment_index: int | None = None
    error: str | None = None
    raw: dict = field(default_factory=dict)

    @property
    def terminal(self) -> bool:
        return self.status.lower() in {
            "succeeded",
            "success",
            "completed",
            "failed",
            "error",
            "canceled",
            "cancelled",
        }

    @property
    def failed(self) -> bool:
        return self.status.lower() in {"failed", "error", "canceled", "cancelled"}


class _ImageAnalysis:
    """Structured result from a vision model or vision adapter."""

    def __init__(
        self,
        *,
        description: str,
        blocked: bool = False,
        error: str | None = None,
    ) -> None:
        self.description = description
        self.blocked = blocked
        self.error = error


@dataclass
class UsageInfo:
    credits_remaining: int | None = None
    credits_total: int | None = None
    plan: str | None = None
    detail: dict = field(default_factory=dict)


class VideoProvider(ABC):
    """Provider contract.

    Implementations must be safe to call after a worker restart: generation
    identifiers are persisted by the caller and can be polled again later.
    """

    name: str = "base"
    display_name: str = "Base Provider"
    requires_consent: bool = False

    @abstractmethod
    async def verify_account(self) -> dict: ...

    @abstractmethod
    async def get_usage(self) -> UsageInfo: ...

    @abstractmethod
    async def submit_generation(
        self,
        *,
        prompt: str,
        tier: str,
        orientation: str,
        duration: float,
        reference_image_path: Path | None = None,
        idempotency_key: str | None = None,
    ) -> GenerationResult: ...

    @abstractmethod
    async def get_generation_status(self, generation_id: str) -> GenerationResult: ...

    @abstractmethod
    async def extend_generation(
        self,
        *,
        parent_generation_id: str,
        prompt: str,
        tier: str,
        orientation: str,
        duration: float,
        reference_image_path: Path | None = None,
    ) -> GenerationResult: ...

    @abstractmethod
    async def download_generation(self, generation: GenerationResult, destination: Path) -> Path: ...

    async def cancel_generation(self, generation_id: str) -> bool:
        return False

    async def find_generation_by_idempotency(self, idempotency_key: str) -> GenerationResult | None:
        """Reconcile a submission whose response may have been lost."""
        return None

    async def analyze_image(
        self,
        *,
        image_path: Path,
        project_title: str,
        reference_description: str,
    ) -> _ImageAnalysis:
        """Analyze a project asset image such as a previous scene's last frame.

        This is optional. Providers that do not support image analysis should raise
        VisionModelError or return a blocked result.
        """
        raise NotImplementedError
