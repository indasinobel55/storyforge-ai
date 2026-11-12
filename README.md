# StoryForge AI — AI Video Studio

Cloud-first, multi-user AI video generation platform with a durable job queue, a
Next.js PWA frontend, server-side media validation, and a scoped **local Windows
execution mode** that reuses the exact same agent pipeline.

> Development builds use a clearly labelled **simulated provider** that renders
> real MP4 clips with FFmpeg. Real TAAFT automation is **disabled** pending written
> provider authorization (see `TAAFT_INTEGRATION_FEASIBILITY.md`). No paid
> services are activated by default.

## What it does

1. You paste a script and choose scenes, duration, orientation and style.
2. A planner produces a per-scene shot list with prompts, character bible and
   continuity notes.
3. You approve the plan (or auto-start).
4. Each scene is generated, downloaded, probed and validated, then assembled with
   FFmpeg (optional crossfades, music and voiceover mixing).
5. The final MP4 is validated server-side before the project is marked complete.
6. Videos stream with HTTP Range support and are downloadable through signed URLs.

## Architecture

```
frontend/            Next.js 14 App Router + Tailwind + PWA shell
backend/app/         FastAPI API, auth, SQLAlchemy models, queue, storage, realtime
agent/               Shared core: planner, providers, FFmpeg, validation, assembly
workers/             Cloud worker (durable leased jobs, PLAN/GENERATE/ASSEMBLE)
local_agent/         Local Windows worker speaking the scoped execution API
tests/               Security, API isolation and cloud/local end-to-end tests
```

- **Database**: SQLite by default (`sqlite+aiosqlite`), Postgres supported.
- **Queue**: DB-backed jobs with idempotency keys, leases, heartbeats and retries.
  No Redis required.
- **Storage**: local folder by default; S3-compatible (e.g. Cloudflare R2) optional.
- **Auth**: bcrypt hashes, server-side sessions, HttpOnly cookies, CSRF double-submit,
  encrypted provider sessions, HMAC-signed media URLs, per-user isolation.
- **Realtime**: WebSocket tickets + snapshot polling endpoint; the UI uses polling.
- **Providers**: `simulated` (default) and gated `taaft`.

## Requirements

- Python 3.11+
- Node.js 18+ (built and verified with Node 24)
- FFmpeg is optional on PATH: `imageio-ffmpeg` supplies a bundled binary

## Windows quick start

```powershell
# 1. Install dependencies (from the repo root)
python -m pip install -r requirements.txt

# 2. Configure
Copy-Item .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(48))"   # paste into SECRET_KEY

# 3. Run the API (terminal 1)
python -m uvicorn backend.app.main:app --reload --port 8000

# 4. Run the frontend (terminal 2)
cd frontend
Copy-Item .env.local.example .env.local
npm install
npm run dev
```

Open http://localhost:3000, register, and create a project.

Convenience scripts:

```powershell
.\scripts\check.ps1              # pytest + production frontend build
.\scripts\run-local-worker.ps1   # local execution worker
```

### Cloud mode (default)

Start the worker in a third terminal:

```powershell
python -m workers.runner
```

Jobs survive worker restarts because every state transition is checkpointed in the
database. Expired leases are reclaimed automatically.

### Local mode

Set `EXECUTION_MODE=local` in `.env` and restart the API. Create a local execution
token in **Settings → Execution**, then run on the same or another Windows machine:

```powershell
$env:STUDIO_API_URL="http://localhost:8000"
$env:LOCAL_EXECUTION_TOKEN="<token>"
python -m local_agent --once     # one job
python -m local_agent --drain    # until idle
python -m local_agent            # keep polling
```

The local agent claims only **your** jobs, uploads scene clips and the final MP4 to
the backend, and the backend re-validates every uploaded file. The active execution
mode is always shown in the app. In local mode the machine must stay powered on while
a job runs; use `python -m local_agent` as a foreground process (or wrap it in a
service you trust).

## Tests

```powershell
python -m pytest
```

The suite covers password/token security, CSRF enforcement, cross-user project
isolation, the TAAFT gate, and **full cloud and local end-to-end generations**
(plan → generate → assemble → validation → streamed MP4). Current result: **11
passed**. A headless Playwright browser smoke test (register → create project →
project timeline) also passes.

Frontend build check:

```powershell
cd frontend
npm run build
```

## Database migrations

Alembic is configured with an initial schema revision. For production, disable
schema auto-creation and apply migrations explicitly:

```powershell
python -m alembic upgrade head
```

Set `AUTO_CREATE_SCHEMA=false` once the migrations have run. Development defaults
to auto-create for a zero-setup first run.

## Docker

Docker files are provided but were not executed in the authoring environment
(Docker is not installed there):

```powershell
Copy-Item .env.example .env      # set SECRET_KEY first
docker compose up --build
```

This starts the API, cloud worker and frontend. For production, use Postgres and
S3/R2 storage and run migrations instead of relying on `AUTO_CREATE_SCHEMA`.

## Zero-cost deployment notes

Verified constraints as of this build (no paid plan was purchased):

| Service | Free tier notes |
| --- | --- |
| Oracle Cloud Always Free ARM VM | Best fit for a persistent API + worker (1–4 OCPU, 24 GB RAM total). |
| Render | Free web services sleep; background workers are paid. |
| Railway / Fly.io | Trial or limited credits; persistent workers may cost money. |
| Vercel Hobby | Fine for the Next.js UI; not for long-running workers. |
| Neon Postgres | Free tier with autosuspend; good for the API DB. |
| Cloudflare R2 | 10 GB storage, no egress fees; optional `STORAGE_BACKEND=s3`. |
| Upstash Redis | Not required by this build; the queue is DB-backed. |

Recommended zero-cost split: **Vercel Hobby** for `frontend/`, **Oracle Always Free
VM** for FastAPI + worker (or a local worker with `EXECUTION_MODE=local`), **Neon**
for Postgres and **R2** for media. Cloudflare quick tunnels can expose a local
backend for development.

## Documentation

| File | Contents |
| --- | --- |
| `PROJECT_COMPLETION_REPORT.md` | What was built, verified and left open |
| `CLOUD_ARCHITECTURE.md` | Components, job state machine, trust boundaries, topologies |
| `CLOUD_MIGRATION_PLAN.md` | Step-by-step move from local to cloud |
| `CLOUD_SERVICE_COMPARISON.md` | Zero-cost provider comparison |
| `TAAFT_INTEGRATION_FEASIBILITY.md` | Provider authorization decision (NO-GO) |
| `EXISTING_AGENT_AUDIT.md` | Audit of the original `taaft_agent.py` |
| `EXISTING_AGENT_FEATURE_MAP.md` | Original behaviour mapped to the platform |
| `.env.example` / `frontend/.env.local.example` | All configuration variables |

## Security notes

- Set `SECRET_KEY` to a strong random value; keep `COOKIE_SECURE=true` in HTTPS
  deployments and `DEV_EXPOSE_RESET_TOKEN=false` in production.
- Never commit `.env`, provider session files, the TAAFT Chrome profile, or the
  existing `claude-omnirouter-install-guide.md` (it contains a live-looking token).
  These are covered by `.gitignore`.
- Local execution tokens are shown once, stored hashed, scoped per user and can be
  revoked at any time.
- The API refuses to start real TAAFT automation unless explicitly authorized.
