from __future__ import annotations

import math

from agent.core.util import split_sentences
from agent.planner.analyzer import ScriptAnalysis, analyze_script
from agent.scenes.spec import CharacterSpec, ScenePlan, SceneSpec

CAMERAS = [
    "slow dolly-in, 35mm lens, shallow depth of field",
    "smooth lateral tracking shot, 50mm lens",
    "locked-off wide shot with a subtle push-in",
    "slow orbit around the subject, 40mm lens",
    "handheld follow shot with gentle movement",
    "crane rise revealing the environment",
    "low-angle hero shot, 28mm lens",
    "over-the-shoulder follow shot, 40mm lens",
]

LIGHTING = [
    "cool moonlight with volumetric haze",
    "warm golden-hour backlight and soft rim light",
    "high-contrast noir lighting with deep shadows",
    "soft overcast daylight with muted colors",
    "neon rim light and practical city glow",
    "candlelit amber glow with rich falloff",
    "dramatic shafts of sunlight through mist",
]

NO_TEXT = "No text, no subtitles, no captions, no logos, no watermarks."


def _group_sentences(sentences: list[str], target: int) -> list[str]:
    if not sentences:
        return [""] * target
    if len(sentences) <= target:
        groups = list(sentences)
        while len(groups) < target:
            groups.append(groups[-1])
        return groups
    per_scene = max(1, math.ceil(len(sentences) / target))
    groups = [" ".join(sentences[i : i + per_scene]) for i in range(0, len(sentences), per_scene)]
    if len(groups) > target:
        groups = groups[: target - 1] + [" ".join(sentences[(target - 1) * per_scene :])]
    return groups


def _character_presence(beat: str, characters: list[CharacterSpec]) -> list[str]:
    lowered = beat.lower()
    return [character.name for character in characters if character.name.lower() in lowered]


def _compose_prompt(
    *,
    beat: str,
    title: str,
    style: str,
    scene_seconds: int,
    camera: str,
    lighting: str,
    continuity: str,
    characters: list[CharacterSpec],
    present: list[str],
    environment: str,
) -> str:
    bibles = [character.bible() for character in characters if not present or character.name in present]
    if not bibles:
        bibles = [character.bible() for character in characters]
    cast = " ".join(f"Character: {bible}." for bible in bibles[:4]) if bibles else ""
    return (
        f"Create an {scene_seconds}-second cinematic shot for the short film \"{title}\".\n"
        f"STORY BEAT: {beat}\n"
        f"ENVIRONMENT: {environment or 'a coherent environment established by the story beat'}\n"
        f"CHARACTERS: {cast or 'the protagonist described in the story beat'}\n"
        f"CAMERA: {camera}.\n"
        f"LIGHTING: {lighting}.\n"
        f"CONTINUITY: {continuity}\n"
        f"STYLE: {style}.\n"
        "Photorealistic or stylized as described, highly detailed, coherent motion, natural physics, "
        "consistent color grade. " + NO_TEXT
    )


def deterministic_plan(
    *,
    source: str,
    title: str,
    style: str,
    orientation: str,
    aspect_ratio: str,
    target_scenes: int,
    scene_seconds: int,
    target_duration_seconds: int,
    characters: list[CharacterSpec] | None = None,
    genre: str | None = None,
    reference_notes: str | None = None,
) -> ScenePlan:
    characters = characters or []
    analysis: ScriptAnalysis = analyze_script(source, [character.name for character in characters])
    target_scenes = max(1, min(20, target_scenes))
    beats = _group_sentences(analysis.sentences, target_scenes)
    environment = ", ".join(analysis.locations[:3]) if analysis.locations else "the story world"
    logline = (analysis.sentences[0] if analysis.sentences else source)[:300]

    scenes: list[SceneSpec] = []
    for index, beat in enumerate(beats, start=1):
        camera = CAMERAS[(index - 1) % len(CAMERAS)]
        lighting = LIGHTING[(index - 1) % len(LIGHTING)]
        present = _character_presence(beat, characters)
        if index == 1:
            continuity = (
                "Establish the protagonist, environment, wardrobe, props, and color grade for the entire film."
            )
        else:
            continuity = (
                "Continue seamlessly from the last frame of the previous shot. Preserve the same characters, "
                "wardrobe, props, environment, lighting direction, and color grade."
            )
        dialogue = "; ".join(
            f"{item['speaker']}: {item['line']}" if item["speaker"] else item["line"]
            for item in analysis.dialogue
            if item["line"] and item["line"][:24].lower() in beat.lower()
        )
        prompt = _compose_prompt(
            beat=beat,
            title=title,
            style=style,
            scene_seconds=scene_seconds,
            camera=camera,
            lighting=lighting,
            continuity=continuity,
            characters=characters,
            present=present,
            environment=environment,
        )
        if genre:
            prompt = f"Genre: {genre}. " + prompt
        if reference_notes:
            prompt += f"\nREFERENCE NOTES: {reference_notes}"
        scenes.append(
            SceneSpec(
                scene_number=index,
                title=f"Scene {index}: {' '.join(beat.split()[:7]) or title}",
                narrative_purpose=beat[:400],
                duration=float(scene_seconds),
                environment=environment,
                character_presence=present or [character.name for character in characters][:3],
                actions=beat,
                camera=camera,
                lighting=lighting,
                visual_style=style,
                prompt=prompt,
                negative_prompt="text, subtitles, captions, logos, watermarks, distorted anatomy, flicker",
                continuity=continuity,
                previous_scene_relationship="Concludes the previous beat." if index > 1 else "Opening scene.",
                next_scene_relationship="Sets up the next beat." if index < len(beats) else "Final scene.",
                narration=beat,
                dialogue=dialogue,
            )
        )

    return ScenePlan(
        title=title,
        logline=logline,
        style=style,
        orientation=orientation,  # type: ignore[arg-type]
        aspect_ratio=aspect_ratio,
        scene_seconds=scene_seconds,
        target_duration_seconds=target_duration_seconds,
        source=source,
        provider="deterministic",
        characters=characters,
        scenes=scenes,
    )


def build_autonomous_scene_prompt(
    *,
    scene: SceneSpec,
    project_title: str,
    project_style: str,
    project_characters: list[CharacterSpec],
    previous_frame_analysis: str | None,
    continuation_passage: str | None,
    is_final_scene: bool = False,
) -> str:
    """Build the prompt that is actually sent to the video provider for an autonomous
    continuity-aware scene.

    The previous frame analysis and the agent-written continuation passage are included
    verbatim so the next scene is generated from the real previous visual state, not only
    from generic continuity boilerplate.
    """
    character_bibles = ", ".join(
        f"{character.name} ({character.bible()})" for character in project_characters if character.name
    ) or "the protagonist described in the scene"
    parts = [
        f"Create an {int(scene.duration)}-second cinematic shot for the short film \"{project_title}\".",
        f"STORY SEGMENT: {scene.narration or scene.actions or scene.prompt}",
        f"VISUAL DESCRIPTION: {scene.environment or 'a coherent environment established by the story'}.",
        f"CHARACTERS: {character_bibles}.",
        f"CHARACTER ACTIONS: {scene.actions or 'Continue the action implied by the story segment.'}",
        f"ENVIRONMENT: {scene.environment or 'maintain the established environment unless the story transitions.'}",
        f"CAMERA: {scene.camera or 'a cinematic framing appropriate to the scene.'}.",
        f"LIGHTING AND ATMOSPHERE: {scene.lighting or 'maintain consistent lighting and atmosphere.'}.",
        f"VISUAL STYLE: {scene.visual_style or project_style}.",
    ]
    if previous_frame_analysis:
        parts.append(f"PREVIOUS FRAME ANALYSIS:\n{previous_frame_analysis}")
    if continuation_passage:
        parts.append(f"CONTINUATION PASSAGE:\n{continuation_passage}")
    parts.append(
        "CONTINUITY INSTRUCTIONS: Preserve the characters, wardrobe, environment, props, camera direction, "
        "lighting direction, color grade, and ongoing action exactly as described above. Do not teleport characters "
        "or objects between shots. Resolve the story segment naturally without inventing unrelated new subplots. "
        "If this is the final scene, resolve the intended story ending; do not leave the action hanging."
    )
    if is_final_scene:
        parts.append("FINAL SCENE: this is the last shot of the film; complete the intended story ending.")
    parts.append(
        "Photorealistic or stylized as described, highly detailed, coherent motion, natural physics, "
        "consistent color grade. No text, no subtitles, no captions, no logos, no watermarks."
    )
    return "\n".join(parts)
