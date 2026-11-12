from __future__ import annotations

import hashlib
from pathlib import Path

from agent.core.errors import ValidationError
from agent.core.util import probe_video


def _check(name: str, passed: bool, detail: str = "") -> dict:
    return {"name": name, "passed": bool(passed), "detail": detail}


def validate_clip(path: Path) -> dict:
    checks: list[dict] = []
    checks.append(_check("file_exists", path.exists(), str(path)))
    if not path.exists():
        return {"passed": False, "checks": checks, "metadata": {}}
    size = path.stat().st_size
    checks.append(_check("file_size", size > 1024, f"{size} bytes"))
    try:
        probe = probe_video(path)
        checks.append(_check("decodable", True, f"codec={probe.get('codec')}"))
        checks.append(_check("video_stream", bool(probe.get("width") and probe.get("height")), str(probe)))
        checks.append(_check("duration", float(probe.get("duration") or 0) > 0.25, f"{probe.get('duration')}s"))
        checks.append(_check("resolution", int(probe.get("width") or 0) >= 320, f"{probe.get('width')}x{probe.get('height')}"))
    except Exception as error:  # noqa: BLE001
        checks.append(_check("decodable", False, str(error)))
        probe = {}
    return {"passed": all(item["passed"] for item in checks), "checks": checks, "metadata": probe}


def validate_final(
    path: Path,
    *,
    expected_scene_count: int,
    expected_duration: float | None = None,
    expected_width: int | None = None,
    expected_height: int | None = None,
    thumbnail_path: Path | None = None,
) -> dict:
    checks: list[dict] = []
    metadata: dict = {}

    exists = path.exists()
    checks.append(_check("file_exists", exists, str(path)))
    if not exists:
        return {"passed": False, "checks": checks, "metadata": metadata, "errors": ["Output file is missing"]}

    size = path.stat().st_size
    checks.append(_check("file_size", size > 10_000, f"{size} bytes"))

    readable = True
    try:
        with path.open("rb") as handle:
            handle.read(1024)
    except OSError as error:
        readable = False
        checks.append(_check("readable", False, str(error)))
    if readable:
        checks.append(_check("readable", True))

    try:
        metadata = probe_video(path)
        checks.append(_check("decodable", True, f"codec={metadata.get('codec')}"))
        checks.append(_check("video_stream", bool(metadata.get("width") and metadata.get("height")), "present"))
        checks.append(
            _check("resolution_valid", int(metadata.get("width") or 0) >= 320 and int(metadata.get("height") or 0) >= 240, f"{metadata.get('width')}x{metadata.get('height')}")
        )
        if expected_width and expected_height:
            checks.append(
                _check(
                    "expected_resolution",
                    int(metadata.get("width") or 0) == expected_width
                    and int(metadata.get("height") or 0) == expected_height,
                    f"expected {expected_width}x{expected_height}, got {metadata.get('width')}x{metadata.get('height')}",
                )
            )
        duration = float(metadata.get("duration") or 0)
        checks.append(_check("duration_positive", duration > 0.5, f"{duration}s"))
        if expected_duration:
            lower = expected_duration * 0.65
            upper = expected_duration * 1.6 + 2
            checks.append(
                _check(
                    "duration_within_range",
                    lower <= duration <= upper,
                    f"expected ~{expected_duration:.1f}s, got {duration:.2f}s",
                )
            )
        checks.append(_check("scene_count_declared", expected_scene_count >= 1, str(expected_scene_count)))
        checks.append(
            _check(
                "audio_reported",
                True,
                "audio stream present" if metadata.get("has_audio") else "no audio stream",
            )
        )
    except Exception as error:  # noqa: BLE001
        checks.append(_check("decodable", False, str(error)))

    if thumbnail_path is not None:
        checks.append(_check("thumbnail", thumbnail_path.exists() and thumbnail_path.stat().st_size > 0, str(thumbnail_path)))

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)

    errors = [item["detail"] for item in checks if not item["passed"]]
    return {
        "passed": not errors,
        "checks": checks,
        "metadata": metadata,
        "checksum_sha256": digest.hexdigest(),
        "size_bytes": size,
        "errors": errors,
    }


def assert_valid(path: Path, **kwargs) -> dict:
    report = validate_final(path, **kwargs)
    if not report["passed"]:
        raise ValidationError("Final video validation failed: " + "; ".join(report.get("errors") or []))
    return report
