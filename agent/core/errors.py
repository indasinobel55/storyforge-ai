from __future__ import annotations


class AgentError(RuntimeError):
    """Base error for the standalone agent."""


class PlanningError(AgentError):
    pass


class ProviderError(AgentError):
    pass


class ProviderDisabledError(ProviderError):
    """Raised when a provider is gated off by configuration or feasibility."""


class ProviderAuthError(ProviderError):
    pass


class GenerationError(AgentError):
    pass


class DownloadError(AgentError):
    pass


class ProcessingError(AgentError):
    pass


class ValidationError(AgentError):
    pass


class CancelledError(AgentError):
    pass


class VisionModelError(AgentError):
    """Raised when the vision analysis stage fails."""


class ContinuityError(AgentError):
    """Raised when the continuity/continuation stage fails."""


class FrameExtractionError(AgentError):
    """Raised when last-frame extraction or its validation fails."""


class PromptBuildError(AgentError):
    """Raised when the autonomous scene prompt cannot be constructed."""
