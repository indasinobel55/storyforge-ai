#!/bin/bash
# Runs the full StoryForge AI stack in a single container:
#   1. FastAPI API on 127.0.0.1:8000 (internal) — creates the DB schema
#   2. cloud worker (job queue consumer) — started AFTER the API is healthy
#      so schema creation never races between the two processes
#   3. Next.js frontend on $PORT (public), proxying /api to the API via rewrites
set -e
cd /app

export STORAGE_DIR="${STORAGE_DIR:-/app/data/storage}"

python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 &
API_PID=$!

for i in $(seq 1 90); do
  if curl -fsS http://127.0.0.1:8000/api/health >/dev/null 2>&1; then
    echo "[start-all] API is healthy"
    break
  fi
  if ! kill -0 "$API_PID" 2>/dev/null; then
    echo "[start-all] API exited during startup" >&2
    exit 1
  fi
  sleep 2
done

python -m workers.runner &
WORKER_PID=$!

cd /app/frontend-standalone
PORT="${PORT:-10000}" HOSTNAME="0.0.0.0" node server.js &
WEB_PID=$!

term() {
  kill -TERM "$WORKER_PID" "$API_PID" "$WEB_PID" 2>/dev/null || true
  wait
}
trap term TERM INT

wait -n
exit_code=$?
kill -TERM "$WORKER_PID" "$API_PID" "$WEB_PID" 2>/dev/null || true
exit $exit_code
