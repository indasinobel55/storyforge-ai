#!/usr/bin/env bash
set -euo pipefail
cd C:/AI_Video_Studio
rm -rf tmp_verify
mkdir -p tmp_verify
cp .env.example tmp_verify/.env
python -c "import secrets; print('SECRET_KEY=' + secrets.token_urlsafe(48))" >> tmp_verify/.env
echo 'AUTO_CREATE_SCHEMA=false' >> tmp_verify/.env
echo 'DATABASE_URL=sqlite+aiosqlite:///tmp_verify/studio.db' >> tmp_verify/.env
echo 'STORAGE_DIR=tmp_verify/storage' >> tmp_verify/.env
echo 'EXECUTION_MODE=cloud' >> tmp_verify/.env
echo 'DEV_EXPOSE_RESET_TOKEN=true' >> tmp_verify/.env
echo '---ALEMBIC---'
cd tmp_verify
export PYTHONPATH=../
export ALEMBIC_CONFIG=../alembic.ini
export DATABASE_URL=sqlite+aiosqlite:///tmp_verify/studio.db
python -m alembic -c ../alembic.ini upgrade head 2>&1 | tail -n 30
echo '---TABLES---'
sqlite3 tmp_verify/studio.db '.tables'
echo '---COUNT---'
sqlite3 tmp_verify/studio.db "SELECT count(*), group_concat(name) FROM sqlite_master WHERE type='table';"
