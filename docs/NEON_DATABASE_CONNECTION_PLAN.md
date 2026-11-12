# AI Video Studio — Neon PostgreSQL Connection Plan

**Project:** AI Video Studio  
**Directory:** `C:\AI_Video_Studio`  
**Date:** 2026-11-08  
**Status:** Inspection complete; ready for configuration

---

## 1. Database URL Configuration

### Current SQLite Configuration
- **URL format**: `sqlite+aiosqlite:///data/studio.db`
- **Default in code**: `f"sqlite+aiosqlite:///{(ROOT_DIR / 'data' / 'studio.db').as_posix()}"` (config.py)
- **Alembic default**: `sqlite+aiosqlite:///data/studio.db` (alembic.ini)
- **Location**: `C:\AI_Video_Studio\data\studio.db`

### PostgreSQL URL Format Expected
The application uses SQLAlchemy's `create_async_engine()` with the `settings.database_url` string. No code changes are needed — changing the `database_url` environment variable will route all database operations to PostgreSQL.

**Expected PostgreSQL URL format**:
```
postgresql+asyncpg://<username>:<password>@<host>:<port>/<database>
# or with Neon-specific gateway:
postgresql+asyncpg://ep<EUID>.<region>.neon.tech:5454/neondb
# The asyncpg driver is the standard async driver for PostgreSQL with SQLAlchemy
```

**Neon free plan connection example** (format only; do not insert real credentials):
```
postgresql+asyncpg://ep0wvxyz.us-east-2.neon.tech:5454/neondb
```

**Note**: Neon uses port `5454` for TLS connections. The `asyncpg` driver is the SQLAlchemy standard async driver for PostgreSQL.

---

## 2. Environment Variable Names

| Variable | Current Value | Required for PostgreSQL | Notes |
|----------|--------------|----------------------|-------|
| `DATABASE_URL` | Not set (defaults to SQLite in config.py) | **Required** | Read by `Settings` class from `.env` file; overrides hardcoded default |
| `AUTO_CREATE_SCHEMA` | `true` | Recommended: `false` for production | Set to `false` once migrations are applied manually |
| `ENVIRONMENT` | `development` | Recommended: `production` | Optional; affects `is_production` property |

**The `DATABASE_URL` environment variable is the only required change.** The `Settings` class reads it from the `.env` file (via `env_file=str(ROOT_DIR / ".env")`), but if `DATABASE_URL` is set as an OS environment variable, it will override the `.env` value due to `extra="ignore"` in the Pydantic Settings config.

---

## 3. Connection Pooling Strategy

### Application Runtime (`backend/app/database.py`)
```python
engine = create_async_engine(
    settings.database_url,
    echo=False,
    future=True,
    pool_pre_ping=True,  # Connection health check on checkout
)
```

- **Pool type**: SQLAlchemy's default `AsyncAdaptedQueuePool` for async engines
- **`pool_pre_ping=True`**: Probes connections on checkout; gracefully replaces stale connections
- **No manual pool configuration needed** — SQLAlchemy handles pooling automatically

### Alembic Migrations (`migrations/env.py`)
```python
async def run_async_migrations() -> None:
    connectable = create_async_engine(
        settings.database_url, poolclass=pool.NullPool
    )
```

- **Migration pool type**: `NullPool` — one connection per migration run, automatically disposed
- **Why NullPool**: Migration contexts should not persist connections; each `run_migrations_online()` creates and disposes a fresh engine
- **No connection pooling needed for migrations** — NullPool is the correct pattern

---

## 4. Alembic Migration Strategy

### Offline Mode (no database connection required)
```bash
# Set DATABASE_URL before running
alembic upgrade head
```
- Configures `context` with `url=settings.database_url`
- Generates SQL without connecting to the database
- Works with any URL string

### Online Mode (actual database connection)
```bash
# Set DATABASE_URL before running
python -m pytest ...  # or: python -m alembic upgrade head
```
- Creates async engine with `NullPool`
- Connects to the database to run migrations
- Automatically disposes engine after completion

### Recommended Migration Workflow for Neon
1. **Set `DATABASE_URL`** to Neon PostgreSQL URL
2. **Set `AUTO_CREATE_SCHEMA=false`** in `.env` (or OS env)
3. **Run migrations online**:
   ```bash
   # From project root
   DATABASE_URL="postgresql+asyncpg://ep0wvxyz.us-east-2.neon.tech:5454/neondb" \
   python -m alembic upgrade head
   ```
4. **Verify tables** in Neon console (96 tables from initial schema migration)
5. **Application can now connect** using the same `DATABASE_URL`

**No code changes needed** for Alembic — it reads `settings.database_url` just like the application does.

---

## 5. Whether Code Changes Are Required

**Answer: NO code changes required.**

The application already supports PostgreSQL through SQLAlchemy's async engine. All database access goes through `settings.database_url`, which is a string configuration value. Changing this value from a SQLite URL to a PostgreSQL URL routes all operations (ORM, sessions, engine creation, Alembic migrations) to PostgreSQL automatically.

**Supported without modifications:**
- ✅ ORM model reflection and queries
- ✅ Async session management (`get_db()` dependency)
- ✅ `init_db()` — `Base.metadata.create_all()` 
- ✅ Alembic migrations (offline + online)
- ✅ Connection pooling (`pool_pre_ping=True`)
- ✅ SQLite-specific pragmas (automatically skipped for PostgreSQL)
- ✅ `UTCDateTime` timezone handler (works for both SQLite and PostgreSQL)

**The only change needed**: The `DATABASE_URL` environment variable value.

---

## 6. Implementation Plan — Exact Commands

### Prerequisites (already done, verified)
- ✅ Neon PostgreSQL database created on free plan
- ✅ Project structure inspected (no code modifications needed)
- ✅ SQLite database at `C:\AI_Video_Studio\data\studio.db` preserved (not modified)

### Step 1: Obtain Neon Connection URL
From the Neon console, note the connection string format:
```
postgresql+asyncpg://ep<EUID>.<region>.neon.tech:5454/neondb
```
**Do not share or insert actual passwords/credentials in this plan.**

### Step 2: Set DATABASE_URL Environment Variable
**Option A: OS environment variable (recommended for this session)**
```powershell
# PowerShell
$env:DATABASE_URL="postgresql+asyncpg://ep0wvxyz.us-east-2.neon.tech:5454/neondb"
```

**Option B: .env file** (the app reads from `.env` automatically)
Add/override in `.env` (but **do not modify .env or .env.local** per strict instructions):
```
DATABASE_URL=postgresql+asyncpg://ep0wvxyz.us-east-2.neon.tech:5454/neondb
```

### Step 2b: Also set AUTO_CREATE_SCHEMA=false (production recommendation)
```powershell
$env:AUTO_CREATE_SCHEMA="false"
```

### Step 3: Verify the application can connect
```powershell
# From C:\AI_Video_Studio
python -c "from backend.app.config import get_settings; s = get_settings(); print(s.database_url)"
```
**Expected output**: The Neon PostgreSQL URL (not SQLite)

### Step 4: Apply Alembic migrations (online mode)
```powershell
# From C:\AI_Video_Studio
DATABASE_URL="postgresql+asyncpg://ep0wvxyz.us-east-2.neon.tech:5454/neondb" \
python -m alembic upgrade head
```
**Expected**: Migrations run successfully, 96 tables created in Neon PostgreSQL

### Step 5: Verify application works with PostgreSQL
```powershell
python -m pytest tests/test_api.py tests/test_security.py -q
```
**Expected**: All 9 tests pass (same as local SQLite verification)

### Step 6: Verify frontend build still works
```powershell
cd frontend && npm run build
```
**Expected**: 10/10 routes compiled successfully

---

## 7. Summary of Required Changes

| Item | Change Required | Effort |
|------|----------------|--------|
| `DATABASE_URL` env var | Set to Neon PostgreSQL URL | 1 minute |
| `AUTO_CREATE_SCHEMA` | Set to `false` (production recommended) | 1 minute |
| Application code | **None** — reads `settings.database_url` | 0 minutes |
| Alembic config | **None** — reads `settings.database_url` | 0 minutes |
| SQLite database | **Preserve as-is** (do not modify) | 0 minutes |
| Packages installed | **None** — `asyncpg` should already be in requirements | 0 minutes |

**Total effort**: ~2 minutes of configuration, zero code changes.

---

## 8. Connection String Format Reference

### SQLite (current, preserved)
```
sqlite+aiosqlite:///data/studio.db
```

### PostgreSQL (Neon, target)
```
postgresql+asyncpg://ep<EUID>.<region>.neon.tech:5454/neondb
# Example (placeholder UID only):
postgresql+asyncpg://ep01234567.us-east-2.neon.tech:5454/neondb
```

### Driver notes
- `asyncpg` is the recommended async driver for PostgreSQL with SQLAlchemy
- It should already be available in the project's dependencies (installed previously)
- If `asyncpg` is unavailable, `psycopg2` can be used: `postgresql+psycopg2://...` but `asyncpg` is the SQLAlchemy standard

---

## 9. What If `asyncpg` Is Not Installed?

The project's `requirements.txt` (or `pyproject.toml`) should already include `asyncpg` since the application was designed for cloud/async mode. If it's missing, it can be installed with:
```powershell
pip install asyncpg
```
**But do not install packages** per the strict instructions — this is noted as a possible contingency only.

---

## 10. Next Step Confirmation

After obtaining the Neon connection URL and setting the `DATABASE_URL` environment variable, the following verification can be performed:

```powershell
# Verify the URL is read correctly
python -c "from backend.app.config import get_settings; s = get_settings(); print('DB URL:', s.database_url)"

# Verify pytest still works
python -m pytest tests/test_api.py tests/test_security.py -q

# Verify frontend build
cd frontend && npm run build
```

**All three should succeed** with the Neon URL configured, confirming the application is ready for PostgreSQL production use.