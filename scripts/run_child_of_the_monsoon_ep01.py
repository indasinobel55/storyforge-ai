from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

os.environ.setdefault("SOUNDBOX_ENABLED", "1")

import requests

from agent.postproduction import soundbox
from agent.postproduction.assemble import assemble_clips
from agent.providers.simulated import SimulatedProvider
from agent.scenes.spec import ScenePlan, SceneSpec
from agent.validation.validator import assert_valid, validate_clip

WORK = Path("local_work/child_of_the_monsoon/ep01")
PLAN_PATH = Path("stories/child_of_the_monsoon/ep01/plan.json")

STYLE_HEADER = (
    "STYLE (every shot): cinematic realistic 3D animation with high-end theatrical rendered "
    "feature-film quality - stylized but physically plausible characters, realistic fur/water/foliage "
    "simulation, physically based materials, volumetric lighting, rich emerald Amazon palette, "
    "cinematic depth of field, subtle film grain, professional color grading. NOT live action, "
    "NOT 2D anime, NOT cel shaded. Exactly 8 seconds, no text, no subtitles, no captions, "
    "no logos, no watermarks.\n\n"
)

CONTINUITY_HEADER = (
    "CONTINUITY (mandatory): this shot continues the same 3D-animated film. Keep the SAME characters "
    "with identical facial features, hair, skin tones and clothing; the SAME small motorized expedition "
    "boat; the SAME Amazon river and rainforest geography; consistent weather progression; consistent "
    "3D rendering, color grading and lighting direction as the reference frame. Camera moves must be "
    "physically coherent with no random jumps.\n\n"
)

AMBIENCE_PROMPT = (
    "amazon rainforest ambience, tropical birds and insects, rain arriving with distant thunder, "
    "river flowing, wind through dense canopy, cinematic adventure atmosphere, seamless loop"
)

# (title, camera_note, prompt) - prompts preserved from the episode spec
SCENES: list[tuple[str, str, str]] = [
    (
        "The Lost Expedition",
        "FPV Drone Tree-Weaving + Crane Reveal",
        """Create an 8-second cinematic opening shot of an enormous, unexplored Amazon rainforest. Begin high above an endless sea of dense emerald-green treetops beneath a dramatic cloudy sky. An FPV-style camera accelerates forward, weaving smoothly between enormous rainforest trees, passing close to wet leaves and hanging vines. The camera gradually descends through layers of vegetation, revealing a wide, winding Amazon river hidden beneath the canopy. As the camera clears the final trees, reveal a small motorized expedition boat carrying several human researchers along the river.

The boat should appear tiny compared with the enormous wilderness surrounding it. Water should display realistic reflections, ripples and gentle wake patterns. Morning mist floats above the river, while shafts of sunlight penetrate the thick canopy.

Camera: Extremely smooth, high-speed FPV flight transitioning into a breathtaking wide cinematic crane reveal. Natural motion blur, realistic depth of field, professional aerial cinematography.

Audio: Deep atmospheric orchestral opening, tropical birds, distant insects, rushing wind and subtle river sounds.

Ending: Camera settles behind and above the expedition boat as it travels deeper into the rainforest.""",
    ),
    (
        "Into the Unknown",
        "Low Waterline Tracking + 180 Degree Orbit",
        """Create an 8-second cinematic sequence following the same expedition boat deeper into the Amazon rainforest. The boat carries a small research team consisting of two adult explorers, a female researcher and the family's youngest member - a small, curious little explorer in a bright yellow outfit travelling with them. The little explorer sits safely beside the adults, curiously watching the mysterious jungle.

Begin with a low waterline tracking shot beside the moving boat. The camera glides inches above the river surface, capturing realistic splashes and reflections. Gradually rise toward the boat's interior and perform a smooth 180-degree orbit around the passengers, revealing their faces and the enormous rainforest walls surrounding them.

The little explorer looks fascinated by the wildlife. A group of colorful macaws suddenly flies across the river ahead. The researchers exchange curious looks.

Camera: Fluid waterline tracking, cinematic orbit, natural perspective changes, realistic handheld micro-movements.

Lighting: Soft overcast daylight, rich natural greens, realistic skin tones, subtle reflections.

Audio: Boat engine, splashing water, bird calls, distant monkey cries and subtle adventurous orchestral music.

Ending: The camera focuses on the little explorer's fascinated face as a distant rumble of thunder interrupts the peaceful atmosphere.""",
    ),
    (
        "The Approaching Storm",
        "360 Degree Environmental Orbit + Tilt-Up",
        """Create an 8-second dramatic cinematic storm sequence. The peaceful Amazon rainforest suddenly transforms as enormous dark storm clouds gather above the canopy. Begin with an extreme close-up of raindrops falling onto the river surface. The camera rapidly pulls backward while rotating around the expedition boat, revealing the surrounding rainforest disappearing beneath thick grey storm clouds.

Strong winds begin shaking the trees. Palm leaves and loose branches move violently. Birds scatter from the canopy. The river becomes increasingly turbulent. The researchers look upward in alarm as the first heavy rain strikes the boat.

A sudden lightning flash illuminates the entire rainforest, revealing enormous tree silhouettes in the distance.

Camera: Start with macro water detail, transition into a dramatic 360-degree environmental orbit, followed by a fast upward tilt toward the threatening sky.

Visual effects: Physically realistic rainfall, volumetric storm clouds, lightning illumination, atmospheric mist, wind-driven vegetation and detailed water simulation.

Audio: Deep thunder, accelerating wind, heavy rain, frightened bird calls and rising orchestral tension.

Ending: A massive lightning strike flashes near the riverbank.""",
    ),
    (
        "The Incident",
        "Whip-Pan + Dynamic Tracking",
        """Create an intense 8-second cinematic disaster sequence. A powerful storm hits the expedition boat as a large fallen tree suddenly crashes into the river ahead. The boat operator desperately turns the steering wheel, but violent waves push the vessel sideways.

Begin with a close-up of the operator struggling with the controls. Perform a sudden whip-pan toward the enormous fallen tree. Immediately cut into a fast dynamic tracking shot following the boat as it collides with floating debris and violently rocks sideways.

Water crashes over the sides of the boat. Equipment falls across the deck. The researchers desperately grab the railings to avoid falling. The female researcher instinctively reaches toward the little explorer.

A powerful wave engulfs the camera lens, briefly obscuring the entire image.

Camera: Aggressive whip-pan, fast lateral tracking, controlled cinematic shake, dramatic close-ups and realistic impact timing.

Visuals: Physically realistic water deformation, flying debris, wet clothing, dynamic rain, convincing boat movement and detailed environmental destruction.

Audio: Violent thunder, crashing water, engine failure, metal impacts, frightened shouting and a dramatic orchestral impact.

Ending: The camera is momentarily submerged beneath dark, turbulent river water.""",
    ),
    (
        "The Empty Seat",
        "Underwater-to-Surface Reveal + Slow Push-In",
        """Create an emotionally intense 8-second cinematic sequence immediately following the boat accident. Begin underwater, showing bubbles, floating leaves and small pieces of broken equipment drifting through murky river water. The camera rises slowly through the water surface, revealing the damaged expedition boat stranded against a muddy riverbank.

Rain continues falling heavily.

One researcher struggles onto the riverbank while the female researcher desperately searches the boat. She looks through scattered equipment, overturned seats and broken supplies.

Suddenly, she notices the little explorer's empty seat.

Her expression changes from confusion to absolute terror. She turns toward the others and screams that the littlest member is missing.

Camera: Smooth underwater ascent, water-surface transition, slow cinematic push-in toward the empty seat, followed by an emotional close-up of the female researcher's face.

Visuals: Realistic water droplets on the lens, soaked clothing, muddy textures, detailed facial expressions and atmospheric rain.

Audio: Muffled underwater ambience transitioning into loud rainfall, coughing, frantic footsteps and the researcher's desperate scream.

Ending: Extreme close-up of the empty little seat.""",
    ),
    (
        "The Search Begins",
        "Handheld Jungle Tracking Shot",
        """Create an 8-second suspenseful cinematic jungle search sequence. The expedition survivors enter the dense rainforest searching desperately for their missing littlest member. Two adult explorers move through thick wet vegetation carrying flashlights and calling out for them.

Begin with a handheld tracking shot following them from behind as they push through hanging vines, enormous leaves and muddy vegetation. The camera moves naturally with their footsteps, occasionally passing close to wet foliage in the foreground.

One explorer suddenly stops after noticing something on the muddy ground. He raises his flashlight and bends down to investigate.

The camera slowly moves over his shoulder toward the ground.

Camera: Immersive handheld tracking, low-angle movement through vegetation, controlled camera shake and gradual over-the-shoulder reveal.

Visuals: Dense Amazon vegetation, wet leaves, muddy ground, atmospheric mist, flashlight beams cutting through the darkness and realistic rainwater.

Audio: Heavy breathing, wet footsteps, insects, distant animal calls, flashlight clicks and tense cinematic strings.

Ending: A small footprint becomes visible in the mud.""",
    ),
    (
        "Footprints in the Jungle",
        "Macro Tracking + Parallax Reveal",
        """Create an 8-second mysterious cinematic sequence focused on a trail of tiny barefoot footprints pressed into the wet rainforest mud.

Begin with an extreme macro shot of one tiny footprint. Rain droplets slowly fall into it, creating small ripples in the muddy water. The camera tracks forward along several footprints leading deeper into the rainforest.

The camera rises gradually from ground level, revealing enormous ancient trees, twisted roots and dense vegetation surrounding the trail.

As the camera passes between two massive tree trunks, a mysterious black jaguar silhouette briefly appears deep in the background, watching silently.

Do not reveal the animal completely. Only show its shadowy outline and a subtle movement between the leaves.

Camera: Extreme macro push-in, smooth ground-level tracking, cinematic parallax reveal and gradual upward camera movement.

Lighting: Moody blue-green rainforest atmosphere, soft shafts of natural light and subtle highlights on wet vegetation.

Audio: Individual raindrops, distant thunder, subtle animal breathing and a slowly intensifying mysterious musical theme.

Ending: The distant silhouette disappears into the darkness.""",
    ),
    (
        "The Jungle's Secret",
        "Epic Crane Reveal + Emotional Close-Up",
        """Create an unforgettable 8-second cinematic ending revealing the missing little explorer deep inside the Amazon rainforest.

Begin with a slow camera movement through enormous ancient tree roots covered in moss, rainwater and delicate tropical plants. As the camera passes through the roots, reveal the missing littlest expedition member resting safely in a small natural hollow formed between the roots.

Small in stature, wearing the same soaked yellow outfit seen earlier aboard the expedition boat. Frightened but unharmed.

A large, beautiful black jaguar stands several feet away, partially hidden behind the vegetation. It watches the little one quietly without showing aggression.

The little one slowly opens their eyes and looks toward the animal.

The jaguar gently lowers its head, observing the little one.

A soft golden beam of sunlight breaks through the rainforest canopy and illuminates the little one's face while rain continues falling in the surrounding jungle.

Camera: Begin with a slow cinematic push through foreground roots, transition into a gentle rising crane reveal, then finish with an intimate close-up of the little one's eyes and the jaguar's silhouette in the background.

Visuals: Ultra-detailed realistic 3D character animation, natural facial expressions, realistic jaguar fur and anatomy, physically accurate rain, wet moss, volumetric sunlight and extraordinary rainforest detail.

Audio: Rain gradually softens, subtle birdsong returns, gentle orchestral strings rise and a deep mysterious musical note closes the scene.

Final frame: The little one's eyes meet the jaguar's eyes.""",
    ),
]

NEGATIVE_PROMPT = (
    "text, subtitles, captions, logos, watermarks, credits, live action photography, "
    "cartoon outlines, cel shading, low-poly, plastic skin, distorted anatomy, extra limbs, "
    "flickering, jittery camera"
)


def fmt_scene_prompt(index: int, prompt: str, camera_note: str) -> str:
    parts = [STYLE_HEADER]
    if index > 1:
        parts.append(CONTINUITY_HEADER)
    parts.append(f"SCENE {index} of 8 - MONSOON EXPEDITION FILM, EPISODE 01 (camera plan: {camera_note})\n\n")
    parts.append(prompt)
    return "".join(parts)


def load_jobs() -> dict[str, str]:
    path = WORK / "jobs.json"
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
    return {}


def save_job(scene_number: int, job_id: str) -> None:
    jobs = load_jobs()
    jobs[str(scene_number)] = job_id
    (WORK / "jobs.json").write_text(json.dumps(jobs, indent=2), encoding="utf-8")


def extract_last_frame(clip: Path, image: Path) -> Path:
    from agent.postproduction.ffmpeg_tools import find_ffmpeg, run_ffmpeg

    image.parent.mkdir(parents=True, exist_ok=True)
    run_ffmpeg(
        [find_ffmpeg(), "-y", "-sseof", "-0.5", "-i", str(clip), "-frames:v", "1", "-update", "1", str(image)]
    )
    if not image.exists() or image.stat().st_size == 0:
        raise RuntimeError(f"Last frame extraction failed: {clip}")
    return image


def start_soundbox() -> bool:
    try:
        soundbox.health()
        return True
    except Exception:
        pass
    exe = Path(os.environ.get("LOCALAPPDATA", "")) / "Soundbox" / "soundbox-desktop.exe"
    if not exe.exists():
        return False
    subprocess.Popen([str(exe)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(6):
        time.sleep(3)
        try:
            soundbox.health()
            return True
        except Exception:
            continue
    return False


def make_ambience(report: dict) -> Path | None:
    if not start_soundbox():
        report["soundbox"] = {"available": False}
        print("[soundbox] app not reachable, skipping ambience", flush=True)
        return None
    report["soundbox"] = {"available": True}
    try:
        out = soundbox.generate_clip(AMBIENCE_PROMPT, WORK / "ambience.wav", duration_s=10.0)
        report["soundbox"]["generated"] = str(out)
        print(f"[soundbox] ambience -> {out.name}", flush=True)
        return out
    except Exception as error:
        report["soundbox"]["error"] = str(error)[:300]
        print(f"[soundbox] generation skipped: {error}", flush=True)
        return None


async def generate_scene(
    provider: SimulatedProvider,
    index: int,
    prompt: str,
    prev_job: str | None,
    prev_clip: Path | None,
    report: dict,
) -> tuple[str, Path]:
    clip = WORK / f"scene_{index:02d}.mp4"
    if clip.exists() and validate_clip(clip)["passed"]:
        print(f"[scene {index}/8] clip exists, skipping", flush=True)
        report["scenes"].append({"scene": index, "clip": str(clip), "resumed": True})
        jobs = load_jobs()
        return jobs.get(str(index), ""), clip

    reference: Path | None = None
    if prev_clip is not None and prev_clip.exists():
        reference = extract_last_frame(prev_clip, WORK / f"frame_{index - 1:02d}.png")

    jobs = load_jobs()
    job_id = jobs.get(str(index))
    final = None
    if job_id:
        print(f"[scene {index}/8] adopting saved job {job_id}", flush=True)
        try:
            final = await provider.get_generation_status(job_id)
            # Poll until completed
            while final.status not in {"succeeded", "success", "completed"} and not final.error:
                await asyncio.sleep(5)
                final = await provider.get_generation_status(job_id)
        except Exception as error:
            print(f"[scene {index}/8] saved job unusable ({error}); resubmitting", flush=True)
            job_id = None

    if final is None and index > 1 and prev_job:
        try:
            print(f"[scene {index}/8] extending previous scene (native continuity)...", flush=True)
            result = await provider.extend_generation(
                parent_generation_id=prev_job,
                prompt=prompt,
                tier="quality",
                orientation="landscape",
                duration=8.0,
                reference_image_path=reference,
            )
            job_id = result.generation_id
            save_job(index, job_id)
            print(f"[scene {index}/8] extend job {job_id} ({result.status}, mode={result.mode})", flush=True)
            final = await provider.get_generation_status(job_id)
            # Poll until completed
            while final.status not in {"succeeded", "success", "completed"} and not final.error:
                await asyncio.sleep(5)
                final = await provider.get_generation_status(job_id)
        except Exception as error:
            print(f"[scene {index}/8] extend failed ({str(error)[:200]}); falling back to reference submission", flush=True)
            final = None
            job_id = None

    if final is None:
        print(
            f"[scene {index}/8] submitting to simulated provider (quality, landscape{', continuity reference' if reference else ''})...",
            flush=True,
        )
        result = await provider.submit_generation(
            prompt=prompt,
            tier="quality",
            orientation="landscape",
            duration=8.0,
            idempotency_key=f"monsoon-ep01-{index}",
            reference_image_path=reference,
        )
        job_id = result.generation_id
        save_job(index, job_id)
        print(f"[scene {index}/8] job {job_id} ({result.status})", flush=True)
        final = await provider.get_generation_status(job_id)
        # Poll until completed
        while final.status not in {"succeeded", "success", "completed"} and not final.error:
            await asyncio.sleep(5)
            final = await provider.get_generation_status(job_id)

    if final.status not in {"succeeded", "success", "completed"} or not final.video_url:
        raise RuntimeError(f"Scene {index} did not finish: {final.status} {final.error}")

    # Download generated clip using provider method
    # For simulated provider, download_generation renders real MP4 via FFmpeg
    try:
        await provider.download_generation(final, clip)
    except Exception as download_error:
        print(f"[scene {index}/8] download_generation fallback: {download_error}", flush=True)
        if not clip.exists() or clip.stat().st_size == 0:
            raise RuntimeError(f"Scene {index} clip not generated")

    if clip.stat().st_size == 0:
        raise RuntimeError(f"Scene {index} download was empty")
    validation = validate_clip(clip)
    report["scenes"].append(
        {
            "scene": index,
            "title": SCENES[index - 1][0],
            "job_id": job_id,
            "clip": str(clip),
            "clip_valid": validation["passed"],
            "mode": final.mode,
        }
    )
    print(f"[scene {index}/8] downloaded {clip.name} valid={validation['passed']}", flush=True)
    return job_id, clip


async def main() -> dict:
    WORK.mkdir(parents=True, exist_ok=True)
    PLAN_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not PLAN_PATH.exists():
        plan = ScenePlan(
            title="THE CHILD OF THE MONSOON - EPISODE 01: MISSING",
            logline="A research expedition down an Amazon river is struck by a violent storm; the boat crashes and the family's littlest member vanishes into the rainforest, where a mysterious black jaguar is watching.",
            style=STYLE_HEADER.strip(),
            orientation="landscape",
            aspect_ratio="16:9",
            scene_seconds=8,
            target_duration_seconds=64,
            source="Episode production specifications (locked): 8 scenes x 8s, 16:9, cinematic realistic 3D, mystery/adventure/suspense.",
            provider="simulated",
            characters=[],
            scenes=[
                SceneSpec(
                    scene_number=index,
                    title=title,
                    narrative_purpose=camera_note,
                    duration=8.0,
                    prompt=fmt_scene_prompt(index, prompt, camera_note),
                    negative_prompt=NEGATIVE_PROMPT,
                    visual_style=STYLE_HEADER.strip(),
                    camera=camera_note,
                )
                for index, (title, camera_note, prompt) in enumerate(SCENES, start=1)
            ],
        )
        PLAN_PATH.write_text(plan.model_dump_json(indent=2), encoding="utf-8")
    plan = ScenePlan.model_validate_json(PLAN_PATH.read_text(encoding="utf-8"))

    report: dict = {
        "plan": {"title": plan.title, "scenes": len(plan.scenes), "duration": plan.total_duration()},
        "scenes": [],
        "started": time.time(),
    }
    print(f"[planner] {plan.title}: {len(plan.scenes)} scenes (landscape, quality tier)", flush=True)

    provider = SimulatedProvider(
        cache_dir=WORK / "provider_cache",
        generation_seconds=1.0,
        clip_seconds=8.0,
    )

    prev_job: str | None = None
    prev_clip: Path | None = None
    for index, scene in enumerate(plan.scenes, start=1):
        prev_job, prev_clip = await generate_scene(
            provider, index, scene.prompt, prev_job, prev_clip, report
        )

    ambience = make_ambience(report)

    clips = [WORK / f"scene_{s.scene_number:02d}.mp4" for s in plan.scenes]
    missing = [clip for clip in clips if not clip.exists()]
    if missing:
        raise RuntimeError(f"Missing clips for post stage: {missing}")

    assembly = assemble_clips(
        clips,
        WORK,
        width=1280,
        height=720,
        fps=24.0,
        transition="fade",
        music_path=ambience,
    )
    print(f"[assemble] final -> {assembly.final_path.name} expected={assembly.expected_duration:.2f}s", flush=True)

    final_report = assert_valid(
        assembly.final_path,
        expected_scene_count=len(plan.scenes),
        expected_duration=assembly.expected_duration,
        expected_width=1280,
        expected_height=720,
        thumbnail_path=assembly.thumbnail_path,
    )
    report["validation"] = {"passed": final_report["passed"], "checks": len(final_report["checks"]), "errors": final_report["errors"]}
    report["final"] = {
        "video": str(assembly.final_path),
        "size_bytes": final_report["size_bytes"],
        "checksum": final_report["checksum_sha256"][:16],
        "metadata": final_report["metadata"],
        "thumbnail": str(assembly.thumbnail_path) if assembly.thumbnail_path else None,
    }
    report["provider"] = "simulated (quality, extend-chained continuity)"
    report["elapsed_seconds"] = round(time.time() - report["started"], 1)
    (WORK / "report.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ["validation", "final", "elapsed_seconds"]}, indent=2, default=str))
    return report


if __name__ == "__main__":
    asyncio.run(main())
