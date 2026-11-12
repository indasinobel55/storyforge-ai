"""Offline narration synthesis and per-scene sound design.

Narration: Windows SAPI (System.Speech) text-to-speech via PowerShell — no
network calls, no extra dependencies. Each scene's narration is synthesized
once, measured, then tempo-corrected with FFmpeg ``atempo`` so it always fits
inside the scene duration.

Ambient bed: procedural "dark ambient" drone built with FFmpeg ``lavfi``
sources (low sine drones + filtered brown noise), with an optional heartbeat
style tremolo pulse when the master prompt's sound design calls for one.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from agent.core.util import probe_video
from agent.postproduction.ffmpeg_tools import find_ffmpeg, run_ffmpeg


def _ps_quote(value: str) -> str:
    return value.replace("'", "''")


def _sapi_available() -> bool:
    if not shutil.which("powershell"):
        return False
    probe = (
        "Add-Type -AssemblyName System.Speech;"
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer;"
        "$voices = $s.GetInstalledVoices();"
        "if ($voices.Count -gt 0) { exit 0 } else { exit 2 };"
        "$s.Dispose();"
    )
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", probe],
            capture_output=True,
            timeout=30,
        )
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def synthesize_speech(
    text: str,
    destination: Path,
    *,
    rate: int = 1,
    voice: str | None = None,
) -> Path:
    """Render narration text to a WAV file using Windows SAPI TTS."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg = find_ffmpeg()
    with tempfile.TemporaryDirectory(prefix="narration_") as tmp:
        work = Path(tmp)
        source_wav = work / "speech.wav"
        text_file = work / "speech.txt"
        text_file.write_text(text, encoding="utf-8-sig")
        script = (
            "Add-Type -AssemblyName System.Speech;"
            "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer;"
            f"$s.Rate = {max(-10, min(10, int(rate)))};"
            + (f"$s.SelectVoice('{_ps_quote(voice)}');" if voice else "")
            + f"$text = Get-Content -Raw -Encoding UTF8 '{_ps_quote(str(text_file))}';"
            + f"$s.SetOutputToWaveFile('{_ps_quote(str(source_wav))}');"
            + "$s.Speak($text);"
            + "$s.Dispose();"
        )
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            timeout=180,
        )
        if result.returncode != 0 or not source_wav.exists() or source_wav.stat().st_size == 0:
            detail = (result.stderr or b"").decode("utf-8", "replace")[-400:]
            raise RuntimeError(f"SAPI speech synthesis failed: {detail}")
        # Normalize to 48 kHz stereo the same way every later stage expects.
        run_ffmpeg(
            [
                ffmpeg,
                "-y",
                "-i",
                str(source_wav),
                "-ar",
                "48000",
                "-ac",
                "2",
                str(destination),
            ]
        )
    if not destination.exists() or destination.stat().st_size == 0:
        raise RuntimeError("Narration render produced an empty file")
    return destination


def narration_duration(narration_path: Path) -> float:
    import av

    with av.open(str(narration_path)) as container:
        if container.duration is None:
            return 0.0
        return max(0.0, float(container.duration / av.time_base))


def _intensity_from_sound_design(sound: str) -> float:
    text = (sound or "").lower()
    if any(word in text for word in ("silence", "inaudible", "suppressed", "nearly complete", "mute")):
        return 0.3
    if any(word in text for word in ("rumble", "deep", "impact", "distorted")):
        return 1.0
    return 0.6


def _wants_pulse(sound: str) -> bool:
    text = (sound or "").lower()
    return any(word in text for word in ("heartbeat", "pulse", "pulses"))


def build_scene_audio(
    destination: Path,
    *,
    scene_seconds: float,
    script_line: str,
    narration_path: Path | None = None,
    narration_seconds: float = 0.0,
    lead_in: float = 0.8,
    tail: float = 0.6,
    with_narration: bool = True,
    with_ambience: bool = True,
) -> Path:
    """Compose one scene's audio track: ambient drone plus tempo-fitted narration.

    The resulting file is exactly ``scene_seconds`` long, ready to mux over the
    scene clip with its video stream untouched.
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg = find_ffmpeg()
    duration = f"{max(1.0, float(scene_seconds)):.3f}"

    command: list[str] = [ffmpeg, "-y"]
    inputs: list[str] = []
    filter_parts: list[str] = []

    if narration_path and narration_path.exists() and with_narration:
        command += ["-i", str(narration_path)]
        narration_index = len(inputs)
        inputs.append(str(narration_path))
        budget = max(1.0, float(scene_seconds) - lead_in - tail)
        tempo = 1.0
        if narration_seconds > 0:
            tempo = min(2.4, max(0.7, float(narration_seconds) / budget))
        delay_ms = int(max(0.0, lead_in) * 1000)
        filter_parts.append(
            f"[{narration_index}:a]aresample=48000,aformat=channel_layouts=stereo,"
            f"atempo={tempo:.4f},volume=2.1,adelay={delay_ms}|{delay_ms},apad[n]"
        )

    if with_ambience:
        intensity = _intensity_from_sound_design(script_line)
        command += [
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=55:sample_rate=48000:duration={duration}",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=110.5:sample_rate=48000:duration={duration}",
            "-f",
            "lavfi",
            "-i",
            f"anoisesrc=color=brown:sample_rate=48000:duration={duration}:amplitude=0.34",
        ]
        drone_index = len(inputs)
        tone_index = drone_index + 1
        noise_index = drone_index + 2
        inputs += ["lavfi:drone", "lavfi:tone", "lavfi:noise"]
        if _wants_pulse(script_line):
            filter_parts.append(
                f"[{drone_index}:a]tremolo=f=0.85:d=0.85,aresample=48000,aformat=channel_layouts=stereo[d0]"
            )
            drone_ref = "d0"
        else:
            filter_parts.append(f"[{drone_index}:a]aresample=48000,aformat=channel_layouts=stereo[d0]")
            drone_ref = "d0"
        filter_parts.append(f"[{tone_index}:a]aresample=48000,aformat=channel_layouts=stereo,volume=0.5[t0]")
        filter_parts.append(f"[{noise_index}:a]lowpass=f=260,volume=0.8,aformat=channel_layouts=stereo[nz]")
        ambience_gain = 0.42 * intensity
        filter_parts.append(f"[d0]volume={0.55 * intensity:.3f}[dw]")
        filter_parts.append(f"[dw][t0][nz]amix=inputs=3:duration=first:dropout_transition=0,volume={ambience_gain:.3f},apad[amb]")

    if narration_path and narration_path.exists() and with_narration and with_ambience:
        filter_parts.append(
            "[amb][n]amix=inputs=2:duration=longest:dropout_transition=0,volume=1.6,"
            "atrim=0:" + duration + ",asetpts=PTS-STARTPTS[aout]"
        )
    elif narration_path and narration_path.exists() and with_narration:
        filter_parts.append("[n]atrim=0:" + duration + ",asetpts=PTS-STARTPTS[aout]")
    else:
        filter_parts.append("[amb]atrim=0:" + duration + ",asetpts=PTS-STARTPTS[aout]")

    command += ["-filter_complex", ";".join(filter_parts), "-map", "[aout]"]
    command += [
        "-t",
        duration,
        "-c:a",
        "pcm_s16le",
        "-ar",
        "48000",
        str(destination),
    ]
    run_ffmpeg(command, timeout=300)
    if not destination.exists() or destination.stat().st_size == 0:
        raise RuntimeError("Scene audio composition produced an empty file")
    return destination


def mux_audio_onto_clip(
    clip: Path,
    audio: Path,
    destination: Path,
    *,
    keep_clip_audio: bool = False,
) -> Path:
    """Replace (or blend with) the clip's audio stream, keeping video bytes copyable."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg = find_ffmpeg()
    if keep_clip_audio:
        probe = probe_video(clip)
        if probe.get("has_audio"):
            command = [
                ffmpeg,
                "-y",
                "-i",
                str(clip),
                "-i",
                str(audio),
                "-filter_complex",
                "[0:a]volume=0.35[base];[1:a]volume=1.0[vo];[base][vo]amix=inputs=2:duration=first:dropout_transition=0[aout]",
                "-map",
                "0:v",
                "-map",
                "[aout]",
                "-c:v",
                "copy",
                "-c:a",
                "aac",
                "-b:a",
                "160k",
                "-shortest",
                str(destination),
            ]
        else:
            command = [ffmpeg, "-y", "-i", str(clip), "-i", str(audio), "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", str(destination)]
    else:
        command = [
            ffmpeg,
            "-y",
            "-i",
            str(clip),
            "-i",
            str(audio),
            "-map",
            "0:v",
            "-map",
            "1:a",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "160k",
            "-movflags",
            "+faststart",
            str(destination),
        ]
    run_ffmpeg(command, timeout=300)
    if not destination.exists() or destination.stat().st_size == 0:
        raise RuntimeError("Audio mux produced an empty file")
    return destination
