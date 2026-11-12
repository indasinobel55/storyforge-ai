"""Local Windows execution agent for the AI Video Studio platform.

The agent reuses the shared ``agent`` package (planner, providers, downloader,
FFmpeg assembly and validation) and talks only to the scoped local execution API.
"""

from .client import LocalApiClient, LocalApiError
from .pipeline import LocalConfig, LocalRunner

__all__ = ["LocalApiClient", "LocalApiError", "LocalConfig", "LocalRunner"]
