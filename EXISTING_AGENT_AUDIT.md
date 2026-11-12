# Existing Agent Audit — `taaft_agent.py`

Date: 2026-11-08
Scope: read-only inventory of the pre-existing single-user agent before the
platform rewrite. The original file is preserved at the repository root and was
not modified.

## Summary

`taaft_agent.py` is a standalone Python CLI that turns a story into a multi-scene
video by driving the TAAFT video generator in a persistent Playwright Chromium
profile, downloading clips, optionally extending them, extracting the last frame
for continuity, and concatenating with FFmpeg. It is a single-user, local-only
tool with no database, API, authentication, queue, isolation or deployment story.

## Commands

| Command | Behaviour |
| --- | --- |
| `login` | Opens the TAAFT generator with a persistent Chrome profile and waits for an interactive login. |
| `plan` | Builds a scene plan from a script (Pollinations LLM with deterministic fallback) and writes it under `plans/`. |
| `run` | Loads the latest plan, generates/extend scenes sequentially, downloads clips, extracts last frames and resumes from plan state. |
| `status` | Prints account, quota and active generation details via the browser session. |
| `concat` | Concatenates downloaded scene clips into a final MP4. |

## Internals

- **Classes**: `AgentError`, `LoginRequired`, `GenerationError`, `TaaftAgent`.
- **Planning**: `build_plan`, `llm_plan`, `fallback_plan`, `pollinations_chat`,
  `compose_scene_prompt`, `build_sessions`, `extract_json_object`.
- **Utilities**: `normalize_text`, `split_sentences`, `slugify`, `redact`, JSON
  helpers, `probe_video`, `extract_last_frame`, `find_ffmpeg`, `concat_videos`.
- **Browser automation**: persistent context with Chrome, login detection,
  generator navigation, tier/orientation/enhance controls, reference image submit,
  generation polling, extend flow, downloads, active generation via internal JSON.
- **Resume state**: `plans/latest`-style pointers and per-scene `last_frame`.
- **Limits**: `MAX_SEGMENTS = 20`; sequential generation; outputs under `outputs/`.

## Weaknesses found

1. Single shared Chrome profile (`PROFILE_DIR`) — no per-user isolation, no
   encrypted session storage, no account separation.
2. No authentication, authorisation, CSRF, rate limits or audit trail.
3. No durable queue: interruption leaves manual state files; no leases or retries.
4. Hard-coded provider endpoints and internal API probing; brittle to UI changes.
5. No validation that downloaded clips are decodable; only basic concatenation.
6. Secrets and session material live on disk in the browser profile.
7. No storage quotas, usage tracking or multi-tenant media paths.
8. No health checks, deployment packaging or tests.

## Terms-of-service issue

The provider's Terms of Service (updated 2026-03-19) prohibit automated access and
security circumvention without prior written consent. The original agent is exactly
such automation. It is therefore preserved as a reference implementation only and
is **not enabled** in the platform. See `TAAFT_INTEGRATION_FEASIBILITY.md`.

## Reuse decisions

| Existing capability | New location |
| --- | --- |
| Prompt composition + deterministic fallback | `agent/planner/deterministic.py`, `agent/planner/llm.py` |
| Scene/character data model | `agent/scenes/spec.py` |
| TAAFT Playwright flow | ported to `agent/providers/taaft.py` behind a hard gate |
| Probe / last frame / slug / redact | `agent/core/util.py` |
| FFmpeg concat | expanded into `agent/postproduction/ffmpeg_tools.py` + `assemble.py` |
| Resume state | replaced by DB jobs + scene checkpoints (`generation_attempts`) |
| CLI entry points | preserved logic; platform CLIs are `workers/runner.py` and `local_agent` |

The original CLI remains runnable for historical reference, but use of real TAAFT
automation remains at the operator's legal risk and is disabled by default.
