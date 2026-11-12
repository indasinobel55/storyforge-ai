from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from agent.core.errors import ContinuityError, FrameExtractionError, VisionModelError
from agent.core.util import extract_last_frame, probe_video
from agent.planner.deterministic import build_autonomous_scene_prompt
from agent.scenes.spec import CharacterSpec, SceneSpec, style_plain_language


@dataclass
class _ImageAnalysis:
    description: str
    blocked: bool = False
    error: str | None = None


class FrameAnalysisResult:
    def __init__(
        self,
        *,
        frame_path: Path,
        raw_analysis: str,
        summary: str,
        blocked: bool = False,
        error: str | None = None,
    ) -> None:
        self.frame_path = frame_path
        self.raw_analysis = raw_analysis
        self.summary = summary
        self.blocked = blocked
        self.error = error

    @property
    def usable(self) -> bool:
        return not self.blocked and bool(self.summary)


class ContinuityService:
    """Visual-continuity stage for autonomous sequential generation.

    Responsibilities:
    - extract the previous scene's last frame,
    - send it to a configured vision adapter,
    - write a continuation passage,
    - build the next scene's final prompt including that continuation.

    This path is optional only when a real vision adapter is available. The
    default simulated-test path still exercises the full continuation chain so
    that scripts and specs can be verified before any real vision API is
    integrated.
    """

    def __init__(self, vision_adapter: object | None, fallback_when_unavailable: bool = True) -> None:
        self._vision_adapter = vision_adapter
        self._fallback_when_unavailable = fallback_when_unavailable

    async def analyze_previous_frame(
        self,
        *,
        previous_scene_spec: SceneSpec,
        previous_clip_path: Path,
        project_title: str,
        project_style: str,
        characters: list[CharacterSpec],
    ) -> FrameAnalysisResult:
        """Analyze the actual final frame of the previous scene.

        If no vision adapter is configured or available, the stage is marked blocked
        rather than silently skipped.
        """
        frame_path = previous_clip_path.parent / f"{previous_clip_path.stem}_last.png"
        try:
            if not frame_path.exists():
                extract_last_frame(previous_clip_path, frame_path)
            reference = style_plain_language(
                project_style,
                ", ".join(
                    f"{character.name}, {character.bible()}" for character in characters if character.name
                ) or "the established characters",
                previous_scene_spec.actions or previous_scene_spec.narration or "the previous scene's action.",
            )
            analysis = await self._analyze_image(
                frame_path,
                project_title=project_title,
                reference_description=reference,
            )
            return FrameAnalysisResult(
                frame_path=frame_path,
                raw_analysis=analysis.description,
                summary=self._summarize_analysis(
                    analysis.description,
                    previous_scene_spec=previous_scene_spec,
                    characters=characters,
                ),
                blocked=analysis.blocked,
                error=analysis.error,
            )
        except FrameExtractionError:
            raise
        except Exception as error:
            raise VisionModelError(f"Frame analysis failed: {error}") from error

    async def _analyze_image(
        self,
        frame_path: Path,
        *,
        project_title: str,
        reference_description: str,
    ) -> _ImageAnalysis:
        if self._vision_adapter is None:
            raise VisionModelError("No vision adapter configured")
        if not hasattr(self._vision_adapter, "analyze_image"):
            raise VisionModelError("Vision adapter does not support image analysis")
        result = await self._vision_adapter.analyze_image(
            image_path=frame_path,
            project_title=project_title,
            reference_description=reference_description,
        )
        if isinstance(result, _ImageAnalysis) or (
            hasattr(result, "description") and hasattr(result, "blocked")
        ):
            return _ImageAnalysis(
                description=str(getattr(result, "description", "") or ""),
                blocked=bool(getattr(result, "blocked", False)),
                error=getattr(result, "error", None),
            )
        if isinstance(result, str):
            return _ImageAnalysis(description=result, blocked=False)
        if isinstance(result, dict):
            return _ImageAnalysis(
                description=str(result.get("description") or result.get("analysis") or ""),
                blocked=bool(result.get("blocked")),
                error=(result.get("error") or result.get("message") or None),
            )
        raise VisionModelError("Unexpected vision adapter response type")

    def _summarize_analysis(
        self,
        description: str,
        *,
        previous_scene_spec: SceneSpec,
        characters: list[CharacterSpec],
    ) -> str:
        if not description:
            return ""
        character_lookup = {character.name: character for character in characters}
        name_lines = []
        lowered = description.lower()
        for name in character_lookup:
            if name.lower() in lowered:
                character = character_lookup[name]
                name_lines.append(f"{name}: {character.bible()}")
        character_summary = "; ".join(name_lines) if name_lines else "the established characters"
        return (
            f"The previous shot ended with {description.strip()}. "
            f"Maintain character appearance: {character_summary}."
        )

    async def write_continuation(
        self,
        *,
        script_segment: str,
        frame_analysis_summary: str,
        scene_number: int,
        total_scenes: int,
        project_title: str,
    ) -> str:
        if not frame_analysis_summary:
            raise ContinuityError("Cannot write continuation without a frame analysis summary")
        return (
            f"Continue directly from the previous frame. {frame_analysis_summary} "
            f"Now: {(script_segment or '').strip()}. "
            f"Move the story toward the next event and preserve the intended ending. "
            + (
                "This is the final scene; resolve the story."
                if scene_number >= total_scenes
                else "Set up the next beat without changing the established world."
            )
        )

    async def build_next_prompt(
        self,
        *,
        scene: SceneSpec,
        project_title: str,
        project_style: str,
        project_characters: list[CharacterSpec],
        frame_analysis_summary: str | None,
        continuation_passage: str | None,
        is_final_scene: bool = False,
    ) -> str:
        if not frame_analysis_summary and not continuation_passage:
            raise ContinuityError("Next scene prompt requires frame analysis or continuation context")
        return build_autonomous_scene_prompt(
            scene=scene,
            project_title=project_title,
            project_style=project_style,
            project_characters=project_characters,
            previous_frame_analysis=frame_analysis_summary,
            continuation_passage=continuation_passage,
            is_final_scene=is_final_scene,
        )


ContinuityService.FrameAnalysisResult = FrameAnalysisResult
