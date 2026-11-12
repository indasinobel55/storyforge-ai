from __future__ import annotations

import json
import subprocess
import time
import uuid
from pathlib import Path

from agent.core.errors import DownloadError, GenerationError
from agent.core.util import write_json
from agent.postproduction.ffmpeg_tools import find_ffmpeg, run_ffmpeg
from agent.providers.base import GenerationResult, UsageInfo, VideoProvider


class SimulatedProvider(VideoProvider):
    """Deterministic local provider used for development and automated tests.

    It performs a real asynchronous lifecycle (submit -> processing -> ready),
    persists generation metadata, and renders actual MP4 clips with FFmpeg so the
    download, assembly and validation pipelines are exercised end to end.

    It never claims to be TAAFT. Output is clearly marked as simulated.
    """

    name = "simulated"
    display_name = "Simulated Provider"
    requires_consent = False

    def __init__(
        self,
        *,
        cache_dir: Path,
        generation_seconds: float = 1.5,
        clip_seconds: float = 2.0,
    ) -> None:
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.generation_seconds = max(0.0, float(generation_seconds))
        self.clip_seconds = max(1.0, float(clip_seconds))

    def _meta_path(self, generation_id: str) -> Path:
        safe = generation_id.replace("/", "_").replace("\\", "_")
        return self.cache_dir / f"{safe}.json"

    def _load(self, generation_id: str) -> dict:
        path = self._meta_path(generation_id)
        if not path.exists():
            raise GenerationError(f"Unknown simulated generation {generation_id}")
        return json.loads(path.read_text(encoding="utf-8"))

    async def verify_account(self) -> dict:
        return {"provider": self.name, "status": "connected", "simulated": True}

    async def get_usage(self) -> UsageInfo:
        return UsageInfo(credits_remaining=None, credits_total=None, plan="simulated", detail={"simulated": True})

    async def submit_generation(
        self,
        *,
        prompt: str,
        tier: str,
        orientation: str,
        duration: float,
        reference_image_path: Path | None = None,
        idempotency_key: str | None = None,
    ) -> GenerationResult:
        if not prompt or not prompt.strip():
            raise GenerationError("Prompt is empty")
        if idempotency_key:
            existing = await self.find_generation_by_idempotency(idempotency_key)
            if existing is not None:
                return existing
        generation_id = f"sim_{int(time.time() * 1000)}_{uuid.uuid4().hex[:10]}"
        width, height = {
            "portrait": (720, 1280),
            "square": (720, 720),
        }.get(orientation, (1280, 720))
        meta = {
            "generation_id": generation_id,
            "prompt": prompt,
            "tier": tier,
            "orientation": orientation,
            "duration": max(1.0, min(10.0, float(duration) if duration else self.clip_seconds)),
            "width": width,
            "height": height,
            "submitted_at": time.time(),
            "ready_at": time.time() + self.generation_seconds,
            "reference": str(reference_image_path) if reference_image_path else None,
            "fails": "[sim-fail]" in prompt.lower(),
            "idempotency_key": idempotency_key,
        }
        write_json(self._meta_path(generation_id), meta)
        return GenerationResult(
            generation_id=generation_id,
            status="processing",
            mode="simulated_t2v" if reference_image_path is None else "simulated_i2v",
            raw={"simulated": True},
        )

    async def get_generation_status(self, generation_id: str) -> GenerationResult:
        meta = self._load(generation_id)
        if meta.get("fails"):
            return GenerationResult(
                generation_id=generation_id,
                status="failed",
                error="Simulated provider failure requested by test marker",
                raw={"simulated": True},
            )
        if time.time() < float(meta.get("ready_at", 0)):
            return GenerationResult(
                generation_id=generation_id,
                status="processing",
                raw={
                    "simulated": True,
                    "queue_position": 0,
                    "eta_seconds": max(0, int(float(meta["ready_at"]) - time.time())),
                },
            )
        return GenerationResult(
            generation_id=generation_id,
            status="succeeded",
            video_url=f"simulated://{generation_id}",
            mode="simulated_t2v",
            raw={"simulated": True},
        )

    async def extend_generation(
        self,
        *,
        parent_generation_id: str,
        prompt: str,
        tier: str,
        orientation: str,
        duration: float,
        reference_image_path: Path | None = None,
    ) -> GenerationResult:
        parent = self._load(parent_generation_id)
        result = await self.submit_generation(
            prompt=prompt,
            tier=tier,
            orientation=orientation,
            duration=duration,
            reference_image_path=reference_image_path,
        )
        meta = self._load(result.generation_id)
        meta["parent_generation_id"] = parent_generation_id
        write_json(self._meta_path(result.generation_id), meta)
        result.parent_generation_id = parent_generation_id
        result.mode = "simulated_extend"
        return result

    async def find_generation_by_idempotency(self, idempotency_key: str) -> GenerationResult | None:
        for path in self.cache_dir.glob("sim_*.json"):
            try:
                meta = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if meta.get("idempotency_key") == idempotency_key:
                status = "succeeded" if time.time() >= float(meta.get("ready_at", 0)) else "processing"
                return GenerationResult(
                    generation_id=meta["generation_id"],
                    status=status,
                    video_url=f"simulated://{meta['generation_id']}" if status == "succeeded" else None,
                    mode="simulated_t2v",
                    raw={"simulated": True, "reconciled": True},
                )
        return None

    async def download_generation(self, generation: GenerationResult, destination: Path) -> Path:
        if generation.status not in {"succeeded", "success", "completed"}:
            raise DownloadError(f"Generation {generation.generation_id} is not ready")
        meta = self._load(generation.generation_id)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temp = destination.with_suffix(".render.mp4")
        width = int(meta["width"])
        height = int(meta["height"])
        duration = float(meta["duration"])
        ffmpeg = find_ffmpeg()
        run_ffmpeg(
            [
                ffmpeg,
                "-y",
                "-f",
                "lavfi",
                "-i",
                f"testsrc2=size={width}x{height}:rate=24:duration={duration}",
                "-f",
                "lavfi",
                "-i",
                f"sine=frequency=440:sample_rate=48000:duration={duration}",
                "-shortest",
                "-c:v",
                "libx264",
                "-preset",
                "ultrafast",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-b:a",
                "64k",
                "-metadata",
                "comment=Simulated provider output (not TAAFT)",
                "-metadata",
                f"title={generation.generation_id}",
                str(temp),
            ]
        )
        if not temp.exists() or temp.stat().st_size == 0:
            raise DownloadError("Simulated render produced an empty file")
        temp.replace(destination)
        return destination
