"""Parse a structured "master prompt" markdown document into a ScenePlan.

The expected document format (see prompts/obsidian_spire.md) is a markdown
file with sections:

- A ``## Title`` line for the film.
- ``### PROJECT REQUIREMENTS`` with bullet fields such as
  ``**Total scenes:**``, ``**Duration:**`` and ``**Art style:**``.
- ``### VISUAL ART DIRECTION`` prose plus a colour palette bullet list.
- ``### CHARACTER CONTINUITY`` with ``**NAME:** description`` paragraphs.
- ``### COMPLETE STORY`` with per-scene blocks::

    **SCENE 01 — TITLE (MM:SS-MM:SS)**
    <visual description paragraphs>
    Camera: <camera directions>
    Sound: <sound design directions>

Parsing is fully deterministic and offline: no planner LLM is required.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from agent.core.errors import PlanningError
from agent.scenes.spec import CharacterSpec, ScenePlan, SceneSpec

SCENE_HEADER_RE = re.compile(
    r"^\s*\*\*SCENE\s+(\d+)\s*[—–-]\s*(.+?)\s*\(\s*(\d{1,2}):(\d{2})\s*[—–-]\s*(\d{1,2}):(\d{2})\s*\)\s*\*\*\s*$",
    re.IGNORECASE,
)
CHARACTER_RE = re.compile(r"^\s*\*\*(.+?):\*\*\s*(.+)$")
FIELD_RE = re.compile(r"^\s*\*\*([^*]+):?\*\*\s*(.*)$")
PALETTE_VALUE_RE = re.compile(r"^-\s+(.+)$")
QUOTED_LINE_RE = re.compile(r'["\u201c]([^"\u201d]{4,120})["\u201d]')

NEGATIVE_PROMPT = (
    "photorealism, 3D CGI render, anime aesthetic, bright saturated colors, "
    "generic fantasy, text, watermark, logo, on-screen dialogue, subtitles, "
    "visible mouths, lip movement, modern clothing, camera shake"
)

# Rough speech budget for narration composition. SAPI voices speak roughly
# 150-170 words per minute at rate 0; we target about 30 words per 8s scene
# and let the per-scene tempo correction handle the remainder.
WORDS_PER_SECOND = 3.6


@dataclass
class SceneBlock:
    number: int
    title: str
    timecode_from: str
    timecode_to: str
    description_sentences: list[str] = field(default_factory=list)
    narration_directives: list[str] = field(default_factory=list)
    camera: str = ""
    sound: str = ""
    quoted_lines: list[str] = field(default_factory=list)


@dataclass
class MasterPrompt:
    title: str
    style: str
    art_direction: str
    palette: list[str]
    scenes: list[SceneBlock]
    scene_seconds: float = 8.0
    scene_count: int | None = None
    total_runtime: float | None = None
    characters: list[tuple[str, str]] = field(default_factory=list)
    source_path: str = ""

    def style_line(self) -> str:
        palette = ", ".join(self.palette) if self.palette else "muted atmospheric tones"
        direction = (self.art_direction or "").strip().rstrip(".")
        return f"{self.style}. Visual direction: {direction}. Colour palette: {palette}."

    def character_bibles(self, names: list[str] | None = None) -> str:
        selected = self.characters if not names else [c for c in self.characters if c[0] in names]
        return " ".join(f"{name}: {description}" for name, description in selected)


def _read_source(path: Path) -> str:
    if not path.exists():
        raise PlanningError(f"Master prompt file not found: {path}")
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise PlanningError(f"Cannot read master prompt {path}: {error}") from error


def _split_sections(text: str) -> dict[str, list[str]]:
    """Split the document into mapping of section header -> body lines."""
    sections: dict[str, list[str]] = {}
    current = "_header"
    sections[current] = []
    for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if line.startswith("###"):
            current = line.lstrip("#").strip().lower()
            sections.setdefault(current, [])
        else:
            sections.setdefault(current, []).append(line)
    return sections


def _find_section(sections: dict[str, list[str]], keyword: str) -> list[str]:
    for name, lines in sections.items():
        if keyword.split()[-1] in name:
            return lines
    return []


def _requirement_int(lines: list[str], label: str) -> int | None:
    pattern = re.compile(rf"\*\*{label}[^*]*\*\*\s*:?\s*(\d+)", re.IGNORECASE)
    for line in lines:
        match = pattern.search(line)
        if match:
            return int(match.group(1))
    return None


def _extract_parts(text: str) -> tuple[str, str, list[str]]:
    art_direction_parts: list[str] = []
    palette: list[str] = []
    paragraph: list[str] = []
    for line in text.replace("\r\n", "\n").split("\n"):
        stripped = line.strip()
        palette_match = PALETTE_VALUE_RE.match(stripped)
        if palette_match and not stripped.startswith("- **"):
            value = palette_match.group(1).strip().rstrip(".")
            if 2 <= len(value) <= 80 and not value.startswith("**"):
                palette.append(value)
                continue
        if stripped and not stripped.startswith("**"):
            paragraph.append(stripped)
        elif paragraph:
            art_direction_parts.append(" ".join(paragraph))
            paragraph = []
    if paragraph:
        art_direction_parts.append(" ".join(paragraph))
    return " ".join(art_direction_parts[:2]), ", ".join(palette[:8]), palette


def parse_master_prompt(text: str, source: str = "") -> MasterPrompt:
    sections = _split_sections(text)

    title = "_header"
    for line in sections.get("_header", []):
        if line.startswith("## ") and not line.startswith("###"):
            title = line[3:].strip()
            break
    if title == "_header":
        raise PlanningError("Master prompt is missing a '## Title' line")

    requirements = _find_section(sections, "project requirements")
    scene_count = _requirement_int(requirements, "total scenes")
    total_runtime = _requirement_int(requirements, "total runtime")

    scene_seconds = 8.0
    for line in requirements:
        match = re.search(r"(\d+)\s+seconds\s+per\s+scene", line, re.IGNORECASE)
        if match:
            scene_seconds = float(match.group(1))
            break

    style = ""
    for line in requirements:
        match = re.search(r"\*\*Art style:\*\*\s*([^*\n]+)", line, re.IGNORECASE)
        if match:
            style = match.group(1).strip().rstrip(".")
            break
    if not style:
        style = "cinematic hand-drawn dark fantasy"

    art_text = "\n".join(_find_section(sections, "visual art direction"))
    art_direction, _palette_inline, palette = _extract_parts(art_text)

    characters: list[tuple[str, str]] = []
    for line in _find_section(sections, "character continuity"):
        match = CHARACTER_RE.match(line)
        if match:
            characters.append((match.group(1).strip(), match.group(2).strip()))

    story_lines = _find_section(sections, "complete story")
    blocks = _parse_story_blocks(story_lines)
    if not blocks:
        raise PlanningError("Master prompt contains no 'SCENE NN — TITLE (MM:SS-MM:SS)' blocks")

    numbered = [block.number for block in blocks]
    if len(numbered) != len(set(numbered)):
        raise PlanningError("Duplicate scene numbers in master prompt")

    return MasterPrompt(
        title=title,
        style=style,
        art_direction=art_direction,
        palette=palette,
        scenes=blocks,
        scene_seconds=scene_seconds,
        scene_count=scene_count if scene_count is not None else len(blocks),
        total_runtime=float(total_runtime) if total_runtime is not None else None,
        characters=characters,
        source_path=source,
    )


def _parse_story_blocks(lines: list[str]) -> list[SceneBlock]:
    blocks: list[SceneBlock] = []
    index = 0
    while index < len(lines):
        match = SCENE_HEADER_RE.match(lines[index])
        index += 1
        if not match:
            continue
        block = SceneBlock(
            number=int(match.group(1)),
            title=match.group(2).strip().title(),
            timecode_from=f"{match.group(3)}:{match.group(4)}",
            timecode_to=f"{match.group(5)}:{match.group(6)}",
        )
        paragraph: list[str] = []
        while index < len(lines) and not SCENE_HEADER_RE.match(lines[index]) and not lines[index].startswith("###"):
            line = lines[index].strip()
            index += 1
            if not line:
                if paragraph:
                    _absorb_paragraph(block, paragraph)
                    paragraph = []
                continue
            if line.lower().startswith("camera:"):
                block.camera = _field_value(line)
                continue
            if line.lower().startswith("sound:"):
                block.sound = _field_value(line)
                continue
            paragraph.append(line)
        if paragraph:
            _absorb_paragraph(block, paragraph)
        blocks.append(block)
    return blocks


def _field_value(line: str) -> str:
    value = line.split(":", 1)[1].strip().rstrip(".")
    return value[:400]


def _absorb_paragraph(block: SceneBlock, paragraph: list[str]) -> None:
    joined = " ".join(paragraph).strip()
    if not joined:
        return
    if joined.lower().startswith("narration must"):
        block.narration_directives.append(joined)
        quoted = QUOTED_LINE_RE.findall(joined)
        block.quoted_lines.extend(quoted)
    else:
        block.description_sentences.append(joined)
    quoted = QUOTED_LINE_RE.findall(joined)
    if quoted and not joined.lower().startswith("narration must"):
        block.quoted_lines.extend(quoted)


def _compose_narration(block: SceneBlock) -> str:
    """Compose third-person voiceover narration from the scene description."""
    sentences: list[str] = []
    for chunk in block.description_sentences:
        parts = re.split(r"(?<=[.!?])\s+", chunk)
        sentences.extend(part.strip() for part in parts if part.strip())
    if not sentences:
        sentences = [f"As the story unfolds, {block.title.lower()} fills the frame."]

    budget = int(WORDS_PER_SECOND * 7)
    narration: list[str] = []
    used = 0
    for sentence in sentences:
        words = len(sentence.split())
        if used + words > budget and narration:
            break
        narration.append(sentence)
        used += words
        if used >= budget:
            break
    text = " ".join(narration) or sentences[0]
    text = text.strip()
    if not text.endswith((".", "!", "?")):
        text += "."
    if block.quoted_lines and block.quoted_lines[0].strip() not in text:
        text = text + " " + block.quoted_lines[0].strip()
    return text


def _characters_for_prompt(document: MasterPrompt, block: SceneBlock) -> list[str]:
    """Return character names whose distinctive token appears in the scene.

    Previously this fell back to ALL characters when the full name did not
    match verbatim (e.g. 'the colossal Obsidian Spire'), which injected the
    Watcher and Mirror into scenes 1-9 prompts and caused hallucinations.
    Matching the last token ('shard', 'watcher', 'mirror', 'spire') mirrors
    `character_presence` detection and keeps each prompt focused.
    """
    haystack = " ".join(block.description_sentences).lower()
    names: list[str] = []
    for name, _ in document.characters:
        token = name.split()[-1].lower()
        if token and token in haystack:
            names.append(name)
    return names


def master_prompt_to_scene_plan(document: MasterPrompt) -> ScenePlan:
    style_line = document.style_line()
    scene_seconds = max(1.0, min(10.0, document.scene_seconds))
    # Visual lighting defaults derived from the art direction, NOT from the
    # sound-design line (previously Sound was mislabelled as Lighting).
    default_lighting = (
        "minimal atmospheric lighting; the Shard's cracked-mask pale-blue glow is the "
        "primary light source, otherwise near-black with cold silver rim light on stone edges"
    )

    scenes: list[SceneSpec] = []
    for position, block in enumerate(document.scenes):
        present = []
        for name, _ in document.characters:
            if name.lower() in ("the obsidian spire",):
                continue
            if name.split()[-1].lower() in " ".join(block.description_sentences).lower():
                present.append(name)
        characters_for_prompt = _characters_for_prompt(document, block)
        bible = document.character_bibles(characters_for_prompt)
        is_first = block.number == 1
        is_last = block.number == len(document.scenes)
        start_frame = (
            "Opening frame: establish the Obsidian Spire"
            if is_first
            else f"Start frame: seamlessly continue from scene {block.number - 1}'s final frame; "
            "same characters, same palette, same film grain"
        )
        end_frame = (
            "Final frame fades to black"
            if is_last
            else f"End frame: leave motion that resolves naturally into scene {block.number + 1}"
        )

        prompt_parts = [
            f"Cinematic hand-drawn 2D animated scene {block.number} of {len(document.scenes)}: {block.title}. "
            f"{int(scene_seconds)} seconds, single continuous shot, no cuts.",
            f"Style: {style_line}",
            f"Subject to preserve: {bible}" if bible else "Subject: location only, no characters entering frame.",
            f"Action sequence (play in order): {' '.join(block.description_sentences)}",
            f"Camera: {block.camera or 'steady cinematic framing with slow deliberate movement'}",
            f"Lighting: {default_lighting}",
            f"Sound design direction (audio only): {block.sound}" if block.sound else "Sound: silent dark ambience.",
            f"Continuity: {start_frame}. {end_frame}.",
            "Rendering: intricate hand-inked outlines, layered multiplane parallax, painted watercolour textures, "
            "35mm film grain, vignette; no dialogue, no lip movement, no text, no subtitles, "
            "no captions, no logos, no watermarks, no photorealism, no 3D CGI.",
        ]
        narration = _compose_narration(block)

        scenes.append(
            SceneSpec(
                scene_number=block.number,
                title=block.title,
                narrative_purpose=(block.narration_directives[0][:300] if block.narration_directives else ""),
                duration=scene_seconds,
                environment=block.title,
                character_presence=present,
                actions=" ".join(block.description_sentences)[:600],
                camera=block.camera,
                # lighting = visual lighting; sound_design carries the Sound: line
                # so runner/soundstage ambience detection keeps working.
                lighting=default_lighting,
                sound_design=block.sound,
                visual_style=document.style,
                prompt="\n".join(prompt_parts),
                negative_prompt=NEGATIVE_PROMPT,
                continuity=f"Match characters and palette of every other scene; {block.timecode_from}-{block.timecode_to}.",
                previous_scene_relationship=(
                    f"Continues from scene {block.number - 1}" if block.number > 1 else "Opening shot"
                ),
                next_scene_relationship=(
                    f"Leads into scene {block.number + 1}" if block.number < len(document.scenes) else "Final frame fades to black"
                ),
                narration=narration,
                dialogue="",
            )
        )

    target = int(document.total_runtime or (len(scenes) * scene_seconds))
    logline = " ".join(document.scenes[0].description_sentences)[:300]
    return ScenePlan(
        title=document.title,
        logline=logline,
        style=document.style_line(),
        orientation="landscape",
        aspect_ratio="16:9",
        scene_seconds=int(scene_seconds),
        target_duration_seconds=target,
        source=document.source_path or "master-prompt",
        provider="parsed_master_prompt",
        characters=[
            CharacterSpec(name=name, description=description) for name, description in document.characters
        ],
        scenes=scenes,
    )


def parse_master_prompt_file(path: Path) -> tuple[MasterPrompt, ScenePlan]:
    text = _read_source(path)
    document = parse_master_prompt(text, source=str(path))
    return document, master_prompt_to_scene_plan(document)
