"""End-to-end automation for THE CHILD OF THE MONSOON - Episode 01.

Pipeline:
  1. Generate all 8 scenes (simulated provider, real MP4 via FFmpeg)
  2. 4x-enhance every scene with video2x (Real-ESRGAN, RTX 4060 / Vulkan)
  3. Assemble the enhanced scenes into the final episode video
  4. Delete excess intermediates (norm_*, concat.mp4, frames, cache, test files)

Run from anywhere:
    python scripts/run_monsoon_ep01_full.py

Options:
    --skip-generate      reuse existing scene_XX.mp4 files
    --skip-enhance       reuse existing enhanced/scene_XX_4x.mp4 files
    --keep-originals     keep the 1280x720 scene_XX.mp4 files after enhancing
    --scale N            upscale factor (default 4)
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORK = PROJECT_ROOT / "local_work" / "child_of_the_monsoon" / "ep01"
ENHANCED = WORK / "enhanced"
GEN_SCRIPT = PROJECT_ROOT / "scripts" / "run_child_of_the_monsoon_ep01.py"

# video2x install (complete build verified to run: DLLs + models present)
VIDEO2X_DIR = Path("C:/Program Files/video2x")
VIDEO2X_EXE = VIDEO2X_DIR / "video2x.exe"
REALESRGAN_MODEL = "realesr-animevideov3"  # fast model built for video
GPU_DEVICE = "0"  # NVIDIA RTX 4060 Laptop GPU

NUM_SCENES = 8


def log(msg: str) -> None:
    print(msg, flush=True)


def scene_path(i: int) -> Path:
    return WORK / f"scene_{i:02d}.mp4"


def enhanced_path(i: int, scale: int) -> Path:
    return ENHANCED / f"scene_{i:02d}_x{scale}.mp4"


def run(cmd: list[str], cwd: Path | None = None) -> None:
    """Run a command, streaming output, raising on failure."""
    log(f"$ {' '.join(cmd)}")
    proc = subprocess.run(cmd, cwd=str(cwd) if cwd else None)
    if proc.returncode != 0:
        raise SystemExit(f"Command failed (exit {proc.returncode}): {' '.join(cmd)}")


def video_is_valid(path: Path) -> bool:
    """True when ffprobe can read a duration from the file."""
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", str(path)],
            capture_output=True, text=True, timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return out.returncode == 0 and out.stdout.strip() not in {"", "N/A"}


# --------------------------------------------------------------------------- #
# 1. Generation
# --------------------------------------------------------------------------- #
def generate() -> None:
    log("\n=== [1/4] Generating 8 scenes ===")
    WORK.mkdir(parents=True, exist_ok=True)
    # Run generation from the project root so its relative WORK path resolves here.
    run([sys.executable, str(GEN_SCRIPT)], cwd=PROJECT_ROOT)
    missing = [i for i in range(1, NUM_SCENES + 1) if not scene_path(i).exists()]
    if missing:
        raise SystemExit(f"Generation did not produce scenes: {missing}")
    log(f"All {NUM_SCENES} scenes present.")


# --------------------------------------------------------------------------- #
# 2. 4x enhancement with video2x
# --------------------------------------------------------------------------- #
def enhance(scale: int) -> None:
    log(f"\n=== [2/4] Enhancing {NUM_SCENES} scenes {scale}x (Real-ESRGAN) ===")
    if not VIDEO2X_EXE.exists():
        raise SystemExit(f"video2x not found at {VIDEO2X_EXE}")
    ENHANCED.mkdir(parents=True, exist_ok=True)
    for i in range(1, NUM_SCENES + 1):
        src = scene_path(i)
        dst = enhanced_path(i, scale)
        if not src.exists():
            raise SystemExit(f"Missing source scene: {src}")
        if dst.exists() and dst.stat().st_size > 0:
            log(f"[scene {i}/8] enhanced clip exists, skipping")
            continue
        part = dst.with_suffix(".part.mp4")
        # A previous run may have crashed on teardown after writing valid output.
        if part.exists():
            if video_is_valid(part):
                part.replace(dst)
                log(f"[scene {i}/8] recovered valid partial -> {dst.name}")
                continue
            part.unlink()
        t0 = time.time()
        # video2x can segfault on teardown (exit 0xC0000005) after a fully valid
        # output has been written, so do not trust the exit code; verify the file.
        cmd = [
            str(VIDEO2X_EXE),
            "-i", str(src),
            "-o", str(part),
            "-s", str(scale),
            "-p", "realesrgan",
            "--realesrgan-model", REALESRGAN_MODEL,
            "-d", GPU_DEVICE,
        ]
        log(f"$ {' '.join(cmd)}")
        proc = subprocess.run(cmd, cwd=str(VIDEO2X_DIR))
        if not part.exists() or part.stat().st_size == 0:
            raise SystemExit(
                f"video2x produced no output for scene {i} (exit {proc.returncode})"
            )
        if not video_is_valid(part):
            raise SystemExit(
                f"video2x output for scene {i} is not a valid video (exit {proc.returncode})"
            )
        if proc.returncode != 0:
            log(f"[scene {i}/8] note: video2x exited {proc.returncode} after valid output (teardown crash, ignored)")
        part.replace(dst)
        log(f"[scene {i}/8] enhanced -> {dst.name} ({dst.stat().st_size/1e6:.1f} MB, {time.time()-t0:.0f}s)")


# --------------------------------------------------------------------------- #
# 3. Assemble enhanced scenes
# --------------------------------------------------------------------------- #
def assemble(scale: int) -> Path:
    log("\n=== [3/4] Assembling enhanced episode ===")
    final = WORK / f"child_of_the_monsoon_ep01_{scale}x.mp4"
    parts = [enhanced_path(i, scale) for i in range(1, NUM_SCENES + 1)]
    for p in parts:
        if not p.exists():
            raise SystemExit(f"Missing enhanced scene: {p}")

    concat_list = WORK / "_concat_list.txt"
    concat_list.write_text(
        "".join(f"file '{p.as_posix()}'\n" for p in parts), encoding="utf-8"
    )
    # All enhanced clips share codec/params, so stream-copy concat is safe and fast.
    run(
        [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", str(concat_list),
            "-c", "copy", "-movflags", "+faststart",
            str(final),
        ]
    )
    concat_list.unlink(missing_ok=True)
    if not final.exists() or final.stat().st_size == 0:
        raise SystemExit("Final assembly produced no output")
    log(f"Final enhanced video -> {final.name} ({final.stat().st_size/1e6:.1f} MB)")
    return final


# --------------------------------------------------------------------------- #
# 4. Cleanup
# --------------------------------------------------------------------------- #
def cleanup(keep_originals: bool) -> None:
    log("\n=== [4/4] Cleaning excess files ===")
    # Explicit intermediates produced by the generation + enhancement stages.
    patterns = [
        "norm_*.mp4",       # per-scene normalised intermediates
        "concat.mp4",       # assembled pre-enhancement video
        "frame_*.png",      # extracted continuity frames
        "segment_*.mp4",    # any segmented intermediates
        "*_test4x.mp4",     # ad-hoc test upscales
        "scene_*_4x.mp4",   # partial/aborted 4x outputs in the work root
        "*.part.mp4",       # aborted enhancement outputs
    ]
    removed: list[Path] = []
    for pattern in patterns:
        for f in WORK.glob(pattern):
            f.unlink()
            removed.append(f)
    # Provider cache directory (regenerable).
    cache = WORK / "provider_cache"
    if cache.exists():
        shutil.rmtree(cache)
        removed.append(cache)
    # Originals: drop unless the caller asked to keep them.
    if not keep_originals:
        for i in range(1, NUM_SCENES + 1):
            p = scene_path(i)
            if p.exists():
                p.unlink()
                removed.append(p)
    if removed:
        for f in removed:
            log(f"removed: {f.relative_to(PROJECT_ROOT)}")
    else:
        log("nothing to remove")


# --------------------------------------------------------------------------- #
def main() -> int:
    parser = argparse.ArgumentParser(description="Child of the Monsoon EP01 full pipeline")
    parser.add_argument("--skip-generate", action="store_true")
    parser.add_argument("--skip-enhance", action="store_true")
    parser.add_argument("--keep-originals", action="store_true")
    parser.add_argument("--scale", type=int, default=4)
    args = parser.parse_args()

    t0 = time.time()
    if not args.skip_generate:
        generate()
    else:
        log("[1/4] generation skipped")

    if not args.skip_enhance:
        enhance(args.scale)
    else:
        log("[2/4] enhancement skipped")

    final = assemble(args.scale)
    cleanup(args.keep_originals)

    log("\n=== DONE ===")
    log(f"Final video : {final}")
    log(f"Enhanced dir: {ENHANCED}")
    log(f"Elapsed     : {time.time() - t0:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
