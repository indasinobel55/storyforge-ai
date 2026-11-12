from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class CharacterSpec(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    age_range: str | None = None
    description: str = ""
    appearance: dict = Field(default_factory=dict)
    voice_description: str | None = None
    reference_notes: str | None = None

    def bible(self) -> str:
        parts = [self.name]
        if self.age_range:
            parts.append(f"age {self.age_range}")
        if self.description:
            parts.append(self.description)
        return ", ".join(parts)


class SceneSpec(BaseModel):
    scene_number: int = Field(ge=1)
    title: str
    narrative_purpose: str = ""
    duration: float = Field(default=8.0, ge=1.0, le=10.0)
    environment: str = ""
    character_presence: list[str] = Field(default_factory=list)
    actions: str = ""
    camera: str = ""
    lighting: str = ""
    sound_design: str = ""
    visual_style: str = ""
    prompt: str = Field(min_length=1)
    negative_prompt: str | None = None
    reference_assets: list[str] = Field(default_factory=list)
    continuity: str = ""
    previous_scene_relationship: str = ""
    next_scene_relationship: str = ""
    narration: str = ""
    dialogue: str = ""

    @field_validator("scene_number")
    @classmethod
    def positive(cls, value: int) -> int:
        if value < 1:
            raise ValueError("scene_number must be >= 1")
        return value


class ScenePlan(BaseModel):
    version: int = 1
    title: str
    logline: str = ""
    style: str
    orientation: Literal["landscape", "portrait", "square"] = "landscape"
    aspect_ratio: str = "16:9"
    scene_seconds: int = 8
    target_duration_seconds: int = 48
    source: str
    provider: str = "deterministic"
    characters: list[CharacterSpec] = Field(default_factory=list)
    scenes: list[SceneSpec]

    @field_validator("scenes")
    @classmethod
    def scenes_present(cls, value: list[SceneSpec]) -> list[SceneSpec]:
        if not value:
            raise ValueError("Plan must contain at least one scene")
        numbers = [scene.scene_number for scene in value]
        if len(numbers) != len(set(numbers)):
            raise ValueError("Scene numbers must be unique")
        return value

    def total_duration(self) -> float:
        return sum(scene.duration for scene in self.scenes)


def style_plain_language(style: str, character_bibles: str, current_action: str) -> str:
    """Summarize visual style, character look, and current action into a short plain-language
    description suitable for a vision-model analysis request and for the continuation builder.
    """
    style = (style or "cinematic").strip()
    if not style:
        style = "cinematic"
    return (
        f"Style: {style}. "
        f"Characters and their look: {character_bibles or 'the established characters'}. "
        f"Current action and visible state: {current_action or 'the scene is finishing its action'}."
    )


def plan_json_schema() -> dict:
    return ScenePlan.model_json_schema()
