import json

# Read existing plan
with open('hollowthorn_plan.json') as f:
    plan = json.load(f)

# Define scenes 18-54
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

# Scene 18: THROUGH THE THORNS
scenes_18_27 = [
    make_scene(18, "Scene 18: Through the Thorns",
        "Garrow forces himself through a narrow passage, thorns scraping his body.",
        "Garrow forces himself through a narrow passage. Thorn branches scrape both sides of his body, tearing his already damaged coat and opening fresh cuts along his flanks. He pushes forward despite the pain. At the end of the corridor, the branches slowly part, revealing a pale opening beyond.",
        "Tight side-tracking shot through the narrow passage, ending in a bright reveal.",
        "Dark thorn tunnel opening into soft moonlight.",
        "Branches scraping fur, strained breathing, distant water.",
        "Create an 8-second cinematic shot for the short film \"HOLLOWTHORN — THE GUARDIAN OF THE FLEECE\". STORY BEAT: Garrow forces himself through a narrow passage. Thorn branches scrape both sides of his body, tearing his already damaged coat and opening fresh cuts along his flanks. He pushes forward despite the pain. At the end of the corridor, the branches slowly part, revealing a pale opening beyond. VISUAL: Garrow forces himself through a narrow passage. Thorn branches scrape both sides of his body, tearing his already damaged coat and opening fresh cuts along his flanks. He pushes forward despite the pain. At the end of the corridor, the branches slowly part, revealing a pale opening beyond. CAMERA: Tight side-tracking shot through the narrow passage, ending in a bright reveal. LIGHTING: Dark thorn tunnel opening into soft moonlight. STYLE: cinematic photorealistic short film, 35mm lens, shallow depth of field, natural film grain, consistent color grade. No text, no subtitles, no captions, no logos, no watermarks. Preserve the same characters, wardrobe, props, environment, and color grade throughout the film."),
    make_scene(19, "Scene 19: The Bramble Cloister",
        "Reveal the Bramble Cloister courtyard with moonlight, lilies, and basin.",
        "Reveal the Bramble Cloister: a sunken courtyard beneath a broken stone vault. Moonlight enters through a crack in the roof, creating pale bars across ancient flagstones. White lilies grow from the mortar. A shallow basin filled with clear water rests at the centre. Above the far arch hangs a cracked bronze bell. Garrow enters and stumbles, overwhelmed by the sudden stillness.",
        "Slow cinematic wide reveal, moving down toward the courtyard floor.",
        "Soft moonlight, silver-blue highlights, delicate mist.",
        "Quiet water, faint wind through the roof, soft ambient music.",
        "Create an 8-second cinematic shot for the short film \"HOLLOWTHORN — THE GUARDIAN OF THE FLEECE\". STORY BEAT: Reveal the Bramble Cloister: a sunken courtyard beneath a broken stone vault. Moonlight enters through a crack in the roof, creating pale bars across ancient flagstones. White lilies grow from the mortar. A shallow basin filled with clear water rests at the centre. Above the far arch hangs a cracked bronze bell. Garrow enters and stumbles, overwhelmed by the sudden stillness. VISUAL: Reveal the Bramble Cloister: a sunken courtyard beneath a broken stone vault. Moonlight enters through a crack in the roof, creating pale bars across ancient flagstones. White lilies grow from the mortar. A shallow basin filled with clear water rests at the centre. Above the far arch hangs a cracked bronze bell. Garrow enters and stumbles, overwhelmed by the sudden stillness. CAMERA: Slow cinematic wide reveal, moving down toward the courtyard floor. LIGHTING: Soft moonlight, silver-blue highlights, delicate mist. STYLE: cinematic photorealistic short film, 35mm lens, shallow depth of field, natural film grain, consistent color grade. No text, no subtitles, no captions, no logos, no watermarks. Preserve the same characters, wardrobe, props, environment, and color grade throughout the film."),
    make_scene(20, "Scene 20: Three Small Figures",
        "Three lambs stand beside the basin - Pip (eldest), Bram (smallest with dark muzzle), Oona (quiet).",
        "Three small white lambs stand beside the basin. The smallest has a dark muzzle and leans curiously forward. The eldest watches Garrow with thoughtful, steady eyes. The quietest remains half a step behind, gentle and still. Their clean white fleece contrasts sharply against the soot-dark courtyard. Garrow looks at them through exhaustion.",
        "Medium-wide shot of the lambs, followed by a slow close-up of Garrow's eyes.",
        "Moonlight catches the lambs' fleece, creating a soft natural glow.",
        "Soft hoof movements, quiet water, faint fleece rustling.",
        "Create an 8-second cinematic shot for the short film \"HOLLOWTHORN — THE GUARDIAN OF THE FLEECE\". STORY BEAT: Three small white lambs stand beside the basin. The smallest has a dark muzzle and leans curiously forward. The eldest watches Garrow with thoughtful, steady eyes. The quietest remains half a step behind, gentle and still. Their clean white fleece contrasts sharply against the soot-dark courtyard. Garrow looks at them through exhaustion. VISUAL: Three small white lambs stand beside the basin. The smallest has a dark muzzle and leans curiously forward. The eldest watches Garrow with thoughtful, steady eyes. The quietest remains half a step behind, gentle and still. Their clean white fleece contrasts sharply against the soot-dark courtyard. Garrow looks at them through exhaustion. CAMERA: Medium-wide shot of the lambs, followed by a slow close-up of Garrow's eyes. LIGHTING: Moonlight catches the lambs' fleece, creating a soft natural glow. STYLE: cinematic photorealistic short film, 35mm lens, shallow depth of field, natural film grain, consistent color grade. No text, no subtitles, no captions, no logos, no watermarks. Preserve the same characters, wardrobe, props, environment, and color grade throughout the film."),
    make_scene(21, "Scene 21: Hunger Returns",
        "Garrow's gaze shifts toward the lambs, hunger overwhelming him.",
        "Garrow's gaze shifts toward the lambs. His pupils tighten. His legs tremble, and his mouth fills with saliva. Show a brief close-up of his hungry expression, followed by the lambs' small, vulnerable forms. He lowers his head and tenses his shoulders. The instinct to attack begins overcoming his remaining restraint.",
        "Alternating close-ups between Garrow's face and the lambs.",
        "Shadows deepen around Garrow while the lambs remain softly illuminated.",
        "Low rumble, shallow breathing, tension-building strings.",
        "Create an 8-second cinematic shot for the short film \"HOLLOWTHORN — THE GUARDIAN OF THE FLEECE\". STORY BEAT: Garrow's gaze shifts toward the lambs. His pupils tighten. His legs tremble, and his mouth fills with saliva. Show a brief close-up of his hungry expression, followed by the lambs' small, vulnerable forms. He lowers his head and tenses his shoulders. The instinct to attack begins overcoming his remaining restraint. VISUAL: Alternating close-ups between Garrow's face and the lambs. LIGHTING: Shadows deepen around Garrow while the lambs remain softly illuminated. STYLE: cinematic photorealistic short film, 35mm lens, shallow depth of field, natural film grain, consistent color grade. No text, no subtitles, no captions, no logos, no watermarks. Preserve the same characters, wardrobe, props, environment, and color grade throughout the film."),
    make_scene(22, "Scene 22: The Charge",
        "Garrow lunges toward the lambs, Bram steps forward.",
        "Garrow suddenly lunges toward the three lambs. The smallest lamb, Bram, steps forward instead of running. He tilts his head toward the wolf's black nose, sniffs it, and gives a small sneeze. Then he presses his warm shoulder against Garrow's torn paw. Garrow's jaws snap shut inches above the lamb.",
        "Rapid forward tracking shot, ending in an intense close-up of the near miss.",
        "Sudden movement against the still moonlit courtyard.",
        "Sudden paw impact, sharp breath, a tiny sneeze, abrupt musical silence.",
        "Create an 8-second cinematic shot for the short film \"HOLLOWTHORN — THE GUARDIAN OF THE FLEECE\". STORY BEAT: Garrow suddenly lunges toward the three lambs. The smallest lamb, Bram, steps forward instead of running. He tilts his head toward the wolf's black nose, sniffs it, and gives a small sneeze. Then he presses his warm shoulder against Garrow's torn paw. Garrow's jaws snap shut inches above the lamb. VISUAL: Rapid forward tracking shot, ending in an intense close-up of the near miss. LIGHTING: Sudden movement against the still moonlit courtyard. STYLE: cinematic photorealistic short film, 35mm lens, shallow depth of field, natural film grain, consistent color grade. No text, no subtitles, no captions, no logos, no watermarks. Preserve the same characters, wardrobe, props, environment, and color grade throughout the film."),
    make_scene(23, "Scene 23: Kindness Instead of Fear",
        "Bram nudges a wicker bowl of food toward Garrow.",
        "Hold on the moment after Garrow's jaws stop. Bram remains close, visibly trembling but refusing to retreat. The eldest lamb, Pip, carefully nudges a small wicker bowl across the stone floor. Inside are dried berries, sweet roots, and a little mound of clover. Pip pushes the bowl toward Garrow, then steps back.",
        "Close-up of the bowl sliding across the flagstones, then Garrow's stunned expression.",
        "Warm highlights on the food against the cool stone.",
        "Wicker scraping softly across stone, gentle breathing, restrained music.",
        "Create an 8-second cinematic shot for the short film \"HOLLOWTHORN — THE GUARDIAN OF THE FLEECE\". STORY BEAT: Hold on the moment after Garrow's jaws stop. Bram remains close, visibly trembling but refusing to retreat. The eldest lamb, Pip, carefully nudges a small wicker bowl across the stone floor. Inside are dried berries, sweet roots, and a little mound of clover. Pip pushes the bowl toward Garrow, then steps back. VISUAL: Close-up of the bowl sliding across the flagstones, then Garrow's stunned expression. LIGHTING: Warm highlights on the food against the cool stone. STYLE: cinematic photorealistic short film, 35mm lens, shallow depth of field, natural film grain, consistent color grade. No text, no subtitles, no captions, no logos, no watermarks. Preserve the same characters, wardrobe, props, environment, and color grade throughout the film."),
    make_scene(24, "Scene 24: The Hum That Calmed the Wolf",
        "Oona hums, ripples on the basin water.",
        "Oona, the quiet lamb, lowers her head and begins humming. Show gentle ripples moving across the basin water. The note travels through the courtyard as faint silver-blue vibrations in the air. Garrow's tense muscles slowly loosen. His gaze shifts from the lambs to the bowl. His breathing begins to settle.",
        "Close-up of Oona, then a smooth pan across the rippling water toward Garrow.",
        "Subtle silver-blue highlights, peaceful moonlight.",
        "Delicate nonverbal humming, soft water resonance, fading tension.",
        "Create an 8-second cinematic shot for the short film \"HOLLOWTHORN — THE GUARDIAN OF THE FLEECE\". STORY BEAT: Oona, the quiet lamb, lowers her head and begins humming. Show gentle ripples moving across the basin water. The note travels through the courtyard as faint silver-blue vibrations in the air. Garrow's tense muscles slowly loosen. His gaze shifts from the lambs to the bowl. His breathing begins to settle. VISUAL: Close-up of Oona, then a smooth pan across the rippling water toward Garrow. LIGHTING: Subtle silver-blue highlights, peaceful moonlight. STYLE: cinematic photorealistic short film, 35mm lens, shallow depth of field, natural film grain, consistent color grade. No text, no subtitles, no captions, no logos, no watermarks. Preserve the same characters, wardrobe, props, environment, and color grade throughout the film."),
    make_scene(25, "Scene 25: The First Meal",
        "Garrow eats and drinks from the basin, his expression changes.",
        "Garrow slowly lowers his muzzle toward the bowl. He drinks from the clear basin, then eats the dried berries, roots, and clover. His body trembles with weakness. The lambs wait nearby without approaching too quickly. Show his expression gradually changing from desperation to quiet disbelief.",
        "Intimate close-ups of the bowl, water, and Garrow's face.",
        "Soft moonlight reflecting across the basin.",
        "Gentle water, quiet eating, soft ambient melody.",
        "Create an 8-second cinematic shot for the short film \"HOLLOWTHORN — THE GUARDIAN OF THE FLEECE\". STORY BEAT: Garrow slowly lowers his muzzle toward the bowl. He drinks from the clear basin, then eats the dried berries, roots, and clover. His body trembles with weakness. The lambs wait nearby without approaching too quickly. Show his expression gradually changing from desperation to quiet disbelief. VISUAL: Intimate close-ups of the bowl, water, and Garrow's face. LIGHTING: Soft moonlight reflecting across the basin. STYLE: cinematic photorealistic short film, 35mm lens, shallow depth of field, natural film grain, consistent color grade. No text, no subtitles, no captions, no logos, no watermarks. Preserve the same characters, wardrobe, props, environment, and color grade throughout the film."),
    make_scene(26, "Scene 26: Warmth Against the Cold",
        "Garrow collapses, lambs curl against his body.",
        "Garrow's legs finally give way. He collapses beside the basin. The lambs approach carefully and curl against his body. Bram tucks himself beneath Garrow's chin. Oona settles near his forepaws. Pip rests against the wolf's belly, where his breathing is shallowest. Their white fleece contrasts with Garrow's dark, frost-covered coat.",
        "Slow circular movement around the group, ending in a close-up of their peaceful arrangement.",
        "Soft moonlight, delicate warmth, gentle shadows.",
        "Soft fleece movement, steady breathing, delicate music.",
        "Create an 8-second cinematic shot for the short film \"HOLLOWTHORN — THE GUARDIAN OF THE FLEECE\". STORY BEAT: Garrow's legs finally give way. He collapses beside the basin. The lambs approach carefully and curl against his body. Bram tucks himself beneath Garrow's chin. Oona settles near his forepaws. Pip rests against the wolf's belly, where his breathing is shallowest. Their white fleece contrasts with Garrow's dark, frost-covered coat. VISUAL: Slow circular movement around the group, ending in a close-up of their peaceful arrangement. LIGHTING: Soft moonlight, delicate warmth, gentle shadows. STYLE: cinematic photorealistic short film, 35mm lens, shallow depth of field, natural film grain, consistent color grade. No text, no subtitles, no captions, no logos, no watermarks. Preserve the same characters, wardrobe, props, environment, and color grade throughout the film."),
    make_scene(27, "Scene 27: A Sleep Without the Gorge",
        "Garrow lies peacefully beside the basin, surrounded by sleeping lambs.",
        "Garrow lies peacefully beside the basin, surrounded by the sleeping lambs. His eyes slowly close. A faint reflection of the Northern Gorge appears in the water, then disappears as the surface becomes still. The camera rises above the group, showing the sanctuary protecting them beneath its broken vault.",
        "Slow overhead pullback.",
        "Gentle moonlight, calm shadows, still water.",
        "Gentle breathing, faint nighttime ambience, soft musical resolution.",
        "Create an 8-second cinematic shot for the short film \"HOLLOWTHORN — THE GUARDIAN OF THE FLEECE\". STORY BEAT: Garrow lies peacefully beside the basin, surrounded by the sleeping lambs. His eyes slowly close. A faint reflection of the Northern Gorge appears in the water, then disappears as the surface becomes still. The camera rises above the group, showing the sanctuary protecting them beneath its broken vault. VISUAL: Slow overhead pullback. LIGHTING: Gentle moonlight, calm shadows, still water. STYLE: cinematic photorealistic short film, 35mm lens, shallow depth of field, natural film grain, consistent color grade. No text, no subtitles, no captions, no logos, no watermarks. Preserve the same characters, wardrobe, props, environment, and color grade throughout the film.")
]

# Extend the plan's scenes
plan["scenes"].extend(scenes_18_27)

with open('hollowthorn_plan.json', 'w') as f:
    json.dump(plan, f, indent=2)

print(f"Plan updated with {len(plan['scenes'])} scenes (added scenes 18-27)")