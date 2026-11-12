# AI Video Studio — Activity Engine Final Acceptance Report

**Project:** AI Video Studio
**Directory:** `C:\AI_Video_Studio`
**Date:** 2026-11-08
**Mission:** Activity Engine Test Recovery & Contract Verification

---

## Final Result

**27 / 27 backend tests passing. 0 failed. 0 skipped. Frontend production build succeeds.**

| Suite | Passing | Failed | Skipped |
|-------|--------:|-------:|--------:|
| `tests/test_activity_engine.py` | 4 | 0 | 0 |
| `tests/test_api.py` | 5 | 0 | 0 |
| `tests/test_security.py` | 4 | 0 | 0 |
| `tests/test_local_e2e.py` | 1 | 0 | 0 |
| `tests/test_continuity_engine.py` | 13 | 0 | 0 |
| **Total** | **27** | **0** | **0** |

> Note: the mission's baseline table listed Security as 5 tests. The suite actually contains 4; the 27-test total is unchanged (`5 + 4 + 1 + 13 + 4 = 27`).

---

## 1. Review of the Previous Fix (Async Test Infrastructure)

Verified in `tests/test_activity_engine.py` and `backend/app/database.py`:

| Check | Result |
|-------|--------|
| `async_sessionmaker` configured | ✅ `async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)` — mirrors `backend/app/database.py` |
| `AsyncSession` used consistently | ✅ `class_=AsyncSession` on every sessionmaker; no sync sessions left |
| `create_async_engine` appropriate | ✅ `create_async_engine("sqlite+aiosqlite:///…")` matches the async driver |
| `Base.metadata.create_all` async pattern | ✅ `async with engine.begin() as conn: await conn.run_sync(Base.metadata.create_all)` — same pattern as `init_db()` |
| Engine disposal | ✅ `asyncio.run()` closes each loop; per-test engines live on temp files and are garbage-collected with the engine pool. No cross-test engine sharing |
| Test isolation | ✅ Each test creates its own `tempfile.mkdtemp()` database; unique users per test; distinct project IDs |
| Shared session/engine across tests | ✅ None — engine, sessionmaker and DB path are function-local |

The previous async conversion did not introduce new defects. The remaining three failures were assertion-level, not session-level, and are analyzed below.

---

## 2. Failure 1 — `test_activity_event_creation` (expected 6, got 7)

### Actual event sequence (7 events, newest-first)

| # (newest→oldest) | Kind | Source |
|---|---|---|
| 1 | `generation_complete` | recorded in test |
| 2 | `scene_complete` (scene 2) | recorded in test |
| 3 | `scene_complete` (scene 1) | recorded in test |
| 4 | `generation_started` | recorded in test |
| 5 | `planning_complete` | recorded in test |
| 6 | `planning_started` | recorded in test |
| 7 | `project_created` | recorded in test |

### Root cause

The assertion was **stale**, not the implementation:

1. The fixture makes **seven** explicit `record_activity` calls — including `2× scene_complete`.
2. The real worker emits **one `scene_complete` per scene**: `workers/generation_worker.py` line ~440 (`publish_activity(..., event="scene_complete", title=f"Scene {scene.scene_number} generated", ...)`).
3. The project's own contract document `docs/AGENT_ACTIVITY_ACCEPTANCE_REPORT.md` enumerates the same seven events (`project_created, planning_started, planning_complete, generation_started, 2× scene_complete, generation_complete`) while mislabelling the total as "6 events" — the count was written before the second `scene_complete` was added.
4. No duplicate or spurious event exists; `record_activity` performs one insert per call and is the only code path that constructs `Activity` rows.

**Conclusion:** 7 events is the correct contract. `6` was a stale expectation.

### Fix

Expectation updated to 7 and the count assertion strengthened into an exact newest-first kind-sequence assertion, so the test now pins the documented ordering contract rather than a bare count. All per-event field assertions were kept.

---

## 3. Failure 2 — `test_activity_ordering_and_replay` (nondeterministic order)

### Diagnosis (measured, not assumed)

Fixing the async session revealed a genuine ordering defect. `activity_for_user` orders by `Activity.created_at.desc()` **as the only key**, and `created_at` is a Python-side `utcnow()` default. Three consecutive `record_activity` calls commit within one Windows clock tick, so two or three events can receive an **identical** timestamp.

Diagnostic run (real engine, real service, three repetitions):

```
run 0: .418562 e3 | .414569 e2 | .410589 e1     (distinct)
run 1: .570975 e3 | .566952 e2 | .560289 e1     (distinct)
run 2: .717281 e3 | .701493 e1 | .701493 e2     (e1 == e2 -> tie, order flipped)
```

The tie in run 2 reproduces the flaky failure exactly: with equal `created_at`, SQLite returns an arbitrary row order, so `events[0]` alternated between `event_type_1`, `event_type_2` and `event_type_3` across runs. The documented contract in `docs/AGENT_ACTIVITY_ACCEPTANCE_REPORT.md` — "Events have stable IDs and ordering … ordered newest-first by `created_at`" and replay oldest-first — is violated whenever timestamps tie.

### Fix (production, smallest justified)

`backend/app/services/project_service.py` → `record_activity` now assigns a **strictly monotonic** `created_at` per project: it reads `MAX(created_at)` for the same project (or the same user when `project_id` is `NULL`) and, if the new timestamp is not strictly greater, advances it by 1 microsecond.

- Portable: plain `func.max` + Python `timedelta`, no dialect-specific `rowid`/`ctid`, so it behaves identically on SQLite and the Neon PostgreSQL target.
- No schema change, no migration.
- Ordering semantics unchanged for normal traffic (real events are seconds apart); only the pathological same-tick case is made deterministic.
- Covers every insert path: `record_activity` is the only constructor of `Activity` rows (verified by search).

Both consumers benefit automatically because they both order by `created_at`: `/activity` (`created_at.desc()`) and `/activity/replay` (`created_at.asc()`).

---

## 4. Failure 3 — `test_activity_event_kinds_from_generation` (expected 6, got 7)

### Root cause

Same stale-count defect as Failure 1, independently confirmed:

- The fixture creates **two** `Scene` rows and records `scene_complete` once per scene.
- `generation_worker` emits `scene_complete` per scene and one terminal `generation_complete`.
- The set check (`required_kinds`) already passed: all six kinds were present. Only the count was wrong, because `scene_complete` legitimately appears twice while contributing one kind.

No unintended duplicate lifecycle event exists, and no worker event was removed.

### Fix

Count updated to 7 with an explicit per-scene invariant (`scene_complete` count == 2). The required-kinds assertions were left intact.

---

## 5. Changes Made

| File | Change |
|------|--------|
| `backend/app/services/project_service.py` | `record_activity` guarantees strictly increasing `created_at` per project (reads `MAX(created_at)`, bumps by 1 µs on collision), removing nondeterministic activity ordering |
| `tests/test_activity_engine.py` | Test 1: expectation 6 → 7 plus exact newest-first kind-sequence assertion. Test 4: expectation 6 → 7 plus `scene_complete` count == 2 assertion. No assertions removed, no tests skipped, no xfail |

Nothing else was modified: no test deleted, no assertion weakened, no Neon credential or production database touched, no Alembic migration run.

---

## 6. Individual Test Results

| Test | Result |
|------|--------|
| `test_activity_event_creation` | ✅ PASS |
| `test_activity_ordering_and_replay` | ✅ PASS |
| `test_activity_multi_user_isolation` | ✅ PASS |
| `test_activity_event_kinds_from_generation` | ✅ PASS |

## 7. Full Regression Results

```
tests/test_api.py                 5 passed
tests/test_security.py            4 passed
tests/test_local_e2e.py           1 passed
tests/test_continuity_engine.py  13 passed
tests/test_activity_engine.py     4 passed
--------------------------------------------
27 passed, 17 warnings in 7.41s   (exit 0, 0 failed, 0 skipped)
```

Frontend production build (`frontend: npm run build`, Next.js 14.2.35):

```
✓ Compiled successfully
✓ Linting and checking validity of types
✓ Generating static pages (10/10)
build_exit=0
```

All 10 routes built; TypeScript validation passed as part of the build.

## 8. Data Preservation Evidence

| Check | Result |
|-------|--------|
| `data/studio.db` exists | ✅ `True` |
| `data/studio.db` size | ✅ `372,736` bytes |
| `data/studio.db` SHA-256 | ✅ `012f08c875448ea5d3b966b3908db062241008041ff9df2123be910d603d0eef` — identical to the pre-mission hash |
| Tests used production DB? | ❌ No — every activity test creates its own `tempfile.mkdtemp()` SQLite file |
| Neon production database accessed? | ❌ No |
| `.env` committed / secrets printed? | ❌ No — `.gitignore` still covers `.env`, `.env.*`, `frontend/.env*.local`; no URLs or secrets appear in test output |
| Alembic migrations run? | ❌ No |
| Paid services enabled? | ❌ No (₹0) |

## 9. Remaining Limitations

1. **Monotonic guarantee is per-writer.** The 1 µs bump is computed inside `record_activity`; two *simultaneous* writers using separate connections could still collide. This app records activity through the worker/API in a mostly serialized lifecycle, so the risk is negligible, and a schema-level sequence (`BIGSERIAL`) would add migration cost for no practical gain here. The new assertion would surface the problem immediately if it ever occurred.
2. **One extra SELECT per activity write.** Activity writes are low-frequency (project lifecycle plus one per scene), so the cost is immaterial; it was preferred over denormalising a sequence column.
3. **Pytest warnings remain:** `PytestUnknownMarkWarning` for `@pytest.mark.activity` / `@pytest.mark.continuity` (unregistered marks). Harmless; unrelated to this mission and not silenced.
4. **Frontend kinds grep:** the frontend activity panel renders backend-supplied events generically, so no kind constant needed updating for the 7-event sequence.
5. **No git repository** in this workspace, so changes are reported by file rather than by diff/commit.

---

## Acceptance Checklist

| Criterion | Status |
|-----------|--------|
| All four activity-engine tests pass | ✅ 4/4 |
| All 27 backend regression tests pass | ✅ 27/27 (0 failed, 0 skipped) |
| Assertions still verify meaningful behavior | ✅ Counts tightened into sequence/per-scene invariants; field, ordering, isolation and kind-set assertions retained |
| Multi-user isolation remains intact | ✅ `test_activity_multi_user_isolation` passes with ownership filters unchanged |
| Local SQLite untouched | ✅ Same size and SHA-256 |
| Frontend production build succeeds | ✅ 10/10 routes, type check passed |
| No Neon migration / cloud deployment | ✅ Not performed |

**Status: COMPLETE — 27/27 passing, verified by execution.**
