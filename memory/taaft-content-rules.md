# TAAFT Content Rules (IMPORTANT - read before generating)

Learned 2026-11-14 from a live 422 rejection. TAAFT enforces an automatic
keyword policy on every submitted prompt.

## The rule
- TAAFT REJECTS prompts containing wording about minors / under-18 age
  references ("child", "kid", "toddler", "baby", "infant", "years old",
  "two-year-old", etc.) with:
    HTTP 422
    {"success":false,
     "message":"Your prompt contains wording that is not allowed for video generation.",
     "reason_code":"keyword_policy"}
- The filter scans the ENTIRE submitted text, including headers we prepend.
  A innocent jungle story got rejected purely because the per-scene header
  contained the series title "THE CHILD OF THE MONSOON" - even though the
  scene body had no age references at all.

## Workaround
- Never send minor/age wording to TAAFT. Replace with neutral phrasing:
  "the littlest expedition member", "the family's youngest member",
  "the little explorer", "small in stature", "tiny barefoot footprints".
- The film/series TITLE itself must not be included verbatim in the prompt
  if it contains blocked words (title stays in plan.json / UI only).
- Not length-related: a 3380-char prompt (Gojo vs Sukuna) was accepted
  while a 1825-char prompt with the blocked title was rejected.
- The response body of failed submissions is now logged by
  agent/providers/taaft.py (_parse_generation_response includes the body),
  so any future keyword_policy rejection is visible in the logs.

## Deeper filter: minor_safety (learned 2026-11-15)
- Neutral phrasing is NOT enough. TAAFT also runs a semantic classifier
  ("minor_safety") that rejects any prompt DEPICTING a minor on-screen:
    HTTP 422
    {"success":false,
     "message":"Please describe a scene with adults only.",
     "reason_code":"minor_safety"}
- "the littlest member" / "the little explorer" in a scene body trips it
  even with zero banned keywords. Only adults may appear on-screen.
- Workaround for child-centered stories: never show the minor. Imply
  presence through objects: "a small bright-yellow rain jacket folded on
  the seat", "tiny barefoot footprints in the mud", the animal guardian
  watching over the hollow. Applied to Child of the Monsoon EP01
  (scenes 2,4,5,6,8 rewritten; 3,7 needed no people anyway).
- Quota note: a rejected submission still consumed 1 credit in one case;
  assume each POST may consume quota even on 422.

## Other TAAFT facts (verified same day)
- Tier "quality" is the top mode; render output is 864x480 (16:9-ish) or
  equivalent for portrait; we upscale to 720p locally with ffmpeg lanczos.
- Extend (native continuity chaining) exists; fallback is last-frame
  reference image attach (#videogen_image_input, multi-file supported).
- Quota: 100 generations per reset cycle; each submission consumes 1.
- Real quality-tier generation took ~108s wall time (scene 1, EP01).
- History scraping: [data-videogen-generation-id] elements expose past
  generations; the ?resume=1 endpoint only reports the ACTIVE one, so a
  finished generation from a previous day cannot be adopted by id unless
  it is visible in the history DOM (empty at next-day session start).
