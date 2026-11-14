from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

from agent.core.errors import ProviderDisabledError, ProviderError

DEFAULT_BASE_URL = "http://127.0.0.1:17494"
DEFAULT_MODEL = "audiocpp-stable-audio-3-sfx"
MUSIC_MODEL = "audiocpp-ace-step"
DEFAULT_TIMEOUT = 900
TERMINAL_OK = {"done"}
TERMINAL_FAIL = {"error", "cancelled"}


def soundbox_enabled() -> bool:
    return os.environ.get("SOUNDBOX_ENABLED", "0") == "1"


def _base_url() -> str:
    return os.environ.get("SOUNDBOX_API_URL", DEFAULT_BASE_URL).rstrip("/")


def _request(method: str, path: str, payload: dict | None = None) -> dict:
    url = f"{_base_url()}{path}"
    headers = {"X-Soundbox": "storyforge"}
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            body = response.read()
    except urllib.error.URLError as exc:
        raise ProviderError(f"Soundbox API unreachable at {url}: {exc}") from exc
    if not body:
        return {}
    return json.loads(body)


def health() -> dict:
    return _request("GET", "/api/health")


def generate_clip(
    prompt: str,
    output_path: Path,
    *,
    model: str | None = None,
    duration_s: float | None = None,
    seed: int | None = None,
    negative_prompt: str | None = None,
    tags: list[str] | None = None,
    poll_seconds: float = 2.0,
) -> Path:
    """Generate a sound effect, ambience or music clip via the local Soundbox API."""
    if not soundbox_enabled():
        raise ProviderDisabledError("Soundbox is disabled (SOUNDBOX_ENABLED=0)")
    if not prompt.strip():
        raise ProviderError("Soundbox prompt is empty")
    body: dict = {
        "model": model or os.environ.get("SOUNDBOX_MODEL", DEFAULT_MODEL),
        "prompt": prompt,
    }
    if duration_s is not None:
        body["duration_s"] = duration_s
    if seed is not None:
        body["seed"] = seed
    if negative_prompt:
        body["negative_prompt"] = negative_prompt
    if tags:
        body["tags"] = tags
    start = _request("POST", "/api/generate", body)
    job_id = start.get("job_id")
    if not job_id:
        raise ProviderError(f"Soundbox did not return a job id: {start}")
    deadline = time.monotonic() + DEFAULT_TIMEOUT
    while time.monotonic() < deadline:
        job = _request("GET", f"/api/jobs/{job_id}")
        status = job.get("status")
        if status in TERMINAL_FAIL:
            raise ProviderError(f"Soundbox job failed: {job.get('error') or job}")
        if status in TERMINAL_OK:
            sounds = ((job.get("result") or {}).get("sounds") or [])
            if not sounds:
                raise ProviderError(f"Soundbox job finished without sounds: {job}")
            return _download_file(sounds[0], output_path)
        time.sleep(poll_seconds)
    raise ProviderError(f"Soundbox job {job_id} timed out")


def _download_file(sound_id: str, output_path: Path) -> Path:
    url = f"{_base_url()}/files/{sound_id}.wav"
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with urllib.request.urlopen(url, timeout=DEFAULT_TIMEOUT) as response, output_path.open("wb") as handle:
            while True:
                chunk = response.read(1 << 20)
                if not chunk:
                    break
                handle.write(chunk)
    except urllib.error.URLError as exc:
        raise ProviderError(f"Could not download Soundbox file {url}: {exc}") from exc
    return output_path


def generate_cue(
    prompt: str,
    output_path: Path,
    *,
    kind: str = "ambience",
    duration_s: float | None = None,
    seed: int | None = None,
    tags: list[str] | None = None,
) -> Path:
    """Generate one audio cue, using the music model for melodic kinds with
    fallback to the SFX model if that fails."""
    model = MUSIC_MODEL if kind == "music" else os.environ.get("SOUNDBOX_MODEL", DEFAULT_MODEL)
    try:
        return generate_clip(
            prompt,
            output_path,
            model=model,
            duration_s=duration_s,
            seed=seed,
            tags=tags,
        )
    except ProviderError:
        if model == MUSIC_MODEL:
            return generate_clip(
                prompt,
                output_path,
                model=os.environ.get("SOUNDBOX_MODEL", DEFAULT_MODEL),
                duration_s=duration_s,
                seed=seed,
                tags=tags,
            )
        raise
