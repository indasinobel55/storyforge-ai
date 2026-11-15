from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent.providers.taaft import GEN_URL, TaaftProvider
from agent.validation.validator import validate_clip

import requests

WORK = Path("local_work/GOJO vs SUKUNA")

# Reference images in <Image n> order (explicit order matters for the labels)
REFERENCE_ORDER = [
    "images.jpg",                        # 1: Gojo face - white hair, blue eyes
    "il_fullxfull.8414176664_2d90.jpg",  # 2: Gojo costume - black high-collar uniform
    "images (1).jpg",                    # 3: Gojo live-action face, alternate
    "images (4).jpg",                    # 4: Sukuna in Megumi - photoreal, markings + Megumi uniform
    "images (3).jpg",                    # 5: Sukuna in Megumi - figure, markings/outfit detail
    "images (2).jpg",                    # 6: Sukuna markings, full-face cosplay
]

REFERENCE_PREFIX = """CHARACTER REFERENCE IMAGES (live-action design sheet):
<Image 1> shows SATORU GOJO portrayed by a real human actor: natural snow-white spiky hair, sharp pale-blue glowing eyes, dark high-collar collar detail.
<Image 2> shows Gojo's costume: fitted black high-collar under-layer with draped outer robe - replicate the fitted black high-collar uniform in the scene.
<Image 3> shows the same Gojo as a real human actor in live action - use it for realistic skin texture and facial structure.
<Image 4> shows RYOMEN SUKUNA inhabiting Megumi Fushiguro's body portrayed by a real human actor: Megumi's youthful face, messy spiky black hair, Sukuna's black facial markings, Megumi's dark high-collar uniform.
<Image 5> is a collectible figure - use it ONLY for Sukuna's exact facial markings and Megumi's outfit details, NOT its material, gloss or anime style.
<Image 6> shows Sukuna's black facial markings pattern across the cheeks, nose bridge and forehead.

STRICT reference rules: replicate the faces, hairstyles, facial markings and uniforms from these images with real human skin texture and natural proportions. Do NOT copy the poses, framing, backgrounds or photography style of the reference photos. In this scene Gojo's eyes stay covered by his black blindfold, and Sukuna wears Megumi's dark uniform. Do not turn anything anime - real live-action humans only. Everything else follows the direction below.

---

"""

PROMPT = """**DURATION: EXACTLY 8 SECONDS | PHOTOREALISTIC LIVE ACTION**

Create an ultra-realistic Hollywood-style live-action cinematic sequence recreating the iconic first face-off between Satoru Gojo and Ryomen Sukuna inhabiting Megumi Fushiguro's body, following their reunion after Gojo's unsealing.

**0-2 SECONDS - GOJO'S ARRIVAL**

A cinematic wide shot of a devastated Shinjuku street in Japan. Broken buildings, abandoned vehicles, cracked asphalt, floating dust and a gloomy overcast sky. Satoru Gojo stands facing Sukuna in the distance. He has realistic natural snow-white hair, a black blindfold, and his iconic fitted black high-collar uniform. His hands rest casually in his pockets. His body language communicates absolute confidence. The camera slowly moves toward him.

**2-4 SECONDS - SUKUNA REVEALED**

Cut to Sukuna inhabiting Megumi Fushiguro's body. He has Megumi's recognizable youthful facial structure, messy black hair, Sukuna's distinctive black facial markings, and an intimidating expression. He wears Megumi's dark uniform. His lips form a sinister, amused smile as he looks directly at Gojo. A subtle dark crimson supernatural glow reflects across his face.

**4-6 SECONDS - THE STARE DOWN**

A cinematic alternating close-up of both characters. Gojo slightly tilts his head, smiling confidently beneath his blindfold. Sukuna's expression becomes more menacing. Their eyes and facial movements feel completely natural and human. Wind blows through their hair and clothing. Dust swirls between them. The atmosphere is tense and eerily silent.

**6-8 SECONDS - NAH, I'D WIN**

Cut to a close-up of Gojo's face. He gives a relaxed, playful smile and casually says in a natural, confident male voice:

"Nah, I'd win."

His delivery is effortless, almost teasing, as though he has absolutely no doubt about the outcome. End on his confident expression.

**PHOTOREALISTIC VISUAL QUALITY:**

- Extreme photorealism, indistinguishable from high-budget Hollywood live-action cinematography.
- Real human skin texture, visible pores, realistic hair strands and natural facial expressions.
- Physically accurate lighting, realistic shadows and environmental reflections.
- IMAX-quality cinematic camera work.
- Real-world ruined Tokyo environment with practical-looking destruction.
- Subtle, realistic supernatural blue and crimson atmospheric effects.
- Natural human body proportions and believable costumes.
- Cinematic depth of field, anamorphic lens characteristics, subtle film grain and dramatic color grading.

**STRICT REQUIREMENTS:**

Absolutely NO anime appearance, NO illustration, NO cartoon rendering, NO cel shading, NO exaggerated facial proportions, NO artificial plastic-looking skin.

Both characters must look like real human actors portraying their live-action movie adaptations.

Gojo must retain his white hair, black blindfold and black uniform. Sukuna must remain inside Megumi's body, with black hair, facial markings and Megumi's clothing.

Do not start the fight. No punches, no attacks, no explosions. This scene is exclusively about their first face-to-face confrontation. Preserve the manga's original sequence and character positioning. Gojo must be blindfolded, and Sukuna must be inside Megumi's body, not his original Heian-era appearance. The dialogue must be spoken by Gojo, not Sukuna.
"""

FULL_PROMPT = REFERENCE_PREFIX + PROMPT


def load_jobs() -> dict[str, str]:
    path = WORK / "jobs.json"
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
    return {}


def save_job(job_id: str) -> None:
    (WORK / "jobs.json").write_text(json.dumps({"1": job_id}, indent=2), encoding="utf-8")


async def main() -> dict:
    WORK.mkdir(parents=True, exist_ok=True)
    (WORK / "prompt.md").write_text(FULL_PROMPT, encoding="utf-8")
    refs = [WORK / name for name in REFERENCE_ORDER]
    missing = [str(p) for p in refs if not p.exists()]
    if missing:
        raise FileNotFoundError(f"Missing reference images: {missing}")
    report: dict = {
        "started": time.time(),
        "title": "GOJO vs SUKUNA - Nah, I'd Win",
        "references": [p.name for p in refs],
        "scenes": [],
    }
    print(f"[scene 1/1] submitting to TAAFT (quality, landscape, {len(refs)} reference images)...", flush=True)

    provider = TaaftProvider(
        enabled=True,
        profile_dir=Path(".taaft_chrome_profile"),
        headless=False,
        poll_seconds=20,
        job_timeout_seconds=3600,
        tier="quality",
        orientation="landscape",
    )

    clip = WORK / "scene_01.mp4"
    final = None
    jobs = load_jobs()
    job_id = jobs.get("1")
    if job_id:
        print(f"[scene 1/1] adopting saved job {job_id}", flush=True)
        try:
            final = await provider.wait_for_generation(job_id)
        except Exception as error:
            print(f"[scene 1/1] saved job unusable ({error}); resubmitting", flush=True)
            job_id = None
    if final is None:
        result = await provider.submit_generation(
            prompt=FULL_PROMPT,
            tier="quality",
            orientation="landscape",
            duration=8.0,
            idempotency_key="gojo-vs-sukuna-refs-1",
            reference_image_path=refs,
        )
        job_id = result.generation_id
        save_job(job_id)
        print(f"[scene 1/1] job {job_id} ({result.status})", flush=True)
        final = await provider.wait_for_generation(job_id)

    if final.status not in {"succeeded", "success", "completed"} or not final.video_url:
        raise RuntimeError(f"Scene did not finish: {final.status} {final.error}")

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140 Safari/537.36",
        "Referer": GEN_URL,
    }
    response = requests.get(final.video_url, headers=headers, timeout=180)
    response.raise_for_status()
    clip.write_bytes(response.content)
    if clip.stat().st_size == 0:
        raise RuntimeError("Download was empty")
    validation = validate_clip(clip)
    report["scenes"].append({"job_id": job_id, "clip": str(clip), "clip_valid": validation["passed"]})
    print(f"[scene 1/1] downloaded {clip.name} valid={validation['passed']}", flush=True)

    if not validation["passed"]:
        raise RuntimeError(f"Clip failed validation: {validation}")

    from agent.postproduction.ffmpeg_tools import find_ffmpeg, run_ffmpeg

    native = validation["metadata"]
    upscale = WORK / "gojo_vs_sukuna_720p.mp4"
    run_ffmpeg(
        [
            find_ffmpeg(),
            "-y",
            "-i",
            str(clip),
            "-vf",
            "scale=1280:720:flags=lanczos,setsar=1",
            "-c:v",
            "libx264",
            "-preset",
            "slow",
            "-crf",
            "18",
            "-c:a",
            "aac",
            "-b:a",
            "160k",
            "-movflags",
            "+faststart",
            str(upscale),
        ]
    )
    upscale_validation = validate_clip(upscale)
    report["final"] = {
        "video": str(clip),
        "native_resolution": f"{native['width']}x{native['height']}",
        "upscaled_720p": str(upscale) if upscale_validation["passed"] else None,
        "upscale_valid": upscale_validation["passed"],
    }
    report["elapsed_seconds"] = round(time.time() - report["started"], 1)
    (WORK / "report.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report["final"], indent=2, default=str))
    return report


if __name__ == "__main__":
    asyncio.run(main())
