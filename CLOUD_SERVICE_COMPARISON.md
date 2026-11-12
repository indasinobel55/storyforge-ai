# Cloud Service Comparison (Zero-Cost Focus)

Reviewed: 2026-11-08. Free tiers change frequently; verify current limits before
deploying. No paid plan was purchased for this project. Prices/limits below are
notes from the review, not guarantees.

| Service | Free offer (review notes) | Fit for this project | Caveats |
| --- | --- | --- | --- |
| **Oracle Cloud Always Free** | Always Free ARM Ampere VMs (up to 4 OCPU / 24 GB RAM total), 200 GB block storage, 10 TB egress | **Best fit** for API + persistent worker on one host | Capacity availability varies by region; account verification can be strict |
| **Render** | Free web services; cron jobs; free static sites | UI/API demos | Free web services spin down; background workers are **paid**; ephemeral filesystem |
| **Railway** | Trial credit / limited free usage | Quick prototype | No reliable always-free worker; usage-based billing |
| **Fly.io** | Pay-as-you-go with small free allowances historically | Containerized API + worker | No dependable always-free tier for always-on machines |
| **Vercel (Hobby)** | Static/Next.js hosting, serverless functions | **Frontend only** | Non-commercial Hobby terms; function duration limits; no long-running worker |
| **Cloudflare Pages/Workers** | Generous free requests; R2 10 GB + no egress fees | Frontend, storage, optional proxy | Workers runtime not suited to long FFmpeg/Playwright jobs |
| **Supabase** | Free Postgres + storage + auth | Alternative DB/auth | Free projects pause after inactivity; 500 MB DB; storage limits |
| **Neon** | Free serverless Postgres with autosuspend | **DB** | Cold starts after suspend; connection limits |
| **Cloudflare R2** | 10 GB storage, 1M class A ops, no egress fees | **Media storage** | S3-compatible; configure credentials carefully |
| **Upstash Redis** | Free daily command allowance | Optional cache/limiter | Not required: queue is DB-backed |
| **GitHub Actions** | Free minutes on public/limited private | CI, tests, scheduled tasks | Not suitable as an always-on job worker |
| **Cloudflare Quick Tunnel** | Free ephemeral tunnel | Expose a local backend for development | URL changes; not production |

## Recommended zero-cost combinations

### A. Always-on free (single VM)

- API + cloud worker + optional local fallback: Oracle Always Free ARM VM (Docker
  or systemd + venv).
- Database: Neon free Postgres (or SQLite on the VM's block volume for a simpler
  single-node setup).
- Media: Cloudflare R2 free tier (`STORAGE_BACKEND=s3`).
- Frontend: Vercel Hobby (commercial use requires a paid plan) or static export
  served by the same VM.

### B. No persistent worker

- API on a free host that can sleep.
- Frontend on Vercel Hobby.
- Users run `python -m local_agent` with `EXECUTION_MODE=local`; a connected
  computer performs generation and uploads validated media.
- Caveat: the backend must stay reachable while the local job runs; a sleeping
  free web service can interrupt long uploads.

### C. Development only

- Everything on one Windows machine: SQLite + local storage + uvicorn + Next dev +
  cloud worker or local agent. No external service required. This is the mode that
  was executed and tested.

## Cost guardrails implemented

- No paid API keys are required; the default provider is simulated.
- TAAFT automation is disabled, so no provider credits are consumed.
- LLM planning is opt-in (`PLANNER_LLM_ENABLED=false`) and falls back to a local
  deterministic planner.
- Media storage is local by default and R2-compatible when object storage is needed.
- The queue is database-backed; Redis is optional, avoiding another service.

## Chosen deployment for this delivery

Because the authoring environment has no Docker and no paid accounts, the verified
configuration is **single-machine development**: FastAPI + SQLite + local storage +
Next.js + either the cloud worker or the local agent. The cloud topologies above are
documented and packaged but were not deployed.
