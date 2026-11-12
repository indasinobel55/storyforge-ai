# Cloud Architecture

## Topology

```
Browser (Next.js PWA)
   │  HTTPS, HttpOnly session cookie, CSRF header
   ▼
FastAPI API ──────────────► Postgres/SQLite (users, projects, scenes, jobs, videos)
   │                              ▲
   │ signed media URLs            │ leases / checkpoints
   ▼                              │
Object storage ◄──── Cloud worker (PLAN → GENERATE → ASSEMBLE)
   ▲
   │ uploads + final MP4
Local agent (optional, EXECUTION_MODE=local)
   │  claims only its user's jobs via scoped bearer tokens
   └────────────────────────────────────────────────────────────
```

Two execution modes share one code path:

- **cloud**: `workers/runner.py` claims any queued job.
- **local**: `python -m local_agent` claims jobs for one user token; the server
  re-validates every uploaded asset.

The mode is a backend setting (`EXECUTION_MODE`) and is displayed in the UI.
Cloud and local workers must not run against the same deployment at once for the
same jobs; the API refuses local claims unless the mode is `local`, and the cloud
worker refuses to run when the mode is not `cloud`.

## Components

| Component | Responsibility |
| --- | --- |
| API (`backend/app`) | Auth, projects, scenes, approvals, job enqueue, signed media, local execution protocol, health/config, WebSocket tickets |
| Queue (`services/queue.py`) | Idempotent enqueue, conditional claim with lease, heartbeat, retry with exponential backoff, cancellation |
| Planning (`services/planning_service.py`) | Deterministic/LLM planning, scene regeneration, approval |
| Project service | Provider resolution, per-account lock, progress, notifications, usage, storage keys |
| Agent core (`agent/`) | Planner, provider contract, simulated/TAAFT adapters, FFmpeg assembly, validation |
| Cloud worker (`workers/`) | Executes PLAN/GENERATE/ASSEMBLE, per-scene retries, uploads, final validation |
| Local agent (`local_agent/`) | Same pipeline over HTTP; checkpointing after every scene |
| Frontend (`frontend/`) | PWA UI: dashboard, wizard, project timeline, scene editing, videos, settings |
| Storage (`services/storage.py`) | Local filesystem or S3-compatible (R2), path traversal guard |

## Data model (authoritative: `backend/app/models.py`)

- `users`, `sessions`, `password_reset_tokens`, `audit_events`
- `provider_accounts` (encrypted session, usage, active-workflow lock)
- `projects` (`status`, `progress`, `plan_revision`, `execution_mode`, `executor`,
  `generation_config`, `final_video_id`, `report`)
- `characters`, `scenes` (prompt, status, generation id, attempts, local key,
  duration/resolution, checksum, last frame)
- `generation_attempts` (per-scene audit of submissions)
- `jobs` (`kind`, `status`, `idempotency_key`, `available_at`, lease fields,
  `attempts`, `max_attempts`, `payload`, `result`)
- `videos` (final + scene, storage keys, metadata, checksum, soft delete)
- `notifications`, `push_subscriptions`, `usage_events`, `local_execution_tokens`

All datetimes are stored UTC. A custom SQLAlchemy type keeps SQLite values
timezone-aware on read to avoid naive/aware comparison bugs.

## Job state machine

```
QUEUED ──claim──► RUNNING ──complete──► SUCCEEDED
   ▲                  │
   │                  ├──fail (attempts < max)──► QUEUED (backoff)
   │                  ├──fail (attempts = max)──► FAILED
   │                  └──cancel─────────────────► CANCELLED
   └──revive (explicit retry)── SUCCEEDED/FAILED/CANCELLED
```

- Claims are conditional updates; two workers cannot both win a job.
- Leases expire if a worker dies; another worker reclaims the job.
- Idempotency keys make retries safe: `plan:{project}:{revision}`,
  `generate:{project}:{plan_revision}`, `assemble:{project}:{revision}[:local]`.
- Scene-level progress is persisted, so a reclaimed GENERATE skips scenes already
  marked `SUCCEEDED` with an uploaded clip.

## Storage layout

```
users/{user_id}/projects/{project_id}/
  final.mp4
  thumbnail.jpg
  scenes/scene_001.mp4
  scenes/scene_001_last.png
  assets/reference_*.png
  assets/music_*.mp3
  assets/voiceover_*.m4a
```

Local execution uploads to a temporary `_uploads/{job_id}` area, validates, then
promotes to the user path. Signed URLs bind `video_id|user_id` and a short TTL.

## Trust boundaries

- Browser → API: session cookie + CSRF double-submit; bearer only for the local
  execution protocol.
- API → provider: per-user encrypted session material, one active workflow per
  provider account, no cross-user reuse.
- Local agent → API: scoped bearer token; claims only that user's jobs; all media
  validated server-side before being stored.
- Worker → storage: path-safe keys; no user-supplied filesystem paths.
- External links/downloads: filename quoting and a traversal guard.

## Deployment shapes

1. **Fully free / single VM**: Oracle Always Free ARM VM runs API + worker; Neon
   Postgres; R2 storage; Vercel Hobby for the frontend.
2. **Local execution**: API on free hosting, worker on the user's Windows machine
   with `EXECUTION_MODE=local`.
3. **Single process for development**: SQLite + local storage + `uvicorn` +
   `workers.runner` + `next dev`.

Docker files are provided for packaging; Docker is not installed in the original
authoring environment, so the images were not executed there.
