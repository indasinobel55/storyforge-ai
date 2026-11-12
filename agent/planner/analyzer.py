from __future__ import annotations

import re
from dataclasses import dataclass, field

from agent.core.util import normalize_text, split_sentences

DIALOGUE_RE = re.compile(r"^\s*([A-Z][A-Za-z0-9 _'\-]{1,30}):\s*(.+)$", re.MULTILINE)
QUOTED_RE = re.compile(r"[\"“]([^\"”]{2,300})[\"”]")
TRANSITIONS = {
    "suddenly": "sudden action beat",
    "meanwhile": "parallel storyline",
    "the next day": "time jump",
    "later": "time jump",
    "at dawn": "time of day change",
    "at night": "time of day change",
    "finally": "climactic beat",
    "just then": "sudden action beat",
    "moments later": "time jump",
}
LOCATION_HINTS = [
    "jungle",
    "forest",
    "river",
    "mountain",
    "city",
    "street",
    "village",
    "house",
    "room",
    "office",
    "school",
    "beach",
    "desert",
    "space",
    "ship",
    "cave",
    "castle",
    "rooftop",
    "cliff",
    "field",
    "market",
    "station",
]


@dataclass
class ScriptAnalysis:
    sentences: list[str] = field(default_factory=list)
    dialogue: list[dict[str, str]] = field(default_factory=list)
    speakers: list[str] = field(default_factory=list)
    locations: list[str] = field(default_factory=list)
    transitions: list[str] = field(default_factory=list)
    continuity_requirements: list[str] = field(default_factory=list)
    contradictions: list[str] = field(default_factory=list)
    word_count: int = 0

    def as_dict(self) -> dict:
        return {
            "sentences": len(self.sentences),
            "dialogue": self.dialogue,
            "speakers": self.speakers,
            "locations": self.locations,
            "transitions": self.transitions,
            "continuity_requirements": self.continuity_requirements,
            "contradictions": self.contradictions,
            "word_count": self.word_count,
        }


def analyze_script(script: str, known_characters: list[str] | None = None) -> ScriptAnalysis:
    text = normalize_text(script)
    sentences = split_sentences(text)
    analysis = ScriptAnalysis(sentences=sentences, word_count=len(text.split()))

    speakers: list[str] = []
    for match in DIALOGUE_RE.finditer(text):
        name = match.group(1).strip()
        line = match.group(2).strip()
        if name.lower() in {"scene", "int", "ext", "cut to", "fade in"}:
            continue
        analysis.dialogue.append({"speaker": name, "line": line})
        if name not in speakers:
            speakers.append(name)

    for match in QUOTED_RE.finditer(text):
        line = match.group(1).strip()
        if line and not any(item["line"] == line for item in analysis.dialogue):
            analysis.dialogue.append({"speaker": "", "line": line})

    for name in known_characters or []:
        if name and name not in speakers:
            speakers.append(name)
    analysis.speakers = speakers

    lowered = text.lower()
    analysis.locations = sorted({hint for hint in LOCATION_HINTS if hint in lowered})
    analysis.transitions = sorted({label for keyword, label in TRANSITIONS.items() if keyword in lowered})

    if len(sentences) > 1:
        analysis.continuity_requirements.append("Preserve character wardrobe, props, and color grade across scenes")
    if any(word in lowered for word in ("night", "dark", "shadow")):
        analysis.continuity_requirements.append("Maintain consistent lighting direction and time of day")
    if analysis.locations:
        analysis.continuity_requirements.append(
            f"Keep locations visually consistent: {', '.join(analysis.locations[:4])}"
        )

    duplicates = {name for name in speakers if speakers.count(name) > 1}
    if duplicates:
        analysis.contradictions.append("Duplicate speaker entries: " + ", ".join(sorted(duplicates)))
    if len(text) < 40:
        analysis.contradictions.append("Script is very short; scene planning may be vague")

    return analysis
