# Existing Agent Feature Map

Status legend: **Ported** = behaviour preserved in the platform; **Replaced** =
superseded by a safer/multi-user implementation; **Gated** = implemented but
disabled pending authorization.

## Planning

| Old behaviour | New implementation | Status |
| --- | --- | --- |
| `build_plan` from script | `agent/planner/planner.py::build_plan` | Ported |
| Pollinations LLM planning | `agent/planner/llm.py` (optional via `PLANNER_LLM_ENABLED`) | Ported, opt-in |
| Deterministic fallback | `agent/planner/deterministic.py` | Ported |
| Script analysis / character names | `agent/planner/analyzer.py` | Ported |
| Scene prompt composition | `compose_scene_prompt` logic in deterministic planner | Ported |
| Plan JSON files + `latest` pointer | DB `projects` / `scenes` + `plan_revision` | Replaced |
| Scene count limit 20 | `MAX_SCENES_PER_PROJECT` (default 20) | Ported |

## Generation

| Old behaviour | New implementation | Status |
| --- | --- | --- |
| TAAFT login with persistent profile | Per-user encrypted Playwright storage state | Gated |
| Submit with tier/orientation/enhance | `VideoProvider.submit_generation` | Gated (TAAFT), Ported (simulated) |
| Poll generation status | `get_generation_status` + job heartbeats | Ported |
| Extend from previous clip | `extend_generation` + parent generation id | Ported |
| Last-frame continuity | `extract_last_frame` + `parent_generation_id` | Ported |
| Reference image | `reference_image_path` | Ported |
| Download clips | `download_generation` with retries | Ported |
| Resume after interruption | DB jobs, scene checkpoints, idempotency keys | Replaced/improved |
| Simulated test provider | `agent/providers/simulated.py` (real MP4 output) | New |

## Assembly and validation

| Old behaviour | New implementation | Status |
| --- | --- | --- |
| FFmpeg stream-copy concat with re-encode fallback | `concat_normalized` | Ported |
| No normalisation | `normalize_clip` (resolution, fps, audio) | Improved |
| No transitions | `concat_with_crossfade` (optional) | New |
| No audio bed | `mix_audio` (music/voiceover) | New |
| No clip validation | `validate_clip` / `validate_final` | New |
| No checksums | SHA-256 per clip and final video | New |

## Platform features added

- Multi-user accounts, sessions, CSRF, rate limiting and audit events.
- Per-user project, media keys and provider account isolation.
- DB-backed durable queue with leases, heartbeats, retries, idempotency and
  crash recovery.
- Cloud worker and local execution modes over one shared pipeline.
- Local execution tokens (hashed, revocable, per-user).
- Server-side re-validation of every uploaded local clip and final video.
- Signed streaming/download URLs with Range support.
- Notifications, WebSocket ticket endpoint, usage and storage quotas.
- Next.js PWA frontend (dashboard, wizard, project timeline, scene editing,
  approval, pause/resume/cancel/retry, video library, settings).
- Automated tests covering security, isolation and both execution modes.

## Explicit non-goals / preserved limits

- No bypass of provider protections, paywalls, quotas or ToS.
- No sharing of browser profiles or sessions between users.
- TAAFT remains disabled until prior written authorization is obtained.
- The original `taaft_agent.py` is kept, unmodified, as historical reference.
