# AI Video Studio — Autonomous Video Agent Plan

**Project:** AI Video Studio
**Directory:** `C:\AI_Video_Studio`
**Date:** 2026-11-08
**Session goal:** turn the existing platform into an autonomous script-to-video production pipeline with real visual continuity, a live agent activity window, and a safe public deployment surface.

This plan is written after inspecting the existing backend, worker, providers, storage, queue, planning, schemas, and frontend. It is intentionally incremental: it extends the current `GenerationWorker` and provider contract rather than replacing them.

---

## 0. Existing architecture understood

### What already exists
- FastAPI backend with session cookies + CSRF, scoped local-execution tokens, signed media URLs, health/config endpoints.
- SQLite/Postgres async models: `users`, `projects`, `scenes`, `characters`, `generation_attempts`, `jobs`, `videos`, `notifications`, `provider_accounts`, `local_execution_tokens`.
- Database-backed job queue: `PLAN`, `GENERATE`, `ASSEMBLE`, leases, heartbeats, retry with backoff, cancel, reclaim.
- Two execution modes: `EXECUTION_MODE=cloud` (in-process worker) and `EXECUTION_MODE=local` (scoped bearer tokens, server-side media revalidation).
- Provider abstraction: `VideoProvider` with `submit_generation`, `get_generation_status`, `extend_generation`, `download_generation`, optional `wait_for_generation` and `find_generation_by_idempotency`.
- Simulated provider produces real MP4s via FFmpeg; TAAFT provider is gated behind `TAAFT_ENABLED`.
- Planning pipeline: deterministic planner present; LLM planner opt-in; scene model already stores prompt, camera, lighting, continuity, narration, dialogue, status, generation id, last frame path, checksum, actual duration.
- FFmpeg pipeline: `normalize_clip`, `concat_normalized`, `concat_with_crossfade`, `mix_audio`, `extract_last_frame`, `extract_thumbnail`, `probe_video`, validator for clips and final video.
- Local-execution protocol supports scene checkpointing, scene video/last-frame uploads, final upload, job heartbeat/complete/fail.
- Frontend has dashboard, project timeline, scene editing/retry, final preview/download, PWA files, responsive layout.

### What does not yet exist
- Autonomous visual-continuity loop:
  - last-frame extraction exists, but there is no stored “last analyzed frame” workflow and no continuation-passage generation step.
  - Scene prompts currently include generic continuity text, not an image-derived continuation passage from the previous actual frame.
- Vision model adapter:
  - No `agent/vision.py` or similar module exists.
  - No configured vision model provider, local or remote, is wired in today.
- Live agent activity stream:
  - WebSocket endpoint exists for project snapshot polling, but there is no persisted activity-event model, no activity API, and no frontend activity panel.
- Deployment of a genuinely independent persistent cloud worker and a public HTTPS URL has not been completed.

### Existing surfaces we should reuse
- `workers/generation_worker.py:_process_generate` is the right place to extend the scene loop.
- `Scene` already has `last_frame_path`, `prompt`, `continuity`, `parent_generation_id`, `attempt_count`, and `generation_id`.
- `GenerationAttempt` already gives us per-scene audit records.
- `VideoProvider.extend_generation` already exists for continuations; the simulated provider already supports `reference_image_path`.
- `agent/core/util.extract_last_frame` already extracts the final frame with `av`.
- `backend/app/services/project_service.resolve_provider` already builds the provider per user/account.
- `backend/app/api/realtime_api.py` already shows the pattern for user-scoped realtime and ticket auth.
- `backend/app/api/videos.py` already handles owner-authorized streaming and downloads.

---

## 1. Scope of this mission

### In scope
- Autonomous script breakdown into scenes targeting **8 seconds each**, including the final scene, with a richer per-scene spec and optional plan review.
- Autonomous visual continuity loop: generate → download → validate → extract last frame → analyze image → write continuation → build next prompt using that continuation → generate next scene.
- A configurable vision model adapter with local-first support and an explicit unavailable fallback.
- Live agent activity panel backed by persisted activity events and a user-scoped event stream.
- Stronger multi-user isolation on every new endpoint, file route, and event stream.
- New deterministic and simulated tests for the continuity pipeline and the activity system.
- Updated deployment documentation and an honest deployment-verification report.

### Out of scope unless explicitly approved later
- Real TAAFT integration or real vision-model API keys.
- Deploying a remote persistent cloud worker if the environment cannot host one for free.
- Any change that disables local execution or weakens existing auth/isolation.

---

## 2. Design principles

1. **Continuity must actually be used.** The continuation passage and frame analysis must be included in the provider prompt sent for the next scene, not only saved to the database.
2. **Vision is optional but not silent.** If no vision model is configured or available, the pipeline must record that clearly and must not pretend it analyzed an image. It may fall back to a documented text-only continuity mode only if an explicit fallback is configured.
3. **Autonomy is the default.** Once the user clicks Generate, the platform should run the whole pipeline without requiring per-scene approval. An optional review step may exist before generation starts.
4. **Preserve what works.** Do not rewrite planning, queue, storage, auth, or assembly just to add continuity. Extend the current worker loop and provider contract.
5. **Isolation first.** Every new API, stream, and file route must be scoped to the owning user.
6. **Honest deployment.** Only claim online + independent worker + real vision model + real TAAFT when they are actually verified.

---

## 3. Data model additions

### Recommended new/extended fields
I do not plan to add a separate full rewrite of models. I plan to use existing columns where possible and add only what the continuity loop genuinely needs.

Likely additions:
- `Scene.analyzed_frame_path` or reuse `last_frame_path` semantics with an extra analyzed artifact path.
- `Scene.frame_analysis` JSON/text: structured or free-text analysis of the previous scene’s final frame.
- `Scene.continuation_passage` text: the agent-written continuation used in the next prompt.
- `Scene.final_prompt` or store the exact prompt actually sent in `GenerationAttempt.raw` or a new scene-level field.
- `Activity` model:
  - `id`, `user_id`, `project_id`, `scene_id` optional, `kind`, `message`, `status`, `meta` JSON, timestamps.
  - Indexed by `(user_id, project_id, created_at)` for replay.

I will finalize fields after re-reading `backend/app/models.py` and `agent/scenes/spec.py` and after checking the existing scene schema more closely.

---

## 4. Phase-by-phase implementation plan

### Phase 1 — Richer script-to-scene breakdown
Goal: accept one complete script and produce sequential 8-second scenes with the requested detail.

Implementation direction:
- Extend planning so each scene record carries:
  - scene number
  - target duration, always 8s in the default autonomous workflow
  - original script segment
  - visual description
  - character descriptions
  - character actions
  - environment
  - camera framing and movement
  - lighting and atmosphere
  - dialogue/audio instructions when applicable
  - generation prompt
  - continuity requirements from previous scene
  - expected ending state for the next scene
- Planning must not blindly split by fixed word count; it should be based on how much action/dialogue fits into 8 seconds.
- Keep deterministic planner as the default; allow LLM planner when configured.
- Optionally store a plan-review state, but default workflow is autonomous after Generate.

Tests:
- deterministic breakdown test
- scene duration planning test
- character consistency data test

### Phase 2 — Visual continuity engine
Goal: generate scenes sequentially using the actual previous scene’s last frame.

Implementation direction:
- After a scene succeeds, extract last frame with `extract_last_frame`.
- Save the extracted frame securely in project storage.
- Send the frame to the configured vision adapter.
- Store the vision analysis.
- Generate a continuation passage from the analysis + script context.
- Store the continuation passage.
- For the next scene, build the prompt from:
  - next scene’s planned description
  - original script segment
  - project-level character/style spec
  - previous frame analysis
  - continuation passage
  - explicit continuity instructions
- Send that combined prompt to the provider.
- Repeat using the immediately preceding scene’s frame for every later scene.

Failure handling:
- If frame extraction fails, record it and decide whether to retry the scene or proceed with a documented degraded continuity mode.
- If vision analysis fails and no fallback is configured, mark continuity as blocked and do not silently skip it.
- If continuation generation fails, fail the current scene or retry with backoff; do not corrupt completed scenes.

Tests:
- actual final-frame extraction test
- vision-model analysis test using a test image
- continuation passage generation test
- scene 2 prompt contains the continuation passage test
- scene 3 uses scene 2’s last frame test

### Phase 3 — Generation orchestration
Goal: sequential, resumable, safe generation loop.

Implementation direction:
- One scene at a time per project by default.
- Persist every stage transition.
- Resume from last successfully completed stage after worker restart.
- Do not regenerate completed scenes unnecessarily.
- Retry transient failures with bounded policy.
- Separate provider submission failures from download/assembly failures.
- Support cancellation, provider timeout, missing/corrupt output, failed frame extraction, vision-model errors, continuity-generation errors, quota exhaustion.
- Make stage execution idempotent and recoverable.

This is largely an extension of the existing worker, but I will make the continuity stages explicit in the job/lifecycle reporting and in the activity stream.

Tests:
- sequential generation test
- worker crash and recovery test
- duplicate-generation prevention test

### Phase 4 — Live agent activity window
Goal: a polished panel that shows real autonomous-agent activity.

Implementation direction:
- Add an `Activity` model and persist events as the worker moves through stages.
- Expose a user-scoped activity API:
  - list activities for a project
  - replay since a cursor/timestamp
- Expose a realtime path:
  - either WebSocket or SSE, chosen based on what fits the existing stack best
  - in-process fan-out plus DB replay for missed events is a reasonable default here because the current project already uses an in-process WebSocket manager and DB-backed state
- Frontend panel:
  - current project
  - current scene number and total scenes
  - current operation
  - actual progress
  - completed stages
  - pending stages
  - errors and retry status
  - timestamps
  - overall job status
  - compact view + expandable detailed log
  - responsive desktop/mobile

Rules:
- Do not fabricate percentages.
- Do not mark an operation complete until backend confirms it.
- User A must not subscribe to user B’s stream.

Tests:
- activity event persistence test
- activity stream reconnection test
- multi-user activity isolation test

### Phase 5 — Final video assembly
Goal: assemble and validate the final MP4 with strong integrity checks.

Current code already does most of this. I will ensure:
- all expected scenes exist and are in sequence
- each clip is validated before assembly
- dimensions/frame rate/codecs/audio are normalized where necessary
- assembly avoids black frames and audio corruption where possible
- final MP4 is validated and checksummed
- final video is saved to private storage
- project and video library are updated

No major rewrite expected here; mainly verification and hardening.

Tests:
- final FFmpeg assembly test
- final video validation test

### Phase 6 — Multi-user security
Goal: preserve and extend isolation.

Implementation direction:
- Reuse `owned_project`, `require_user`, and signed media token patterns.
- Ensure new activity API, activity stream, frame-analysis assets, continuation artifacts, and any new file route are user-scoped.
- Never expose one user’s provider session or artifacts to another user.
- Do not collect TAAFT credentials in website forms.

Tests:
- private asset access test
- activity isolation test
- continue existing multi-user isolation test

### Phase 7 — TAAFT integration safety
Goal: preserve the existing safe posture.

Implementation direction:
- Keep TAAFT gated.
- Keep simulated provider fully functional.
- Do not claim cloud TAAFT works without authorization.
- Document any research findings, but do not bypass protections or quotas.

### Phase 8 — Cloud architecture and public website
Goal: make the site reachable over HTTPS where genuinely possible, and be honest about what is not yet independently hosted.

Implementation direction:
- Prepare deployment config for frontend + backend + DB + storage + worker.
- Keep local mode functional.
- Document the free-tier choices from `CLOUD_SERVICE_COMPARISON.md`.
- Do not claim a persistent cloud worker is verified unless one is actually deployed and tested.

### Phase 9 — Friend access
Goal: safe invite/registration-based multi-user access.

Implementation direction:
- Provide registration/login, private dashboards, project creation, script submission, scene progress, final preview/download, session management, and user isolation.
- If email invitations are not configured, prefer a safe registration/invite-code flow over pretending invitations were sent.
- Videos remain private by default.

### Phase 10 — Testing
Goal: cover the new autonomous pipeline and activity system.

I will add tests covering the Phase 10 list in the mission text, using simulated providers and a test image for vision-analysis stubs/fallbacks as needed.

### Phase 11 — Deployment and final acceptance
Goal: run the verification gates and write honest reports.

Deliverables:
- `docs/AUTONOMOUS_VIDEO_AGENT_PLAN.md`
- `docs/SCENE_CONTINUITY_ENGINE.md`
- `docs/AGENT_ACTIVITY_SYSTEM.md`
- `docs/PUBLIC_DEPLOYMENT_GUIDE.md`
- `docs/DEPLOYMENT_VERIFICATION_REPORT.md`

---

## 5. What I will implement first

1. A richer scene spec and deterministic 8-second breakdown path.
2. A vision adapter interface plus a simulated/test double and an explicit unavailable fallback.
3. The continuity loop hooks in the worker: extract last frame, analyze, write continuation, build next prompt, include continuation in the actual provider prompt.
4. Activity model + API + realtime path + frontend panel.
5. Hardening and isolation checks for all new surfaces.
6. Tests for breakdown, continuity, activity, isolation, recovery, and final assembly.

---

## 6. Known constraints for this environment

- No system `ffmpeg` on PATH; only `imageio_ffmpeg` binary is available. The backend already handles this, but any new CLI tooling must use the same binary or add it to PATH.
- No Docker here, so Docker-based deployment verification will remain BLOCKED unless run elsewhere.
- No real vision model API key and no real TAAFT authorization in this session.
- Frontend is Next.js; backend is FastAPI; realtime currently uses an in-process WebSocket manager. New live updates should extend that pattern unless SSE is clearly better.
- The worker is currently in-process for cloud mode in local verification; an independently hosted persistent cloud worker is a deployment claim, not something already proven here.

---

## 7. Success criteria

- One script produces sequential 8-second scenes with the richer spec.
- Scene 2’s actual provider prompt contains Scene 1’s generated continuation passage.
- Scene 3 uses Scene 2’s last frame, not Scene 1’s.
- The activity panel shows real operations only and isolates users.
- Existing local execution, multi-user isolation, and simulated E2E still pass.
- Final reports clearly separate implemented, locally tested, simulated-tested, published online, real-vision-verified, real-TAAFT-authorized, and blocked items.
