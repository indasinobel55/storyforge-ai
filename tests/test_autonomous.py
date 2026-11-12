from __future__ import annotations

from pathlib import Path

import pytest

from agent.autonomous.masterprompt import parse_master_prompt_file
from agent.autonomous.soundstage import build_scene_audio
from agent.validation.validator import validate_final

PROMPT_FIXTURE = Path(__file__).resolve().parents[1] / "prompts" / "obsidian_spire.md"


@pytest.fixture
def obsidian_prompt() -> Path:
    if not PROMPT_FIXTURE.exists():
        pytest.skip("prompts/obsidian_spire.md fixture missing")
    return PROMPT_FIXTURE


def test_parse_obsidian_master_prompt(obsidian_prompt: Path) -> None:
    document, plan = parse_master_prompt_file(obsidian_prompt)

    assert document.title.startswith("THE OBSIDIAN SPIRE")
    assert len(document.scenes) == 12
    assert document.scene_seconds == 8.0
    assert document.scene_count == 12
    assert plan.target_duration_seconds == 96
    assert plan.scene_seconds == 8

    assert [scene.scene_number for scene in plan.scenes] == list(range(1, 13))
    for scene in plan.scenes:
        assert scene.duration == 8.0
        assert scene.prompt.strip()
        assert scene.narration.strip()
        assert scene.dialogue == ""

    assert plan.scenes[0].title == "The Obsidian Spire"
    assert plan.scenes[11].title == "The Hunt Had Begun"
    # The final chilling line must be preserved as narration.
    assert "The hunt had begun." in plan.scenes[11].narration
    # Characters carried through the character bible.
    names = [character.name for character in plan.characters]
    assert "THE SHARD" in names
    assert "THE WATCHER" in names
    # Character presence detects the Shard from scene 2 onwards.
    assert "THE SHARD" not in plan.scenes[0].character_presence
    assert "THE SHARD" in plan.scenes[1].character_presence
    # Style and palette carry into the plan style field.
    assert "Hand-Drawn Gothic Metroidvania" in plan.style


def test_parse_consistency_of_timestamps(obsidian_prompt: Path) -> None:
    document, _ = parse_master_prompt_file(obsidian_prompt)
    # Timestamps advance in 8s steps from 00:00 to 01:36.
    assert document.scenes[0].timecode_from == "00:00"
    assert document.scenes[0].timecode_to == "00:08"
    assert document.scenes[-1].timecode_to == "01:36"


async def test_autonomous_mini_run(tmp_path: Path) -> None:
    """Tiny end-to-end run: 2 scenes generated, mixed, assembled and validated."""
    from agent.autonomous.runner import AutonomousConfig, AutonomousPipeline

    prompt = tmp_path / "mini.md"
    prompt.write_text(
        "\n".join(
            [
                "## MINI TEST FILM",
                "",
                "### PROJECT REQUIREMENTS",
                "- **Art style:** Hand-drawn noir ink animation.",
                "",
                "### VISUAL ART DIRECTION",
                "Bold ink outlines with strong silhouettes.",
                "",
                "Colour palette:",
                "- Deep ink black.",
                "- Smoke grey.",
                "",
                "### CHARACTER CONTINUITY",
                "",
                "**THE ECHO:** A slender courier in a long charcoal coat with a pale lantern.",
                "",
                "### COMPLETE STORY",
                "",
                "**SCENE 01 — THE STAIRWELL (00:00-00:02)**",
                "",
                "The Echo climbs a broken stairwell. Rain threads through stained glass.",
                "",
                "Camera: Slow climb behind the courier.",
                "",
                "Sound: Faint rain and low drums.",
                "",
                "**SCENE 02 — THE LANDING (00:02-00:04)**",
                "",
                "The Echo steps onto the landing. The lantern flares and reveals a sealed door.",
                "",
                "Camera: Push-in on the lantern glow.",
                "",
                "Sound: One low toll of a distant bell.",
            ]
        ),
        encoding="utf-8",
    )
    output = tmp_path / "mini_out"
    config = AutonomousConfig(
        prompt_path=prompt,
        output_dir=output,
        provider="simulated",
        scene_seconds_override=2.0,
        with_narration=False,
        with_ambience=False,
        transition="fade",
        simulated_generation_seconds=0.1,
    )
    pipeline = AutonomousPipeline(config)
    result = await pipeline.run()

    assert result.final_path is not None and result.final_path.exists()
    assert result.plan.target_duration_seconds == 4
    assert validate_final(
        result.final_path,
        expected_scene_count=2,
        expected_width=1280,
        expected_height=720,
    )["passed"]
    probe = result.validation["metadata"]
    assert abs(float(probe["duration"]) - 4.0) < 3.0
    assert (output / "report.json").exists()
    assert (output / "plan.json").exists()
    assert (output / "narration_script.txt").exists()


async def test_scene_audio_composition(tmp_path: Path) -> None:
    """The ambient bed renders a track of the exact requested duration."""
    from agent.autonomous.soundstage import narration_duration

    destination = tmp_path / "track.wav"
    build_scene_audio(
        destination,
        scene_seconds=2.0,
        script_line="Deep subterranean rumble with restrained dark ambient music.",
        narration_path=None,
        with_ambience=True,
    )
    assert destination.exists() and destination.stat().st_size > 1024
    assert abs(narration_duration(destination) - 2.0) < 0.3


async def test_resume_reuses_generated_clips(tmp_path: Path) -> None:
    """A second run reuses valid existing scene clips instead of regenerating."""
    from agent.autonomous.runner import AutonomousConfig, AutonomousPipeline

    output = tmp_path / "resume_out"
    prompt = tmp_path / "three.md"
    prompt.write_text(
        "## TOWER FILM\n\n"
        "### COMPLETE STORY\n\n"
        + "**SCENE 01 — ONE (00:00-00:01)**\n\nA lone tower in the mist. A wanderer leans in. \n\nCamera: push in.\n\nSound: low drone.\n\n"
        + "**SCENE 02 — TWO (00:01-00:02)**\n\nThe wanderer walks on. \n\nCamera: pan.\n\nSound: footsteps.\n",
        encoding="utf-8",
    )
    config = AutonomousConfig(
        prompt_path=prompt,
        output_dir=output,
        provider="simulated",
        with_narration=False,
        with_ambience=False,
        transition="none",
        simulated_generation_seconds=0.05,
        scene_seconds_override=1.0,
    )
    pipeline = AutonomousPipeline(config)
    first = await pipeline.run()
    clips = sorted(output.glob("scenes/scene_*.mp4"))
    stamps = {clip.name: clip.stat().st_mtime for clip in clips}
    assert first.final_path and first.final_path.exists()

    pipeline2 = AutonomousPipeline(
        AutonomousConfig(
            prompt_path=prompt,
            output_dir=output,
            provider="simulated",
            with_narration=False,
            with_ambience=False,
            transition="none",
            simulated_generation_seconds=0.05,
            scene_seconds_override=1.0,
            resume=True,
        )
    )
    second = await pipeline2.run()
    stamps_after = {clip.name: clip.stat().st_mtime for clip in sorted(output.glob("scenes/scene_*.mp4"))}
    assert second.final_path and second.final_path.exists()
    assert stamps == stamps_after
