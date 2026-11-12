from __future__ import annotations

import time

import requests

from agent.core.errors import PlanningError
from agent.core.util import extract_json_object
from agent.scenes.spec import CharacterSpec, ScenePlan, SceneSpec


def _build_messages(
    source: str,
    title: str,
    style: str,
    genre: str | None,
    target_scenes: int,
    scene_seconds: int,
    characters: list[CharacterSpec],
    analysis: dict,
    reference_notes: str | None,
) -> list[dict[str, str]]:
    character_text = "\n".join(character.bible() for character in characters) or "No predefined characters"
    prompt = (
        "You are a senior cinematic director and screenwriter. Turn the source material into a complete "
        "short-film scene plan. Return valid JSON only, no markdown and no commentary.\n\n"
        f"Title: {title}\nGenre: {genre or 'unspecified'}\nStyle: {style}\n"
        f"Target scene count: exactly {target_scenes}\nEach scene duration: exactly {scene_seconds} seconds\n"
        f"Characters:\n{character_text}\n"
        f"Script analysis (dialogue, locations, transitions): {analysis}\n"
        f"Reference notes: {reference_notes or 'none'}\n\n"
        "Schema:\n"
        '{"title":"...","logline":"...","characters":[{"name":"...","description":"...",'
        '"age_range":"...","appearance":{}}],'
        '"scenes":[{"scene_number":1,"title":"...","narrative_purpose":"...","duration":8,'
        '"environment":"...","character_presence":["..."],"actions":"...","camera":"...",'
        '"lighting":"...","visual_style":"...","prompt":"...","negative_prompt":"...",'
        '"continuity":"...","previous_scene_relationship":"...","next_scene_relationship":"...",'
        '"narration":"...","dialogue":"..."}]}\n\n'
        "Rules:\n"
        "1. Preserve the source story, characters, and important details.\n"
        "2. Each scene must be a distinct filmable beat.\n"
        "3. Each prompt must be 70-140 words and describe subject, action, environment, camera, lighting, continuity.\n"
        "4. Every prompt must include: No text, no subtitles, no captions, no logos, no watermarks.\n"
        "5. Scenes after the first must describe continuing from the previous final frame.\n"
        "6. Keep one consistent protagonist, wardrobe, environment, and color grade across all scenes.\n"
        "7. Do not describe unsafe, explicit, or disallowed content.\n"
        "8. Use only ASCII double quotes for JSON syntax. Use single quotes inside string values.\n\n"
        f"Source material:\n{source}"
    )
    return [
        {"role": "system", "content": "You are a precise cinematic planner. Return only valid JSON."},
        {"role": "user", "content": prompt},
    ]


def llm_plan(
    *,
    source: str,
    title: str,
    style: str,
    genre: str | None,
    orientation: str,
    aspect_ratio: str,
    target_scenes: int,
    scene_seconds: int,
    target_duration_seconds: int,
    characters: list[CharacterSpec],
    analysis: dict,
    llm_url: str,
    timeout_seconds: int,
    reference_notes: str | None = None,
) -> ScenePlan:
    messages = _build_messages(
        source, title, style, genre, target_scenes, scene_seconds, characters, analysis, reference_notes
    )
    payload = {"model": "openai", "messages": messages, "temperature": 0.65, "max_tokens": 8000}
    last_error: Exception | None = None
    for attempt in range(2):
        try:
            response = requests.post(llm_url, json=payload, timeout=timeout_seconds)
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            data = extract_json_object(content)
            raw_scenes = data.get("scenes")
            if not isinstance(raw_scenes, list) or not raw_scenes:
                raise ValueError("LLM returned no scenes")
            llm_characters = []
            for raw in data.get("characters") or []:
                if not isinstance(raw, dict):
                    continue
                llm_characters.append(
                    CharacterSpec(
                        name=str(raw.get("name") or "Character").strip(),
                        age_range=raw.get("age_range"),
                        description=str(raw.get("description") or "").strip(),
                        appearance=raw.get("appearance") or {},
                    )
                )
            merged_characters = {character.name.lower(): character for character in characters}
            for character in llm_characters:
                merged_characters.setdefault(character.name.lower(), character)

            scenes: list[SceneSpec] = []
            for offset, raw in enumerate(raw_scenes[:target_scenes]):
                if not isinstance(raw, dict):
                    continue
                number = int(raw.get("scene_number") or offset + 1)
                prompt = str(raw.get("prompt") or "").strip()
                if not prompt:
                    raise ValueError(f"Scene {number} has no prompt")
                lower = prompt.lower()
                if f"{scene_seconds}-second" not in lower and f"{scene_seconds} second" not in lower:
                    prompt = f"Create an {scene_seconds}-second cinematic shot.\n{prompt}"
                if "no text" not in lower:
                    prompt += "\nNo text, no subtitles, no captions, no logos, no watermarks."
                scenes.append(
                    SceneSpec(
                        scene_number=offset + 1,
                        title=str(raw.get("title") or f"Scene {offset + 1}").strip(),
                        narrative_purpose=str(raw.get("narrative_purpose") or "").strip(),
                        duration=float(raw.get("duration") or scene_seconds),
                        environment=str(raw.get("environment") or "").strip(),
                        character_presence=[str(item) for item in raw.get("character_presence") or []],
                        actions=str(raw.get("actions") or raw.get("narration") or "").strip(),
                        camera=str(raw.get("camera") or "cinematic camera movement").strip(),
                        lighting=str(raw.get("lighting") or "cinematic natural light").strip(),
                        visual_style=str(raw.get("visual_style") or style).strip(),
                        prompt=prompt,
                        negative_prompt=raw.get("negative_prompt"),
                        continuity=str(raw.get("continuity") or "").strip(),
                        previous_scene_relationship=str(raw.get("previous_scene_relationship") or "").strip(),
                        next_scene_relationship=str(raw.get("next_scene_relationship") or "").strip(),
                        narration=str(raw.get("narration") or "").strip(),
                        dialogue=str(raw.get("dialogue") or "").strip(),
                    )
                )
            if not scenes:
                raise ValueError("No valid scenes after normalization")
            return ScenePlan(
                title=str(data.get("title") or title).strip(),
                logline=str(data.get("logline") or "").strip(),
                style=style,
                orientation=orientation,  # type: ignore[arg-type]
                aspect_ratio=aspect_ratio,
                scene_seconds=scene_seconds,
                target_duration_seconds=target_duration_seconds,
                source=source,
                provider="llm",
                characters=list(merged_characters.values()),
                scenes=scenes,
            )
        except Exception as error:  # noqa: BLE001 - retry then surface
            last_error = error
            time.sleep(2)
    raise PlanningError(f"LLM planning failed: {last_error}")
