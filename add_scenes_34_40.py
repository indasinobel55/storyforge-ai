import json

# Read existing plan
with open('hollowthorn_plan.json') as f:
    plan = json.load(f)

# Define scenes 34-54
def make_scene(idx, title, narration, visual, camera, lighting, continuity, prompt):
    return {
        "index": idx,
        "duration": 8,
        "title": title,
        "narration": narration,
        "visual": visual,
        "camera": camera,
        "lighting": lighting,
        "continuity": continuity,
        "prompt": prompt,
        "status": "pending",
        "job_id": None,
        "video_url": None,
        "local_video": None,
        "last_frame": None,
        "error": None,
        "attempts": 0,
    }

# Scene 34-40
scenes_34_40 = [
    make_scene(34, "Scene 34: The Pack He Had Lost",
        "Garrow looks into the basin, memories of his old pack.",
        "Garrow sits beside the basin, looking into the water. The reflection briefly suggests distant memories of his old pack crossing frozen steppes and ruined kingdoms. These are indistinct silhouettes, not new identifiable characters. Return to Garrow as he lowers his head. His grief remains visible, but it no longer overwhelms him.",
        "Close-up of the basin reflection, then a slow push toward Garrow.",
        "Cool reflections with soft silver highlights.",
        "Distant wind, faint remembered howls, soft strings.",
        "Create an 8-second cinematic shot for the short film \"HOLLOWTHORN — THE GUARDIAN OF THE FLEECE\". STORY BEAT: Garrow sits beside the basin, looking into the water. The reflection briefly suggests distant memories of his old pack crossing frozen steppes and ruined kingdoms. These are indistinct silhouettes, not new identifiable characters. Return to Garrow as he lowers his head. His grief remains visible, but it no longer overwhelms him. VISUAL: Close-up of the basin reflection, then a slow push toward Garrow. LIGHTING: Cool reflections with soft silver highlights. STYLE: cinematic photorealistic short film, 35mm lens, shallow depth of field, natural film grain, consistent color grade. No text, no subtitles, no captions, no logos, no watermarks. Preserve the same characters, wardrobe, props, environment, and color grade throughout the film."),
    make_scene(35, "Scene 35: The Meaning of Family",
        "Bram falls asleep on Garrow, Oona hums, Pip watches moonlight.",
        "Bram falls asleep with his head resting on Garrow's foreleg. Oona hums beside the basin. Pip watches moonlight move across the lilies. Garrow looks down at Bram, then toward the other two lambs. His expression changes as he understands the bond they have formed. He remains still so Bram can sleep.",
        "Slow close-ups of each lamb, ending on Garrow's peaceful expression.",
        "Warm moonlight, quiet and intimate composition.",
        "Soft humming, slow breathing, delicate musical warmth.",
        "Create an 8-second cinematic shot for the short film \"HOLLOWTHORN — THE GUARDIAN OF THE FLEECE\". STORY BEAT: Bram falls asleep with his head resting on Garrow's foreleg. Oona hums beside the basin. Pip watches moonlight move across the lilies. Garrow looks down at Bram, then toward the other two lambs. His expression changes as he understands the bond they have formed. He remains still so Bram can sleep. VISUAL: Slow close-ups of each lamb, ending on Garrow's peaceful expression. LIGHTING: Warm moonlight, quiet and intimate composition. STYLE: cinematic photorealistic short film, 35mm lens, shallow depth of field, natural film grain, consistent color grade. No text, no subtitles, no captions, no logos, no watermarks. Preserve the same characters, wardrobe, props, environment, and color grade throughout the film."),
    make_scene(36, "Scene 36: The Bell Trembles",
        "The cracked bronze bell begins to vibrate.",
        "The cracked bronze bell above the far arch begins to tremble. Its clapper does not visibly strike the rim. A subtle vibration travels through the bell's metal surface. The water in the basin develops small ripples. Garrow lifts his head sharply. Pip stops moving. Oona's humming fades. Bram wakes and presses closer to Garrow.",
        "Close-up of the vibrating bell, followed by a wide shot of the group's reaction.",
        "Moonlight becomes colder; shadows deepen.",
        "Low metallic vibration, rippling water, music shifting toward suspense.",
        "Create an 8-second cinematic shot for the short film \"HOLLOWTHORN — THE GUARDIAN OF THE FLEECE\". STORY BEAT: The cracked bronze bell above the far arch begins to tremble. Its clapper does not visibly strike the rim. A subtle vibration travels through the bell's metal surface. The water in the basin develops small ripples. Garrow lifts his head sharply. Pip stops moving. Oona's humming fades. Bram wakes and presses closer to Garrow. VISUAL: Close-up of the vibrating bell, followed by a wide shot of the group's reaction. LIGHTING: Moonlight becomes colder; shadows deepen. STYLE: cinematic photorealistic short film, 35mm lens, shallow depth of field, natural film grain, consistent color grade. No text, no subtitles, no captions, no logos, no watermarks. Preserve the same characters, wardrobe, props, environment, and color grade throughout the film."),
    make_scene(37, "Scene 37: The Scent of Fire",
        "Garrow senses the Cinder Tiger approaching.",
        "Garrow rises slowly. His fur lifts along his spine. He turns toward the southern arch. Deep claw grooves have appeared across the granite, far wider than any wolf's claws. The surrounding stone is blackened as though scorched from within. Pip moves the other lambs behind Garrow. A faint dark shape shifts beyond the arch.",
        "Slow pan from the claw marks to Garrow's defensive stance.",
        "Cold moonlight with subtle burnt-orange reflections from the distant darkness.",
        "Deep chain drag, faint crackling, tense low strings.",
        "Create an 8-second cinematic shot for the short film \"HOLLOWTHORN — THE GUARDIAN OF THE FLEECE\". STORY BEAT: Garrow rises slowly. His fur lifts along his spine. He turns toward the southern arch. Deep claw grooves have appeared across the granite, far wider than any wolf's claws. The surrounding stone is blackened as though scorched from within. Pip moves the other lambs behind Garrow. A faint dark shape shifts beyond the arch. VISUAL: Slow pan from the claw marks to Garrow's defensive stance. LIGHTING: Cold moonlight with subtle burnt-orange reflections from the distant darkness. STYLE: cinematic photorealistic short film, 35mm lens, shallow depth of field, natural film grain, consistent color grade. No text, no subtitles, no captions, no logos, no watermarks. Preserve the same characters, wardrobe, props, environment, and color grade throughout the film."),
    make_scene(38, "Scene 38: The Guardian Stands",
        "Garrow positions himself between the arch and the lambs.",
        "Garrow moves directly between the southern arch and the three lambs. His body is still scarred and not fully recovered, but his stance is firm. Pip, Bram, and Oona gather behind him. The camera slowly pushes toward Garrow's face as he watches the darkness. Beyond the arch, an unseen chain drags across stone.",
        "Low-angle hero composition, slow push-in.",
        "Moonlight outlines Garrow's silhouette; deep shadows conceal the approaching threat.",
        "Heavy chain scrape, controlled breathing, rising orchestral tension.",
        "Create an 8-second cinematic shot for the short film \"HOLLOWTHORN — THE GUARDIAN OF THE FLEECE\". STORY BEAT: Garrow moves directly between the southern arch and the three lambs. His body is still scarred and not fully recovered, but his stance is firm. Pip, Bram, and Oona gather behind him. The camera slowly pushes toward Garrow's face as he watches the darkness. Beyond the arch, an unseen chain drags across stone. VISUAL: Low-angle hero composition, slow push-in. LIGHTING: Moonlight outlines Garrow's silhouette; deep shadows conceal the approaching threat. STYLE: cinematic photorealistic short film, 35mm lens, shallow depth of field, natural film grain, consistent color grade. No text, no subtitles, no captions, no logos, no watermarks. Preserve the same characters, wardrobe, props, environment, and color grade throughout the film."),
]

plan["scenes"].extend(scenes_34_40)

with open('hollowthorn_plan.json', 'w') as f:
    json.dump(plan, f, indent=2)

print(f"Plan updated with {len(plan['scenes'])} scenes (added scenes 34-40)")