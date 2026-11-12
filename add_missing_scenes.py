import json

# Read existing plan
with open('hollowthorn_plan.json') as f:
    plan = json.load(f)

# Check current scene count and indices
print("Current scene count:", len(plan["scenes"]))
print("Current scene indices:", [s["index"] for s in plan["scenes"]])

# Define scenes 39 and 40
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

# Scene 39: THE COPPER MOON
s39 = make_scene(39, "Scene 39: The Copper Moon",
    "A copper-coloured moon appears between thorn branches, staining the courtyard with old-blood glow.",
    "The scene opens on the night sky above Hollowthorn. A copper-coloured moon appears between tangled thorn branches. Its strange light stains the broken courtyard walls with an old-blood glow. The surrounding forest becomes unnaturally still. No insects move. No water drips. Even the labyrinth's grinding stops.",
    "Slow upward tilt toward the copper moon, then downward toward the silent courtyard.",
    "Copper-red moonlight, deep shadows, unnatural stillness.",
    "Wind cuts out, music falls into near silence.",
    "Create an 8-second cinematic shot for the short film \"HOLLOWTHORN — THE GUARDIAN OF THE FLEECE\". STORY BEAT: The scene opens on the night sky above Hollowthorn. A copper-coloured moon appears between tangled thorn branches. Its strange light stains the broken courtyard walls with an old-blood glow. The surrounding forest becomes unnaturally still. No insects move. No water drips. Even the labyrinth's grinding stops. VISUAL: The scene opens on the night sky above Hollowthorn. A copper-coloured moon appears between tangled thorn branches. Its strange light stains the broken courtyard walls with an old-blood glow. The surrounding forest becomes unnaturally still. No insects move. No water drips. Even the labyrinth's grinding stops. CAMERA: Slow upward tilt toward the copper moon, then downward toward the silent courtyard. LIGHTING: Copper-red moonlight, deep shadows, unnatural stillness. STYLE: cinematic photorealistic short film, 35mm lens, shallow depth of field, natural film grain, consistent color grade. No text, no subtitles, no captions, no logos, no watermarks. Preserve the same characters, wardrobe, props, environment, and color grade throughout the film.")

# Scene 40: THE BELL OF DOOM
s40 = make_scene(40, "Scene 40: The Bell of Doom",
    "The bronze bell suddenly strikes, dust falls, water ripples violently.",
    "The bronze bell suddenly strikes. Dust falls from the broken vault. The basin water ripples violently. The lambs huddle beneath the stone dais. Garrow plants his paws in front of them, lowering his shoulders and preparing to defend the courtyard. The bell's movement becomes increasingly violent.",
    "Rapid close-up of the bell, followed by a wide shot of the courtyard.",
    "Copper moonlight, moving dust, trembling shadows.",
    "Three powerful bell strikes, falling dust, deep stone resonance.",
    "Create an 8-second cinematic shot for the short film \"HOLLOWTHORN — THE GUARDIAN OF THE FLEECE\". STORY BEAT: The bronze bell suddenly strikes. Dust falls from the broken vault. The basin water ripples violently. The lambs huddle beneath the stone dais. Garrow plants his paws in front of them, lowering his shoulders and preparing to defend the courtyard. The bell's movement becomes increasingly violent. VISUAL: The bronze bell suddenly strikes. Dust falls from the broken vault. The basin water ripples violently. The lambs huddle beneath the stone dais. Garrow plants his paws in front of them, lowering his shoulders and preparing to defend the courtyard. The bell's movement becomes increasingly violent. CAMERA: Rapid close-up of the bell, followed by a wide shot of the courtyard. LIGHTING: Copper moonlight, moving dust, trembling shadows. STYLE: cinematic photorealistic short film, 35mm lens, shallow depth of field, natural film grain, consistent color grade. No text, no subtitles, no captions, no logos, no watermarks. Preserve the same characters, wardrobe, props, environment, and color grade throughout the film.")

# Insert scenes 39 and 40 at the correct positions (after scene 38, before scene 41)
plan["scenes"].insert(38, s39)
plan["scenes"].insert(39, s40)

# Update scene indices - need to renumber all scenes after the insertion
# Currently indices are: 1-38, 41-54
# After insertion: 1-40, then the rest need to shift
# But we want to keep original indices, so let me just add them and adjust

# Actually, the indices are already in order 1-38, then 41-54
# After inserting 39 and 40 at positions 38 and 39, the list becomes:
# 1, 2, ..., 38, 39, 40, 41, ..., 54
# Which is exactly what we want!

with open('hollowthorn_plan.json', 'w') as f:
    json.dump(plan, f, indent=2)

print(f"Plan updated with {len(plan['scenes'])} scenes")
print("Scene indices:", [s["index"] for s in plan["scenes"]])