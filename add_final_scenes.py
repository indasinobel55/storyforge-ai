import json

# Read existing plan
with open('hollowthorn_plan.json') as f:
    plan = json.load(f)

# Define scenes 52-54
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

# Scene 52-54
scenes_52_54 = [
    make_scene(52, "Scene 52: Three Voices, One Magic",
        "Oona, Pip, and Bram hum/bleat together, silver light stirs in the Bone Barrow cracks.",
        "At the entrance of the Bone Barrow, Oona begins humming. Pip stands beside her, his head raised. Bram, trembling behind the altar, joins with a thin, wavering nonverbal bleat. Three voices find the same pitch. The sound travels through the ancient bones. Silver light begins stirring in the cracks between the stones. Garrow and Aethelgard remain in the foreground.",
        "Close-ups of the three lambs, followed by a sweeping shot across the glowing cracks.",
        "Silver-blue light emerging from deep darkness.",
        "Layered nonverbal humming and bleating, subtle magical resonance, stone vibrations.",
        "Create an 8-second cinematic shot for the short film \"HOLLOWTHORN — THE GUARDIAN OF THE FLEECE\". STORY BEAT: At the entrance of the Bone Barrow, Oona begins humming. Pip stands beside her, his head raised. Bram, trembling behind the altar, joins with a thin, wavering nonverbal bleat. Three voices find the same pitch. The sound travels through the ancient bones. Silver light begins stirring in the cracks between the stones. Garrow and Aethelgard remain in the foreground. VISUAL: Close-ups of the three lambs, followed by a sweeping shot across the glowing cracks. LIGHTING: Silver-blue light emerging from deep darkness. STYLE: cinematic photorealistic short film, 35mm lens, shallow depth of field, natural film grain, consistent color grade. No text, no subtitles, no captions, no logos, no watermarks. Preserve the same characters, wardrobe, props, environment, and color grade throughout the film."),
    make_scene(53, "Scene 53: The Weaver-Fleece",
        "Silver threads slip from Bram's flank, weave around Aethelgard and Garrow, healing them.",
        "A silver thread slips from Bram's wounded flank, not like blood but like a strand of moonlight. More threads follow, weaving an intricate luminous pattern above the altar. The threads lash around Aethelgard's limbs, weakening the furnace glow. One reaches Garrow and passes through his chest like cold water. His broken ribs draw together. Fine silver filaments spread across his grey coat, forming a delicate mantle over his shoulders and back. Garrow rises.",
        "Slow magical reveal, following the threads before moving into a close-up of Garrow rising.",
        "Brilliant but restrained silver light, glowing bone cracks, fading furnace orange.",
        "Delicate magical chimes, threads weaving, tiger's weakened growl, rising orchestral swell.",
        "Create an 8-second cinematic shot for the short film \"HOLLOWTHORN — THE GUARDIAN OF THE FLEECE\". STORY BEAT: A silver thread slips from Bram's wounded flank, not like blood but like a strand of moonlight. More threads follow, weaving an intricate luminous pattern above the altar. The threads lash around Aethelgard's limbs, weakening the furnace glow. One reaches Garrow and passes through his chest like cold water. His broken ribs draw together. Fine silver filaments spread across his grey coat, forming a delicate mantle over his shoulders and back. Garrow rises. VISUAL: Slow magical reveal, following the threads before moving into a close-up of Garrow rising. LIGHTING: Brilliant but restrained silver light, glowing bone cracks, fading furnace orange. STYLE: cinematic photorealistic short film, 35mm lens, shallow depth of field, natural film grain, consistent color grade. No text, no subtitles, no captions, no logos, no watermarks. Preserve the same characters, wardrobe, props, environment, and color grade throughout the film."),
    make_scene(54, "Scene 54: The Broken Alpha and the First Dawn",
        "Garrow pins Aethelgard against the altar, the talisman cracks, curse breaks. The forest receives its first true dawn. End card reveals HOLLOWTHEORN - THE GUARDIAN OF THE FLEECE.",
        "Begin with Garrow pinning Aethelgard against the altar. His jaws are near the tiger's throat, but he does not bite. Silver light reveals the tiger's true face: a familiar muzzle, a scar above the brow, and a notched left ear. The glowing stripes fade, revealing the exhausted eyes of Aethel, the old Alpha of Garrow's ancestral pack. Garrow turns his attention to the rune talisman embedded in Aethel's chest. Its markings match the rusted charm hanging from Garrow's collar. The silver mantle brightens. Garrow presses his teeth against the talisman. It cracks, and a wave of silver light unbinds the curse. The snare cables fall away. Aethel's body dissolves into silver-lit ash, rising through the ribs of the Bone Barrow. In the same continuous visual passage, the great roots fall silent. Thorn walls open. Black branches reveal pale wood, white lilies emerge, and water runs clear. Bram limps from behind the altar. Garrow lowers his head so Bram can press his forehead against the wolf's muzzle. Pip stands on one side and Oona on the other. Oona places a small white flower behind Garrow's torn left ear. The silver mantle rests gently over his shoulders as the first golden dawn enters the newly opened forest.",
        "Intimate close-up of the revealed Alpha, transition to the talisman breaking, then a wide rising shot of the restored forest and reunited family.",
        "Silver magic transitions into warm golden dawn, pale wood, fresh green, white lilies, and clear water.",
        "Talisman cracking, chains breaking, silver ash rising, roots becoming still, gentle water, warm orchestral resolution.",
        "Create an 8-second cinematic shot for the short film \"HOLLOWTHORN — THE GUARDIAN OF THE FLEECE\". STORY BEAT: Begin with Garrow pinning Aethelgard against the altar. His jaws are near the tiger's throat, but he does not bite. Silver light reveals the tiger's true face: a familiar muzzle, a scar above the brow, and a notched left ear. The glowing stripes fade, revealing the exhausted eyes of Aethel, the old Alpha of Garrow's ancestral pack. Garrow turns his attention to the rune talisman embedded in Aethel's chest. Its markings match the rusted charm hanging from Garrow's collar. The silver mantle brightens. Garrow presses his teeth against the talisman. It cracks, and a wave of silver light unbinds the curse. The snare cables fall away. Aethel's body dissolves into silver-lit ash, rising through the ribs of the Bone Barrow. In the same continuous visual passage, the great roots fall silent. Thorn walls open. Black branches reveal pale wood, white lilies emerge, and water runs clear. Bram limps from behind the altar. Garrow lowers his head so Bram can press his forehead against the wolf's muzzle. Pip stands on one side and Oona on the other. Oona places a small white flower behind Garrow's torn left ear. The silver mantle rests gently over his shoulders as the first golden dawn enters the newly opened forest. VISUAL: Intimate close-up of the revealed Alpha, transition to the talisman breaking, then a wide rising shot of the restored forest and reunited family. LIGHTING: Silver magic transitions into warm golden dawn, pale wood, fresh green, white lilies, and clear water. STYLE: cinematic photorealistic short film, 35mm lens, shallow depth of field, natural film grain, consistent color grade. No text, no subtitles, no captions, no logos, no watermarks. Preserve the same characters, wardrobe, props, environment, and color grade throughout the film.")
]

plan["scenes"].extend(scenes_52_54)

# Update sessions to have 54 scenes (14 sessions of 4, plus last with 2)
sessions = []
for i in range(0, 54, 4):
    session_scenes = plan["scenes"][i:i+4]
    sessions.append({
        "name": f"Session {len(sessions) + 1}",
        "scene_indices": [s["index"] for s in session_scenes],
        "status": "pending"
    })

plan["sessions"] = sessions

with open('hollowthorn_plan.json', 'w') as f:
    json.dump(plan, f, indent=2)

print(f"Plan updated with {len(plan['scenes'])} scenes (added scenes 52-54)")
print(f"Total sessions: {len(plan['sessions'])}")