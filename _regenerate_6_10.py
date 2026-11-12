import json
import shutil
from datetime import datetime
from pathlib import Path

PLAN = Path(r"C:\AI_Video_Studio\plans\the_boy_who_belonged_to_the_jungle.json")

STYLE = (
    "Hand-painted 2D animated feature-film style, cinematic jungle epic, painterly backgrounds, "
    "expressive characters with clean outlines, lush emerald foliage, warm golden light, volumetric rays, "
    "rich shadows, soft film grain, 24fps, widescreen."
)

KAI = (
    "Kai, a fully grown adult man in his late twenties with messy dark-brown hair, a short dark beard, "
    "expressive brown eyes, sun-kissed skin, a small leaf necklace and simple earthy forest clothing"
)
TARA = "Tara, a gentle elephant with soft grey skin, large ears and warm eyes"
MILO = "Milo, a playful light-brown monkey with a pale face and bright eyes"
RAJA = "Raja, a wise old Bengal tiger with orange fur, black stripes, a calm majestic face and old scars"

PROMPTS = {
    6: f"""An 8-second cinematic shot continuing from the previous final frame. {STYLE} 0-2 seconds: {KAI} climbs onto a rocky ledge; his adult hands grip the stone. 2-4 seconds: he looks down at the animals trapped below the fallen tree; the camera follows his gaze, keeping the fallen tree and the dry riverbed clearly visible. 4-6 seconds: he turns to {TARA} and {MILO}; Tara nods; Milo chatters. 6-8 seconds: Kai points firmly toward the fallen tree; Tara, Milo and {RAJA} gather at the tree; the camera settles on a medium-wide shot of the group at the fallen tree, the tree and the animals filling the frame, Kai pointing from the rocks. Camera: low-angle medium shot on Kai, then a medium-wide composition of the group and the fallen tree; 40mm lens; keep the camera close to the characters and the tree. Lighting: hard golden light breaking through the canopy, dramatic contrast. Continuity: keep Kai, Tara, Milo, Raja, the fallen tree, the painterly 2D style and the color grade consistent. The shot ends on a medium-wide view from behind or the side, with faces not clearly visible; the fallen tree and the animals remain large in the frame. No text, no subtitles, no captions, no logos, no watermarks.""",
    7: f"""An 8-second cinematic shot extending the story from the previous final frame. {STYLE} The shot begins with a hard cut to a medium close shot of {TARA} planting her forehead against the fallen tree and pushing; the bark fills the frame and dust and leaves shake loose. 0-2 seconds: Tara pushes hard, her feet braced in the mud, the huge fallen tree filling the background. 2-4 seconds: {MILO} grabs a thick hanging vine and pulls it away; {RAJA} clears smaller branches with powerful swipes of his paws; the camera stays close to the tree and the animals. 4-6 seconds: {KAI} directs from the rocks, waving his arms; the enormous tree begins to shift; the camera cuts between the tree, Tara, Milo, Raja and Kai. 6-8 seconds: the tree rolls free and water bursts through the channel; the camera pulls back only slightly to a medium-wide shot of the rushing water and the characters from behind at the water's edge. Camera: medium close shots and medium shots, quick cuts; the fallen tree and the animals are always the main subject and fill the frame; 35mm lens; keep the camera close to the action for the entire shot. The frame is filled by the fallen tree, the animals and the riverbed; the camera never shows an empty jungle path or distant tiny figures. Lighting: dramatic shafts of sunlight, mist, water spray. Continuity: keep all characters, the fallen tree, the painterly 2D style and the color grade consistent; build to a triumphant release. The shot ends on a medium-wide view from behind or the side, with faces not clearly visible. No text, no subtitles, no captions, no logos, no watermarks.""",
    8: f"""An 8-second cinematic shot continuing from the previous final frame. {STYLE} 0-2 seconds: fresh water rushes through the river; the camera glides low over the sparkling surface, then rises to a medium-wide view of the animals at the water's edge. 2-4 seconds: elephants splash joyfully; {TARA} scoops water with her trunk; birds return to the trees. 4-6 seconds: flowers bloom along the riverbank; {MILO} leaps from branch to branch. 6-8 seconds: Tara playfully lifts {KAI} with her trunk; Kai laughs; the camera pulls back to a medium-wide view from behind the group. Camera: joyful medium-wide shot, slow circular crane move, 35mm lens; keep the characters visible in the frame. Lighting: bright warm sunlight, rainbow mist, sparkling water. Continuity: keep all characters, the painterly 2D style and the color grade consistent; release the tension into celebration. The shot ends on a medium-wide view from behind or the side, with faces not clearly visible; the characters remain visible. No text, no subtitles, no captions, no logos, no watermarks.""",
    9: f"""An 8-second cinematic shot continuing from the previous final frame. {STYLE} 0-2 seconds: {KAI} walks to the edge of a tall cliff; the camera follows behind him at a medium distance. 2-4 seconds: {MILO} climbs onto his shoulder; {TARA} steps up beside him; {RAJA} settles behind them. 4-6 seconds: the sky glows orange and purple; the endless jungle stretches to the horizon. 6-8 seconds: the camera slowly pulls back into a wide silhouette shot from behind, the family visible against the glowing sky. Camera: slow pull-back, wide cinematic composition, 35mm lens; keep the family readable in silhouette. Lighting: orange and purple sunset, warm rim light, long shadows. Continuity: keep all characters, the painterly 2D style and the color grade consistent; shift into a reflective mood. The shot ends on a wide view from behind or the side, with faces not clearly visible; the family remains visible. No text, no subtitles, no captions, no logos, no watermarks.""",
    10: f"""An 8-second cinematic shot continuing from the previous final frame. {STYLE} 0-2 seconds: the camera continues pulling away from {KAI} and his animal family on the cliff; they remain visible as a small group in the lower third of the frame. 2-4 seconds: the sun sinks behind the mountains; the sky deepens to blue and purple. 4-6 seconds: fireflies blink on across the jungle; stars appear. 6-8 seconds: the family becomes a silhouette against the glowing horizon; the camera holds on a wide, peaceful final image. Camera: very slow aerial pull-back, wide 24mm composition. Lighting: deep blue twilight, orange afterglow, firefly bioluminescence, starlight. Continuity: keep all characters, the painterly 2D style and the color grade consistent; end on a timeless image. The shot ends on a wide view from behind or the side, with faces not clearly visible. No text, no subtitles, no captions, no logos, no watermarks.""",
}

VISUALS = {
    6: "Kai climbs a rocky ledge, sees the trapped animals, turns to Tara and Milo, and points at the fallen tree. Tara, Milo and Raja gather at the tree. The camera ends on a medium-wide shot of the group at the fallen tree.",
    7: "Hard cut to Tara pushing the fallen tree, Milo pulling a vine, Raja clearing branches, and Kai directing. The tree rolls free and water bursts through. The camera stays close to the action and ends on a medium-wide view of the water and characters from behind.",
    8: "Water rushes, elephants splash, flowers bloom, Milo leaps, and Tara lifts Kai. The camera ends on a medium-wide view from behind the group.",
    9: "Kai walks to the cliff edge; Milo climbs onto his shoulder; Tara and Raja join him; the sky glows orange and purple. The camera pulls back to a wide silhouette from behind.",
    10: "The camera pulls away from Kai and his family on the cliff; the sun sinks; fireflies and stars appear; the family becomes a silhouette against the glowing horizon.",
}

CAMERAS = {
    6: "low-angle medium shot on Kai, then a medium-wide composition of the group and the fallen tree, 40mm lens; keep the camera close to the characters and the tree.",
    7: "medium close shots and medium shots, quick cuts, 35mm lens; the fallen tree and animals fill the frame; never an empty jungle path or distant tiny figures.",
    8: "joyful medium-wide shot, slow circular crane move, 35mm lens; keep the characters visible.",
    9: "slow pull-back, wide cinematic composition, 35mm lens; keep the family readable in silhouette.",
    10: "very slow aerial pull-back, wide 24mm composition.",
}

CONTINUITY = {
    6: "Continue from the previous frame. Keep Kai, Tara, Milo, Raja, the fallen tree and the painterly 2D style consistent; end with the tree and animals large in frame.",
    7: "Keep all characters, the fallen tree, the painterly 2D style and the color grade consistent; build to a triumphant release.",
    8: "Keep all characters, the painterly 2D style and the color grade consistent; release the tension into celebration.",
    9: "Keep all characters, the painterly 2D style and the color grade consistent; shift into a reflective mood.",
    10: "Keep all characters, the painterly 2D style and the color grade consistent; end on a timeless image.",
}


def main() -> None:
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    scenes = plan["scenes"]
    scene_dir = Path(scenes[0]["local_video"]).parent
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    final_path = Path(plan["final_video"])
    backup_final = final_path.with_name(final_path.stem + "_before_fix.mp4")
    if final_path.exists() and not backup_final.exists():
        shutil.copy2(final_path, backup_final)
        print(f"Backed up current final: {backup_final}")

    backup_dir = scene_dir / f"_old_run_{stamp}"
    backup_dir.mkdir(parents=True, exist_ok=True)
    for index in range(6, 11):
        for suffix in (".mp4", "_last.png"):
            source = scene_dir / f"scene_{index:03d}{suffix}"
            if source.exists():
                shutil.move(str(source), str(backup_dir / source.name))
    print(f"Backed up old scenes 6-10 to: {backup_dir}")

    plan["logline"] = (
        "A man raised by the jungle must rally his animal family to save their river "
        "and discover where he truly belongs."
    )
    plan["source"] = (
        "THE BOY WHO BELONGED TO THE JUNGLE - 10 scenes x 8 seconds. Kai, a man raised in the jungle, "
        "lives with Milo the monkey, Tara the elephant and Raja the tiger. When a fallen tree blocks the river, "
        "they work together to restore the water and celebrate their family."
    )
    plan["completed_at"] = None
    for session in plan.get("sessions") or []:
        session["status"] = "pending"

    for scene in scenes:
        index = int(scene["index"])
        if index < 6:
            continue
        scene["visual"] = VISUALS[index]
        scene["camera"] = CAMERAS[index]
        scene["continuity"] = CONTINUITY[index]
        scene["prompt"] = PROMPTS[index]
        scene["status"] = "pending"
        scene["job_id"] = None
        scene["video_url"] = None
        scene["local_video"] = None
        scene["last_frame"] = None
        scene["error"] = None
        scene["attempts"] = 0
        scene["prompt_sent"] = None
        scene["duration_actual"] = None
        scene["resolution"] = None
        scene["fps"] = None
        scene["parent_id"] = None
        scene["segment_index"] = index - 1
        scene["mode"] = "i2v"

    PLAN.write_text(json.dumps(plan, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Updated plan: {PLAN}")
    for scene in scenes:
        if int(scene["index"]) >= 6:
            print(f"Scene {scene['index']}: {scene['status']} | prompt chars={len(scene['prompt'])}")


if __name__ == "__main__":
    main()
