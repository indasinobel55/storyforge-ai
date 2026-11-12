# AI Video Studio — Final Verification Plan

This plan records the end-to-end verification run for AI Video Studio on the Windows development machine. It exists so the final report has a reproducible audit trail: what was tested, in what order, with what commands, and how each result was judged.

## Scope and hard constraints

- Work happens in `C:\AI_Video_Studio`.
- No paid infrastructure is purchased or activated.
- No real TAAFT quota is consumed.
- Simulated provider is used for all generation verification.
- Docker verification happens only if Docker is available in the environment.

## Execution order

1. Environment/Dependency check
2. Fresh-database Alembic verification
3. Backend tests
4. Frontend production build
5. Full simulated E2E generation
6. FFmpeg validation of the final MP4
7. Worker crash/recovery test
8. Multi-user isolation test
9. Execution-mode verification (local + cloud configuration)
10. Docker verification (only if available)
11. Mobile/PWA manual checklist preparation
12. TAAFT status recording

## Environment/Dependency check

Check:
- `python --version`
- `node --version`
- `npm --version`
- `ffmpeg` availability (system PATH and via `imageio_ffmpeg`)
- Redis availability
- PostgreSQL availability
- Docker availability
- Docker Compose availability
- `pip check`
- `.env.example` contents
- `.gitignore` and `.dockerignore` hygiene

Expected outcome: Python/Node/npm present, FFmpeg available through `imageio_ffmpeg` or PATH, no broken pip requirements, secrets not tracked.

## Fresh-database Alembic verification

Procedure:
1. Create a fresh temporary directory.
2. Copy `.env.example` and add a generated `SECRET_KEY`.
3. Set `AUTO_CREATE_SCHEMA=false`.
4. Set `DATABASE_URL` to a new SQLite file in the temporary directory.
5. Set `STORAGE_DIR` to a new temporary storage directory.
6. Run `alembic upgrade head`.
7. Enumerate tables directly from the database file.
8. Confirm the `alembic_version` row.

Expected outcome: migration succeeds, expected tables exist, registration works with `AUTO_CREATE_SCHEMA=false`.

## Backend tests

Command:
```bash
python -m pytest -q
```

Expected outcome: all tests pass, exit code 0.

## Frontend production build

Command from `frontend/`:
```bash
rm -rf .next
npm run build
```

Expected outcome: compiled, type-checked, and all expected routes generated.

## Full simulated E2E generation

Procedure:
1. Start the backend against a fresh DB and storage directory.
2. Register a new test user.
3. Create a project with a multi-scene script, `auto_start=True`, `provider='simulated'`.
4. Run `GenerationWorker` until `status == 'COMPLETED'`.
5. Fetch the final video object.
6. Download `/api/videos/{id}/download`.
7. Verify:
   - file exists,
   - file size nonzero,
   - SHA256 of downloaded file matches the API object,
   - FFmpeg can decode the file,
   - video stream present,
   - audio stream present where expected.

Expected outcome: a real MP4 is produced, checksum matches, FFmpeg decodes it.

## FFmpeg validation

Use the FFmpeg binary available to the environment. If `ffmpeg` is not on PATH, use the `imageio_ffmpeg` bundled binary directly.

Checks:
- decode to null without errors,
- report video stream presence,
- report audio stream presence where expected,
- report duration and resolution if the FFmpeg build supports the needed queries.

## Worker crash/recovery test

Procedure:
1. Start a project with `auto_start=True`.
2. Start a worker.
3. Let it make partial progress.
4. Abandon that worker.
5. Start a second worker.
6. Verify the project still reaches `COMPLETED`.
7. Verify completed scenes stay `SUCCEEDED`.
8. Verify job attempt counts do not explode.

Expected outcome: recovery is observable and does not duplicate work.

## Multi-user isolation test

Procedure:
1. Register Alice.
2. Register Bob.
3. Alice creates a project and completes the pipeline.
4. Bob attempts to:
   - list/read Alice's project,
   - approve Alice's project,
   - access Alice's scenes,
   - download Alice's final video.
5. Verify Alice can access her own project and video.

Expected outcome: all of Bob's unauthorized attempts are rejected; Alice's access succeeds.

## Execution-mode verification

Check:
- Local mode executes through the local path.
- Cloud mode configuration is supported.
- Mode switching does not corrupt project data in the available test shape.
- Cloud mode is reported honestly: configuration and simulated cloud path may work, but a real detached cloud worker is a separate deployment claim.

## Docker verification

If Docker is available:
- validate compose config,
- build images,
- start the stack,
- verify migrations, auth, project creation, queue processing, FFmpeg in-container, and volume persistence.

If Docker is unavailable: record BLOCKED.

## Mobile/PWA manual checklist

Prepare a concise checklist for manual phone testing:
- registration, login, dashboard, project creation, script submission, planning,
  timeline, approval, generation start, progress, completion, preview, download,
  settings, videos list, weak-network behavior, reload behavior, PWA install.

Do not claim physical device testing unless it has been performed.

## TAAFT status

Record:
- adapter exists,
- TAAFT is gated by default,
- simulated provider is used for verification,
- real provider is not authorized or exercised in this session.

## Acceptance gates

- G1 — Development environment works
- G2 — Database migration and persistence work
- G3 — Frontend production build passes
- G4 — Backend tests pass
- G5 — Complete simulated video generation works
- G6 — FFmpeg assembly and validation work
- G7 — Worker restart recovery works
- G8 — Multi-user isolation works
- G9 — Local execution mode works
- G10 — Cloud execution configuration works in the scope actually deployed
- G11 — Docker stack works, if Docker is available
- G12 — Responsive mobile browser tests pass
- G13 — PWA functionality passes where testable
- G14 — TAAFT feasibility and authorization status is documented

Each gate is recorded as PASS, PARTIAL, BLOCKED, FAIL, or NOT IMPLEMENTED in the final report, with evidence.

## Evidence artifacts

- `docs/FINAL_VERIFICATION_REPORT.md`
- `PROJECT_COMPLETION_REPORT.md`
- pytest output
- `npm run build` output
- final MP4 location and checksum
- FFmpeg decode evidence
