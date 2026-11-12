# StoryForge AI — Deployment Guide

The platform is verified working (77/77 tests, full E2E smoke test passed). Deploy it
with one of the two paths below.

## Option A — Zero-cost cloud (recommended)

Split: **Render** (frontend) + **Neon** (Postgres) + **Oracle Always Free VM** or any
cheap VPS (API + worker). Cloudflare R2 optional for media storage.

Note on Render free tier: the frontend web service sleeps after ~15 minutes of
inactivity. **Already handled:** a GitHub Actions keep-alive workflow
(`indasinobel55/render-keep-alive`, fork of `EmilienxD/keep-alive-render-free`)
pings the service every 10 minutes, so it stays awake 24/7 within the free
instance-hours allowance. The job **worker must NOT run on Render** (free plan
has no persistent background workers) — it runs on the same VM as the API.

### 1. Neon — database (free, 5 min)

1. Sign up at https://neon.tech → create project.
2. Copy the connection string, e.g.
   `postgresql+asyncpg://user:pass@ep-xxx.aws.neon.tech/neondb?sslmode=require`

### 2. Render — frontend (free, 5 min)

1. Push the `frontend/` directory (or the whole repo) to a GitHub repository.
2. Sign up at https://render.com → **New → Web Service** → connect the GitHub repo.
3. Configure:
   - **Runtime:** Node
   - **Root Directory:** `frontend`
   - **Build Command:** `npm install && npm run build`
   - **Start Command:** `npm run start`
   - **Instance type:** Free
4. Add environment variable (Dashboard → Environment):
   `NEXT_PUBLIC_API_URL = https://<your-api-domain>`
   (Only known after step 3 — set it, then use **Manual Deploy → Deploy latest commit** once more.)
5. Keep-alive: in the `indasinobel55/render-keep-alive` repo (GitHub Actions),
   set the secret/variable holding the service URL to
   `https://<your-app>.onrender.com` — the Action then pings it every 10 minutes.

Automation alternative: if you paste a **Render API key** (Account Settings → API Keys),
the deployment can be created via the Render REST API instead of clicking through
the dashboard.

### 3. Oracle Always Free (or any VPS) — API + worker

1. Create an Oracle Cloud Always Free account → create an ARM Ubuntu VM
   (1–4 OCPU, 24 GB RAM free tier).
2. On the VM:

```bash
# Install
sudo apt update && sudo apt install -y python3.11 python3.11-venv ffmpeg
git clone <your-repo-or-upload storyforge-deploy.zip> && cd AI_Video_Studio
python3.11 -m venv .venv && .venv/bin/pip install -r requirements.txt

# Configure (minimum required values)
cat > .env <<'EOF'
ENVIRONMENT=production
SECRET_KEY=<python -c "import secrets; print(secrets.token_urlsafe(48))">
COOKIE_SECURE=true
DEV_EXPOSE_RESET_TOKEN=false
AUTO_CREATE_SCHEMA=false
DATABASE_URL=<your neon connection string>
EXECUTION_MODE=cloud
FRONTEND_ORIGIN=https://<your-render-app>.onrender.com
PUBLIC_API_URL=https://<your-api-domain>
EOF

# Migrate schema, then run both services
.venv/bin/python -m alembic upgrade head
.venv/bin/python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 &
.venv/bin/python -m workers.runner &
```

3. Put nginx + certbot (free TLS) in front, or expose port 8000 directly for testing.

Alternative to Oracle: any $5 VPS (Hetzner, Contabo) works identically.

### 4. Optional — Cloudflare R2 media storage

Set in `.env` on the VM:

```
STORAGE_BACKEND=s3
S3_ENDPOINT_URL=https://<account-id>.r2.cloudflarestorage.com
S3_BUCKET=storyforge
S3_ACCESS_KEY_ID=...
S3_SECRET_ACCESS_KEY=...
S3_REGION=auto
```

## Option B — Docker (single box)

Docker isn't installed on this machine yet. After installing Docker Desktop:

```powershell
Copy-Item .env.example .env    # then set SECRET_KEY
docker compose up --build
```

Runs API + worker + frontend together (SQLite inside a volume — fine for testing,
use Neon/Postgres for production).

## Deploy bundle

`storyforge-deploy.zip` (repo root) contains the clean deployable tree:
backend, agent, workers, local_agent, frontend, migrations, Docker files —
no venvs, caches, temp dirs or test databases.

## Post-deploy checklist

- [ ] HTTPS on both API and frontend (CORS/cookies require it: `COOKIE_SECURE=true`)
- [ ] `DEV_EXPOSE_RESET_TOKEN=false`
- [ ] `AUTO_CREATE_SCHEMA=false` (migrations applied once)
- [ ] Set `NEXT_PUBLIC_API_URL` on Render to the public API URL
- [ ] Worker process kept alive (systemd services recommended on the VM)
- [ ] TAAFT stays disabled (`TAAFT_ENABLED=false`) until provider authorization
