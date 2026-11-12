# Cloud Migration Plan

The existing tool is a single-user local CLI. The platform is already structured
for cloud deployment; this plan covers moving a verified local installation to a
shared cloud deployment without changing application behaviour.

## Phase 0 — Baseline (complete)

- Single-user agent audited and preserved.
- Shared agent core extracted; platform backend, worker, local agent and frontend
  built.
- Cloud and local end-to-end tests pass on Windows with SQLite and local storage.

## Phase 1 — Hardening before exposure

1. Replace `AUTO_CREATE_SCHEMA=true` with versioned migrations (Alembic) and run
   them during release. Auto-create is convenient for development only.
2. Set `ENVIRONMENT=production`, `COOKIE_SECURE=true`,
   `DEV_EXPOSE_RESET_TOKEN=false`, a strong `SECRET_KEY`, and HTTPS.
3. Move rate limiting to a shared store (Redis/Upstash) if running more than one
   API instance. The current limiter is in-process.
4. Add structured logs and error reporting; ensure tokens, cookies, session state
   and provider payloads are never logged.
5. Decide storage: local volume for a single VM, or S3/R2 for horizontal scaling.
6. Add a reverse proxy (Caddy/Nginx) with request size limits matching
   `UPLOAD_MAX_BYTES` and long timeouts for media uploads.

## Phase 2 — Database and storage

1. Provision Postgres (Neon/Supabase or self-hosted).
2. Set `DATABASE_URL=postgresql+asyncpg://...` and run migrations.
3. Set `STORAGE_BACKEND=s3` with R2/S3 credentials and a private bucket.
4. Verify Range streaming and signed URLs through the proxy.
5. Add a retention policy for scene clips and a storage quota alert.

## Phase 3 — Compute topology

Choose one:

### A. Single VM (recommended zero-cost)

- API: `uvicorn workers...` behind the proxy (or `gunicorn`/`uvicorn` workers).
- Worker: `python -m workers.runner` as a systemd service. Keep
  `EXECUTION_MODE=cloud`.
- Install FFmpeg (`imageio-ffmpeg` also works) and enough disk for scene clips.
- Mount persistent storage or configure R2.

### B. Split API and worker

- API on a small always-on host; worker on a larger machine (FFmpeg is CPU-heavy).
- Both share Postgres and object storage.
- Scale workers horizontally; the queue lease prevents double claims.

### C. Local fallback

- Keep the API in the cloud with `EXECUTION_MODE=local`.
- Users run `python -m local_agent` with a revocable token.
- The machine must stay awake; uploads are re-validated by the server.

Never run cloud and local workers for the same deployment mode simultaneously.
Changing modes requires an API restart.

## Phase 4 — Frontend

1. Deploy `frontend/` to Vercel Hobby or serve `next build` + `next start` from the
   VM/proxy.
2. Set `NEXT_PUBLIC_API_URL` to the public API origin.
3. Update `FRONTEND_ORIGIN` so CORS allows the deployed origin with credentials.
4. Verify cookies: same-site deployments are simplest; cross-site requires
   `SameSite=None; Secure` and HTTPS (not enabled by default in this build).
5. Validate PWA installability on a phone; automated device testing was not
   available in the authoring environment.

## Phase 5 — Operations

1. Health checks: `GET /api/health` (DB, mode, queue depth).
2. Alerts: failed jobs, queue backlog, disk/storage quota, worker heartbeat gaps.
3. Backups: database plus media bucket/volume.
4. Key rotation: `SECRET_KEY` rotation invalidates sessions and signed URLs;
   provider sessions use the derived Fernet key, so plan re-encryption.
5. Incident kill switches: `TAAFT_ENABLED=false`, disable local tokens, scale
   worker to zero.

## Phase 6 — Provider integration

Do not enable TAAFT automation until written authorization is on file. See
`TAAFT_INTEGRATION_FEASIBILITY.md`. If authorized, implement an HTTP provider
against an official API and keep the existing `VideoProvider` contract, quotas,
backoff and audit trail.

## Rollback

- Keep the previous release's container/venv and database backup.
- Schema changes should be backwards compatible for one release.
- Mode can be reverted by changing `EXECUTION_MODE` and restarting API/worker.
- Media is content-addressed by project paths; a failed deploy does not delete
  existing clips.
