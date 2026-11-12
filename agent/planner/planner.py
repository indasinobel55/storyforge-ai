from __future__ import annotations

from dataclasses import dataclass, field

from agent.core.errors import PlanningError
from agent.planner.analyzer import analyze_script
from agent.planner.deterministic import deterministic_plan
from agent.planner.llm import llm_plan
from agent.scenes.spec import CharacterSpec, ScenePlan


@dataclass
class PlanRequest:
    title: str
    script: str
    style: str
    scene_count: int = 6
    scene_seconds: int = 8
    target_duration_seconds: int = 48
    orientation: str = "landscape"
    aspect_ratio: str = "16:9"
    genre: str | None = None
    characters: list[CharacterSpec] = field(default_factory=list)
    reference_notes: str | None = None
    provider: str = "deterministic"  # deterministic | llm | auto
    llm_url: str = ""
    llm_timeout_seconds: int = 180


def build_plan(request: PlanRequest) -> ScenePlan:
    if not request.script or len(request.script.strip()) < 10:
        raise PlanningError("Script is too short to plan")
    scene_count = max(1, min(20, request.scene_count))
    scene_seconds = max(1, min(10, request.scene_seconds))
    analysis = analyze_script(request.script, [character.name for character in request.characters])

    use_llm = request.provider in {"llm", "auto"} and bool(request.llm_url)
    if use_llm:
        try:
            return llm_plan(
                source=request.script,
                title=request.title,
                style=request.style,
                genre=request.genre,
                orientation=request.orientation,
                aspect_ratio=request.aspect_ratio,
                target_scenes=scene_count,
                scene_seconds=scene_seconds,
                target_duration_seconds=request.target_duration_seconds,
                characters=request.characters,
                analysis=analysis.as_dict(),
                llm_url=request.llm_url,
                timeout_seconds=request.llm_timeout_seconds,
                reference_notes=request.reference_notes,
            )
        except Exception:
            if request.provider == "llm":
                raise
            # fall through to the deterministic planner

    return deterministic_plan(
        source=request.script,
        title=request.title,
        style=request.style,
        orientation=request.orientation,
        aspect_ratio=request.aspect_ratio,
        target_scenes=scene_count,
        scene_seconds=scene_seconds,
        target_duration_seconds=request.target_duration_seconds,
        characters=request.characters,
        genre=request.genre,
        reference_notes=request.reference_notes,
    )
