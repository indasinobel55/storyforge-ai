import json

# Read existing plan
with open('hollowthorn_plan.json') as f:
    plan = json.load(f)

# Define scenes 28-38
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

# Scene 28-33
scenes_28_33 = [
    make_scene(28, "Scene 28: Days That Gathered",
        "Poetic sequence of changing moments at the Bramble Cloister.",
        "Show the Bramble Cloister through a poetic sequence of changing moments. Outside its walls, thorn branches shift and black sap seeps from the roots. Inside, Garrow rests near the basin while the lambs move through their daily routines. Moonlight shifts across the courtyard, suggesting time passing without revealing exact days or seasons.",
        "Gentle montage of the sanctuary and surrounding labyrinth.",
        "Quiet moonlit blues with subtle changes in shadow.",
        "Distant root movement, water, soft natural ambience.",
        "Create an 8-second cinematic shot for the short film \"HOLLOWTHORN — THE GUARDIAN OF THE FLEECE\". STORY BEAT: Show the Bramble Cloister through a poetic sequence of changing moments. Outside its walls, thorn branches shift and black sap seeps from the roots. Inside, Garrow rests near the basin while the lambs move through their daily routines. Moonlight shifts across the courtyard, suggesting time passing without revealing exact days or seasons. VISUAL: Show the Bramble Cloister through a poetic sequence of changing moments. Outside its walls, thorn branches shift and black sap seeps from the roots. Inside, Garrow rests near the basin while the lambs move through their daily routines. Moonlight shifts across the courtyard, suggesting time passing without revealing exact days or seasons. CAMERA: Gentle montage of the sanctuary and surrounding labyrinth. LIGHTING: Quiet moonlit blues with subtle changes in shadow. STYLE: cinematic photorealistic short film, 35mm lens, shallow depth of field, natural film grain, consistent color grade. No text, no subtitles, no captions, no logos, no watermarks. Preserve the same characters, wardrobe, props, environment, and color grade throughout the film."),
    make_scene(29, "Scene 29: Pip, The Steady One",
        "Pip leads Garrow toward a hidden cistern.",
        "Pip leads Garrow toward a hidden cistern. He pauses beside a stone passage and waits until the recovering wolf follows. Show Pip pointing his nose toward clean water, then toward pale mushrooms growing between the stones. When Garrow tries to move too quickly, Pip stops patiently until the wolf slows down.",
        "Side-tracking shot following the pair through the courtyard.",
        "Soft natural light filtering through the broken roof.",
        "Small hoofsteps, water dripping, soft stone echoes.",
        "Create an 8-second cinematic shot for the short film \"HOLLOWTHORN — THE GUARDIAN OF THE FLEECE\". STORY BEAT: Pip leads Garrow toward a hidden cistern. He pauses beside a stone passage and waits until the recovering wolf follows. Show Pip pointing his nose toward clean water, then toward pale mushrooms growing between the stones. When Garrow tries to move too quickly, Pip stops patiently until the wolf slows down. VISUAL: Pip leads Garrow toward a hidden cistern. He pauses beside a stone passage and waits until the recovering wolf follows. Show Pip pointing his nose toward clean water, then toward pale mushrooms growing between the stones. When Garrow tries to move too quickly, Pip stops patiently until the wolf slows down. CAMERA: Side-tracking shot following the pair through the courtyard. LIGHTING: Soft natural light filtering through the broken roof. STYLE: cinematic photorealistic short film, 35mm lens, shallow depth of field, natural film grain, consistent color grade. No text, no subtitles, no captions, no logos, no watermarks. Preserve the same characters, wardrobe, props, environment, and color grade throughout the film."),
    make_scene(30, "Scene 30: Bram, The Fearless Mischief",
        "Bram leaps over Garrow's tail and climbs onto his back.",
        "Bram leaps over Garrow's resting tail as though crossing a fallen tree. He disappears playfully into the wolf's thick ruff, then climbs onto Garrow's back. Garrow turns his head with a pretend-annoyed expression. Bram stands proudly atop him. Garrow's tail betrays his amusement, thumping against the flagstones.",
        "Playful low-angle shot followed by a close-up of Garrow's moving tail.",
        "Gentle moonlight with warmer highlights.",
        "Quick hoofsteps, soft fleece rustling, tail thumping against stone.",
        "Create an 8-second cinematic shot for the short film \"HOLLOWTHORN — THE GUARDIAN OF THE FLEECE\". STORY BEAT: Bram leaps over Garrow's resting tail as though crossing a fallen tree. He disappears playfully into the wolf's thick ruff, then climbs onto Garrow's back. Garrow turns his head with a pretend-annoyed expression. Bram stands proudly atop him. Garrow's tail betrays his amusement, thumping against the flagstones. VISUAL: Bram leaps over Garrow's resting tail as though crossing a fallen tree. He disappears playfully into the wolf's thick ruff, then climbs onto Garrow's back. Garrow turns his head with a pretend-annoyed expression. Bram stands proudly atop him. Garrow's tail betrays his amusement, thumping against the flagstones. CAMERA: Playful low-angle shot followed by a close-up of Garrow's moving tail. LIGHTING: Gentle moonlight with warmer highlights. STYLE: cinematic photorealistic short film, 35mm lens, shallow depth of field, natural film grain, consistent color grade. No text, no subtitles, no captions, no logos, no watermarks. Preserve the same characters, wardrobe, props, environment, and color grade throughout the film."),
    make_scene(31, "Scene 31: Oona, The Quiet Melody",
        "Oona gathers flowers and hums gently behind Garrow's ear.",
        "Oona gathers small white flowers and blue bellflowers from cracks in the courtyard stones. She carefully places them behind Garrow's torn left ear. As she works, she hums gently. Garrow catches his reflection in the clear basin: a scarred ash-grey wolf wearing a delicate crown of flowers. He looks away, but a subtle smile appears.",
        "Close-up of Oona placing flowers, followed by the reflection in the basin.",
        "Soft silver-blue illumination, delicate flower details.",
        "Gentle humming, flower stems brushing fur, quiet water.",
        "Create an 8-second cinematic shot for the short film \"HOLLOWTHORN — THE GUARDIAN OF THE FLEECE\". STORY BEAT: Oona gathers small white flowers and blue bellflowers from cracks in the courtyard stones. She carefully places them behind Garrow's torn left ear. As she works, she hums gently. Garrow catches his reflection in the clear basin: a scarred ash-grey wolf wearing a delicate crown of flowers. He looks away, but a subtle smile appears. VISUAL: Close-up of Oona placing flowers, followed by the reflection in the basin. LIGHTING: Soft silver-blue illumination, delicate flower details. STYLE: cinematic photorealistic short film, 35mm lens, shallow depth of field, natural film grain, consistent color grade. No text, no subtitles, no captions, no logos, no watermarks. Preserve the same characters, wardrobe, props, environment, and color grade throughout the film."),
    make_scene(32, "Scene 32: A Language Without Words",
        "Sequence of small gestures between characters.",
        "Show a sequence of small gestures between the characters. Garrow lowers his head to let Bram approach. Pip gives a gentle warning tap with his hoof. Oona rests beside Garrow's forepaws. Garrow holds one paw still as the lambs pass nearby. Their eyes meet, and their movements become naturally coordinated.",
        "A series of intimate medium shots connected by smooth dissolves.",
        "Peaceful courtyard lighting, soft natural shadows.",
        "Soft hoofsteps, breathing, quiet humming.",
        "Create an 8-second cinematic shot for the short film \"HOLLOWTHORN — THE GUARDIAN OF THE FLEECE\". STORY BEAT: Show a sequence of small gestures between the characters. Garrow lowers his head to let Bram approach. Pip gives a gentle warning tap with his hoof. Oona rests beside Garrow's forepaws. Garrow holds one paw still as the lambs pass nearby. Their eyes meet, and their movements become naturally coordinated. VISUAL: A series of intimate medium shots connected by smooth dissolves. LIGHTING: Peaceful courtyard lighting, soft natural shadows. STYLE: cinematic photorealistic short film, 35mm lens, shallow depth of field, natural film grain, consistent color grade. No text, no subtitles, no captions, no logos, no watermarks. Preserve the same characters, wardrobe, props, environment, and color grade throughout the film."),
    make_scene(33, "Scene 33: The Wolf Begins to Heal",
        "Garrow walks more comfortably through the courtyard.",
        "Show Garrow walking more comfortably through the courtyard. His paw pads are healing, his coat looks healthier, and the fever has left his eyes. He rests without constantly watching the entrance. When a branch moves outside, he briefly looks up but does not immediately rise in alarm. The lambs continue their routines around him.",
        "Slow tracking shot following Garrow's steady walk.",
        "Slightly warmer light, peaceful sanctuary ambience.",
        "Calm footsteps, soft breeze, gentle music.",
        "Create an 8-second cinematic shot for the short film \"HOLLOWTHORN — THE GUARDIAN OF THE FLEECE\". STORY BEAT: Show Garrow walking more comfortably through the courtyard. His paw pads are healing, his coat looks healthier, and the fever has left his eyes. He rests without constantly watching the entrance. When a branch moves outside, he briefly looks up but does not immediately rise in alarm. The lambs continue their routines around him. VISUAL: Show Garrow walking more comfortably through the courtyard. His paw pads are healing, his coat looks healthier, and the fever has left his eyes. He rests without constantly watching the entrance. When a branch moves outside, he briefly looks up but does not immediately rise in alarm. The lambs continue their routines around him. CAMERA: Slow tracking shot following Garrow's steady walk. LIGHTING: Slightly warmer light, peaceful sanctuary ambience. STYLE: cinematic photorealistic short film, 35mm lens, shallow depth of the field, natural film grain, consistent color grade. No text, no subtitles, no captions, no logos, no watermarks. Preserve the same characters, wardrobe, props, environment, and color grade throughout the film."),
]

plan["scenes"].extend(scenes_28_33)

with open('hollowthorn_plan.json', 'w') as f:
    json.dump(plan, f, indent=2)

print(f"Plan updated with {len(plan['scenes'])} scenes (added scenes 28-33)")