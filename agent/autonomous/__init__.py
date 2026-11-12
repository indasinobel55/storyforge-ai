"""Fully autonomous video generation from a master prompt document.

Runs offline end to end: parse -> plan -> generate per-scene clips ->
narrate -> ambient sound design -> assemble -> validate -> final MP4.

Usage::

    python -m agent.autonomous prompts/obsidian_spire.md
    python -m agent.autonomous prompts/obsidian_spire.md --dry-run
"""

from agent.autonomous.masterprompt import (
    MasterPrompt,
    parse_master_prompt,
    parse_master_prompt_file,
)
from agent.autonomous.runner import (
    AutonomousConfig,
    AutonomousPipeline,
    AutonomousResult,
)

__all__ = [
    "MasterPrompt",
    "parse_master_prompt",
    "parse_master_prompt_file",
    "AutonomousConfig",
    "AutonomousPipeline",
    "AutonomousResult",
]
