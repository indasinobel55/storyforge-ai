# AI Video Studio — Neon Recovery V3 Report

Date: 2026-11-08
Scope: Windows host, Python 3.11, async SQLAlchemy + asyncpg, Alembic, local SQLite at `data/studio.db`.
Budget: 0 INR. No paid service, upgrade, or new API was used.

This report is itemized and contains no hostnames, usernames, passwords, or
connection URLs. Anything that was not executed is marked NOT_STARTED.

---

## 1. Stage status

| Stage | Result | Note |
|-------|--------|------|
| 0 — Baseline audit | **DONE** | Source verified, not prior reports |
| 1 — Probe rebuild | **DONE** | Pure modules + 42 offline tests |
| 2 — Live run instructions | **RUNTIME RUN COMPLETE** | Pooled endpoint verified end-to-end; migration (direct) run still pending |
| 3 — DNS interpretation | **DONE** | System, Google and Cloudflare DNS pass; DoH failure is not material (see §5.7) |
| 4 — Read-only inspection | **DONE (runtime purpose)** | Empty schema: 0 of 15 expected tables present; Alembic history absent |
| 5 — Config review | **DONE (report only)** | No change applied; 3 proposals below |
| 6 — Acceptance | **DONE for available evidence** | Live markers remain NOT_STARTED |

Overall status: **CONNECTION VERIFIED (runtime)** — the pooled endpoint answered `SELECT 1` through both drivers and the read-only inspection completed. The migration (direct) run has not been performed, so the migration path is still unproven.

---

## 2. Stage 1 artifacts

| Path | Purpose |
|------|---------|
| `backend/app/db_url.py` | Single pure implementation: validation, driver translation (SSL context, libpq param removal), pooled detection, port check, `redact()`, SELECT/SHOW allowlist |
| `backend/app/schema_expectations.py` | Pure revision parser (upgrade-only, ordered) → expected tables + head; ORM set; comparison |
| `scripts/neon_probe.py` | Rewritten probe: 4 input methods, layers L1–L7, marker contract, no host/table/IP output |
| `tests/conftest.py` | Unconditional SQLite test URL, `MIGRATION_DATABASE_URL`, session-start SQLite assertion |
| `tests/test_neon_probe_offline.py` | 42 offline tests, no network |
| `scripts/neon_probe.py.bak_stage0` | Pre-edit backup; secret scan clean |

Not modified: `backend/app/database.py`, `backend/app/main.py`, `workers/runner.py`, `migrations/env.py`.

Alembic head verified from the revision files: single head `027fcf80b4b6`, 15 `create_table` operations in `upgrade()`.

**Schema drift found:** the ORM declares 16 tables; the revision history creates 15. The extra ORM table is `activities` (no revision creates it). Expected counts for Stage 4: `PG_EXPECTED_TABLE_COUNT=15`.

---

## 3. Stage 2 — exact live sequence (user runs this)

Runtime (pooled) URL:

```powershell
cd C:\AI_Video_Studio
$env:NEON_PROBE_URL = (Get-Clipboard -Raw).Trim()
python scripts/neon_probe.py --from-env --purpose runtime
Remove-Item Env:NEON_PROBE_URL
Set-Clipboard -Value " "
```

Migration (direct, non-pooled) URL — repeat the same block with:

```powershell
python scripts/neon_probe.py --from-env --purpose migration
```

Copy each URL fresh from Neon Console → project `ai-video-studio` → branch
`production` → database `neondb` → role `neondb_owner` → Connect. Pooling ON for
runtime, pooling OFF for migration. Do not reuse any hostname from earlier
reports.

Expected final lines (paste them back): `PROBE_PURPOSE`, `URL_VALIDATION`,
`HOST_FORMAT`, `POOLED`, `DNS_SYSTEM`, `DNS_GOOGLE`, `DNS_CLOUDFLARE`, `DNS_DOH`,
`TCP`, `TLS`, `ASYNCPG_SELECT_1`, `SQLALCHEMY_SELECT_1`, `FAILURE_CLASS`,
`COLD_START_RETRY_USED`, plus inspection markers when reached.

---

## 4. Stage 5 — configuration review

| # | Check | Evidence | Result |
|---|-------|----------|--------|
| 1 | SQLite remains the local default | `backend/app/config.py:32`; `Settings()` with URL env removed resolves `sqlite+aiosqlite` | **PASS** |
| 2 | Production URL comes only from configuration | `backend/app/config.py:10-11` (`env_file` + pydantic env precedence); no root `.env` file exists | **PASS** |
| 3 | `AUTO_CREATE_SCHEMA` cannot be true in production | `config.py:29` default `True`; `main.py:28-29` and `workers/runner.py:12-13` gate only on that flag; `init_db()` runs `create_all` (`database.py:75-80`) | **FAIL** — proposal P1 |
| 4 | Runtime engine: asyncpg, SSL via context, pooler cache disabled | `database.py:50-56` passes the raw URL with `sslmode` intact, no SSL context, no prepared-cache setting | **FAIL** — proposal P2 |
| 5 | Alembic can use a separate direct URL | `migrations/env.py:46-53` and `:60-64` use only `settings.database_url`; no `MIGRATION_DATABASE_URL` fallback | **FAIL** — proposal P3 |
| 6 | Worker uses the same intended database | `workers/runner.py:6-7` imports the shared `settings`/engine; `workers/generation_worker.py:82` prints only the URL scheme | **PASS** |
| 7 | No secrets in source or logs | Scan found no credential-bearing URL in code; `generation_worker.py:82` prints only `sqlite`/`postgresql`; no `echo=True` in runtime code | **PASS** |
| 8 | Test fixtures cannot reach a remote database | `tests/conftest.py:18-23` unconditional assignment; `:31-38` session abort when the resolved URL is not SQLite; subprocess proof test | **PASS** |

### Proposals (NOT applied — require approval)

**P1 — production guard for schema creation**

```python
# backend/app/config.py (add property)
@property
def auto_create_schema_enabled(self) -> bool:
    return self.auto_create_schema and not self.is_production

# backend/app/main.py:28 and workers/runner.py:12
if settings.auto_create_schema_enabled:
    await init_db()
```

**P2 — reuse the tested driver translation in the runtime engine**

```python
# backend/app/database.py (replace the create_async_engine call at line ~50)
_engine_url = settings.database_url
_connect_args: dict = {}
if _engine_url.startswith(("postgresql", "postgres://")):
    from .db_url import build_driver_config, validate_connection_url
    _driver = build_driver_config(validate_connection_url(_engine_url))
    _engine_url = _driver.url
    _connect_args = _driver.sqlalchemy_connect_args

engine = create_async_engine(
    _engine_url, echo=False, future=True, pool_pre_ping=True,
    connect_args=_connect_args,
)
```

**P3 — separate migration URL in Alembic**

```python
# migrations/env.py (after imports)
import os
migration_database_url = os.environ.get("MIGRATION_DATABASE_URL") or settings.database_url
# use migration_database_url in run_migrations_offline() and run_async_migrations()
```

---

## 5. Stage 6 — acceptance evidence

### 5.1 SQLite preservation

```
size   372736
sha256 012f08c875448ea5d3b966b3908db062241008041ff9df2123be910d603d0eef
```

Identical to the Stage 0 baseline. No migration, DDL or DML ran against it.

### 5.2 Tests actually run (all on forced temporary SQLite)

| Command scope | Result |
|---------------|--------|
| `tests/test_neon_probe_offline.py` | **42 passed** |
| `tests/test_api.py` | **5 passed** |
| Offline + API + security + continuity + activity + local E2E | **69 passed** |
| Full suite | **69 passed, 3 failed** — the three worker E2E tests (`test_cloud_e2e`, `test_crash_recovery`, `test_multi_user_isolation`) fail identically in isolation; `PLAN` succeeds and `GENERATE` fails. Not caused by this change: the application reads no variable whose value changed (`MIGRATION_DATABASE_URL` is read by no code), and the SQLite URL/`AUTO_CREATE_SCHEMA` values are unchanged. `ffmpeg` resolves through `imageio_ffmpeg`, so it is not a missing binary. Root cause **NOT_STARTED**. |

### 5.3 Secret scan (paths and categories only)

| Category | Files | Note |
|----------|-------|------|
| Credential-shaped PostgreSQL URL | 3 docs, 1 test file | Every match is a documentation placeholder or a deliberately fake test credential; no real value found |
| PostgreSQL URL literal | 15 files | Docs, examples and the `db_url.py` scheme constants |
| `echo=True` | 1 doc | Documentation only, not runtime code |
| URL/engine printing | docs + `workers/generation_worker.py:82` | Scheme only, never credentials |

Environment files present (not read): `.env.example`, `frontend/.env.local.example`,
`tmp_final_e2e/.env`, `tmp_verify/.env`. No root `.env`. `.gitignore` covers
`.env` and `.env.*`.

### 5.4 Final matrix

| Item | Result |
|------|--------|
| `INPUT_ENV` | **PASS** (unit + subprocess; variable deleted after read) |
| `INPUT_CLIPBOARD` | **NOT_STARTED** (not exercised; agent must not read the clipboard) |
| `INPUT_STDIN` | **NOT_STARTED** (implemented, not exercised) |
| `INPUT_HIDDEN_PROMPT` | **NOT_STARTED** (no TTY in the agent shell) |
| `URL_VALIDATION_RUNTIME` | **PASS** — live run; pooled accepted, libpq-only params dropped by the probe (see §5.7) |
| `URL_VALIDATION_MIGRATION` | **PASS** offline (direct fake URL: valid, not pooled) |
| `DNS_SYSTEM` / `DNS_GOOGLE` / `DNS_CLOUDFLARE` | **PASS** (live run) |
| `TCP`, `TLS`, `ASYNCPG_SELECT_1`, `SQLALCHEMY_SELECT_1` (runtime) | **PASS** (live run; `FAILURE_CLASS=NONE`) |
| `TCP`, `TLS`, `ASYNCPG_SELECT_1`, `SQLALCHEMY_SELECT_1` (migration) | **NOT_STARTED** |
| `NEON_READ_ONLY_INSPECTION` | **PASS** (live run; read-only guard verified) |
| `NEON_SCHEMA_STATUS` | **EMPTY** — 15 of 15 expected tables missing (live run) |
| `NEON_ALEMBIC_STATUS` | **ABSENT** — no history table (live run) |
| `SQLITE_PRESERVATION` | **PASS** |
| `SECRET_PROTECTION` | **PASS** (no credential printed, logged, committed or written by the agent) |

### 5.5 Migration readiness

**NOT READY** — the schema is empty and the Alembic history absent, so a
migration is required; with the current revisions it would create 15 of the
16 tables the ORM declares (the `activities` table has no revision), and the
runtime engine does not yet use the tested `db_url` translation (P2). The
migration (direct) probe run is also still pending.

### 5.6 Live run evidence (first attempt, user-pasted markers, sanitized)

```
INPUT_SOURCE=env
STAGE=L1_URL_VALIDATION
ERROR_CLASS=UrlValidationError
ERROR_CODE=BLOCKED_MULTILINE_INPUT
PROBE_PURPOSE=runtime
URL_VALIDATION=FAIL
HOST_FORMAT=NOT_STARTED
POOLED=false
DNS_SYSTEM=NOT_STARTED
DNS_GOOGLE=NOT_STARTED
DNS_CLOUDFLARE=NOT_STARTED
DNS_DOH=NOT_STARTED
TCP=NOT_STARTED
TLS=NOT_STARTED
ASYNCPG_SELECT_1=NOT_STARTED
SQLALCHEMY_SELECT_1=NOT_STARTED
FAILURE_CLASS=URL_PARSE
COLD_START_RETRY_USED=false
```

Interpretation: the environment variable carried the value (and was deleted
 afterwards), but the clipboard content was not a single-line URL, so
validation stopped at L1. No DNS, TCP, TLS, or login was attempted, and no
connection reached Neon. `POOLED=false` is the pre-parse default: detection
never ran. Next step: re-copy from the Neon Console and use the single-line
extraction command in Stage 2.

### 5.7 Runtime live run (user-pasted markers, sanitized)

```
INPUT_SOURCE=env
STAGE=L1_URL_VALIDATION
SCHEME_OK=true
PORT_SOURCE=DEFAULT
PORT_CHECK=PASS
SSL_CONFIGURED=true
DROPPED_PARAM=sslmode
DROPPED_PARAM=channel_binding
STAGE=L2_DNS
STAGE=L3_TCP
STAGE=L4_TLS
STAGE=L5_ASYNCPG
STAGE=L6_SQLALCHEMY
STAGE=L7_READ_ONLY_INSPECTION
PROBE_PURPOSE=runtime
URL_VALIDATION=PASS
HOST_FORMAT=PASS
POOLED=true
DNS_SYSTEM=PASS
DNS_GOOGLE=PASS
DNS_CLOUDFLARE=PASS
DNS_DOH=FAIL
TCP=PASS
TLS=PASS
ASYNCPG_SELECT_1=PASS
SQLALCHEMY_SELECT_1=PASS
FAILURE_CLASS=NONE
COLD_START_RETRY_USED=false
NEON_READ_ONLY_INSPECTION=PASS
PG_SERVER_VERSION=18.6
PG_TABLE_COUNT=0
PG_EXPECTED_TABLE_COUNT=15
PG_MISSING_COUNT=15
PG_UNEXPECTED_COUNT=0
NEON_SCHEMA_STATUS=EMPTY
NEON_ALEMBIC_STATUS=ABSENT
```

Interpretation:

| Marker | Meaning |
|--------|---------|
| `URL_VALIDATION=PASS`, `POOLED=true` | The pooled endpoint is accepted; the two libpq-only query parameters were dropped and never reached the driver |
| `DNS_SYSTEM/GOOGLE/CLOUDFLARE=PASS` | Name resolution works; the application uses the system resolver, so earlier DNS failure classes are closed |
| `DNS_DOH=FAIL` | A third-party DoH endpoint did not answer; not used by the application and not material |
| `TCP/TLS/ASYNCPG/SQLALCHEMY=PASS` | Full round trip: connect, TLS, and `SELECT 1` through both drivers (AsyncpgOptions and SQLAlchemy all succeeded — no `CONFIG_BUG_IN_SQLALCHEMY_LAYER`) |
| `NEON_READ_ONLY_INSPECTION=PASS` | The read-only transaction guard was verified and the inspection ran query-only |
| `PG_*COUNT` / `NEON_SCHEMA_STATUS=EMPTY` | The production database has **no tables at all**; all 15 expected are missing, 0 unexpected |
| `NEON_ALEMBIC_STATUS=ABSENT` | No version table: the migration history was never applied to this database |
| Earlier `ACCESS_DENIED`, timeout, `SSL_ERROR`, `DATABASE_NOT_EXISTS` | Obsolete — superseded by the proven `SELECT 1` above |

Migration consequence: the app's ORM declares 16 tables but the revisions create
15 (the `activities` table has no revision), so running the current migration
would leave the app one table short. The runtime engine also still passes the
raw URL — it must go through the tested `db_url` translation (P2) before the
application can connect in production.

Remaining: the migration-purpose (direct URL) run is still pending.

---

## 6. Safety confirmation

- No production migration was run.
- No DDL or DML was executed against any remote database.
- No production data was read or changed.
- `data/studio.db` is byte-identical to the Stage 0 baseline.
- No credential was printed, logged, committed, or written to disk.
- No paid service was created or upgraded.
- No DNS, adapter, firewall, proxy, VPN or hosts setting was changed.
- The live probe was not run by the agent; no clipboard content and no
  URL-bearing environment variable was read.

---

## 7. One recommended next action

Run the Stage 2 PowerShell block with `--purpose migration` for a **direct
(non-pooled)** URL and paste the marker lines back. That proves the second
endpoint the way Stage 2 requires; afterwards, the migration decision (P2
engine translation plus the `activities` revision) is a separate approval.
