from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import sessionmaker

# ──────────────────────────────────────────────────────────────────────
# Test 1: Activity event creation and persistence
# ──────────────────────────────────────────────────────────────────────

@pytest.mark.activity
def test_activity_event_creation():
    """Verify activity events are persisted in the database."""
    from backend.app.database import engine as _engine
    from backend.app.models import Activity, Project, User
    from backend.app.services.project_service import record_activity, activity_for_user

    tmp_dir = tempfile.mkdtemp(prefix="activity_test_")
    db_path = os.path.join(tmp_dir, "test.db")
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{db_path}"
    os.environ["STORAGE_DIR"] = os.path.join(tmp_dir, "storage")
    os.environ["AUTO_CREATE_SCHEMA"] = "true"

    engine = create_async_engine(os.environ["DATABASE_URL"], echo=False)
    from backend.app.database import Base

    async def _init_db():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(_init_db())

    SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async def _test():
        async with SessionLocal() as db:
            user = (await db.execute(select(User).limit(1))).scalar_one_or_none()
            if user is None:
                from backend.app.models import User as UserModel
                user = UserModel(
                    id="activity-test-user",
                    email="activity@test.local",
                    password_hash="hash",
                    display_name="Activity Tester",
                    is_active=True,
                    role="user",
                )
                db.add(user)
                await db.commit()
                await db.refresh(user)

            project = Project(
                user_id=user.id,
                title="Activity Test Project",
                script="Alice finds a key. She opens a door. She enters a room.",
                genre="test",
                style="cinematic photorealistic short film",
                orientation="landscape",
                aspect_ratio="16:9",
                target_duration_seconds=24,
                target_scene_count=3,
                scene_seconds=8,
                tier="fast",
                resolution="1280x720",
                quality="standard",
                provider="simulated",
                execution_mode="cloud",
                status="DRAFT",
            )
            db.add(project)
            await db.commit()
            await db.refresh(project)

            await record_activity(
                db,
                user_id=user.id,
                project_id=project.id,
                kind="project_created",
                title="Project created",
                body="New project initiated for activity testing",
            )

            await record_activity(
                db,
                user_id=user.id,
                project_id=project.id,
                kind="planning_started",
                title="Planning started",
                body="Script analysis began",
            )

            await record_activity(
                db,
                user_id=user.id,
                project_id=project.id,
                kind="planning_complete",
                title="Planning complete",
                body="Scenes and prompts generated",
            )

            await record_activity(
                db,
                user_id=user.id,
                project_id=project.id,
                kind="generation_started",
                title="Generation started",
                body="Scene generation began",
            )

            await record_activity(
                db,
                user_id=user.id,
                project_id=project.id,
                kind="scene_complete",
                title="Scene 1 generated",
                body="First scene clip generated successfully",
                meta={"scene_number": 1, "duration": 8.0},
            )

            await record_activity(
                db,
                user_id=user.id,
                project_id=project.id,
                kind="scene_complete",
                title="Scene 2 generated",
                body="Second scene clip generated successfully",
                meta={"scene_number": 2, "duration": 8.0},
            )

            await record_activity(
                db,
                user_id=user.id,
                project_id=project.id,
                kind="generation_complete",
                title="All scenes generated",
                body="All 3 scenes generated and ready for assembly",
            )

            events = await activity_for_user(db, user_id=user.id, project_id=project.id)
            # 7 events: project_created, planning_started, planning_complete,
            # generation_started, one scene_complete per generated scene (2),
            # and generation_complete. The previous "6" predates the second
            # scene_complete that the worker emits for each generated scene.
            assert len(events) == 7, f"Expected 7 events, got {len(events)}"
            assert [e.kind for e in events] == [
                "generation_complete",
                "scene_complete",
                "scene_complete",
                "generation_started",
                "planning_complete",
                "planning_started",
                "project_created",
            ], f"Unexpected newest-first event order: {[e.kind for e in events]}"

            for event in events:
                assert event.id is not None, "Activity event should have an ID"
                assert event.kind is not None, "Activity event should have a kind"
                assert event.title is not None, "Activity event should have a title"
                assert event.body is not None, "Activity event should have a body"
                assert event.created_at is not None, "Activity event should have a created_at"
                assert event.user_id == user.id, "Activity event should belong to the correct user"
                assert event.project_id == project.id, "Activity event should belong to the correct project"

            for i in range(len(events) - 1):
                assert events[i].created_at >= events[i + 1].created_at, (
                    f"Events should be ordered newest-first, but {events[i].created_at} < {events[i+1].created_at}"
                )

            print("--- test_activity_event_creation PASSED ---")

    asyncio.run(_test())


# ──────────────────────────────────────────────────────────────────────
# Test 2: Activity ordering and replay
# ──────────────────────────────────────────────────────────────────────

@pytest.mark.activity
def test_activity_ordering_and_replay():
    """Verify activity events have stable ordering and replay works."""
    from backend.app.database import engine as _engine
    from backend.app.models import Project, User
    from backend.app.services.project_service import record_activity, activity_for_user, activity_count_for_user

    tmp_dir = tempfile.mkdtemp(prefix="activity_replay_test_")
    db_path = os.path.join(tmp_dir, "test.db")
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{db_path}"
    os.environ["STORAGE_DIR"] = os.path.join(tmp_dir, "storage")
    os.environ["AUTO_CREATE_SCHEMA"] = "true"

    engine = create_async_engine(os.environ["DATABASE_URL"], echo=False)
    from backend.app.database import Base

    async def _init_db():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(_init_db())

    SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async def _test():
        async with SessionLocal() as db:
            user = (await db.execute(select(User).limit(1))).scalar_one_or_none()
            if user is None:
                from backend.app.models import User as UserModel
                user = UserModel(
                    id="replay-test-user",
                    email="replay@test.local",
                    password_hash="hash",
                    display_name="Replay Tester",
                    is_active=True,
                    role="user",
                )
                db.add(user)
                await db.commit()
                await db.refresh(user)

            project = Project(
                user_id=user.id,
                title="Replay Test Project",
                script="Alice starts her journey. She continues to the river. She reaches her destination.",
                genre="test",
                style="cinematic photorealistic short film",
                orientation="landscape",
                aspect_ratio="16:9",
                target_duration_seconds=24,
                target_scene_count=3,
                scene_seconds=8,
                tier="fast",
                resolution="1280x720",
                quality="standard",
                provider="simulated",
                execution_mode="cloud",
                status="DRAFT",
            )
            db.add(project)
            await db.commit()
            await db.refresh(project)

            await record_activity(db, user_id=user.id, project_id=project.id, kind="event_type_1", title="Event 1", body="First event")
            await record_activity(db, user_id=user.id, project_id=project.id, kind="event_type_2", title="Event 2", body="Second event")
            await record_activity(db, user_id=user.id, project_id=project.id, kind="event_type_3", title="Event 3", body="Third event")

            events = await activity_for_user(db, user_id=user.id, project_id=project.id)
            assert len(events) == 3

            assert events[0].kind == "event_type_3", f"First event should be type 3, got {events[0].kind}"
            assert events[1].kind == "event_type_2", f"Second event should be type 2, got {events[1].kind}"
            assert events[2].kind == "event_type_1", f"Third event should be type 1, got {events[2].kind}"

            count = await activity_count_for_user(db, user_id=user.id, project_id=project.id)
            assert count == 3

            print("--- test_activity_ordering_and_replay PASSED ---")

    asyncio.run(_test())


# ──────────────────────────────────────────────────────────────────────
# Test 3: Multi-user activity isolation
# ──────────────────────────────────────────────────────────────────────

@pytest.mark.activity
def test_activity_multi_user_isolation():
    """Verify different users can only access their own activity."""
    from backend.app.database import engine as _engine
    from backend.app.models import User
    from backend.app.services.project_service import record_activity, activity_for_user

    tmp_dir = tempfile.mkdtemp(prefix="activity_isolation_test_")
    db_path = os.path.join(tmp_dir, "test.db")
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{db_path}"
    os.environ["STORAGE_DIR"] = os.path.join(tmp_dir, "storage")
    os.environ["AUTO_CREATE_SCHEMA"] = "true"

    engine = create_async_engine(os.environ["DATABASE_URL"], echo=False)
    from backend.app.database import Base

    async def _init_db():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(_init_db())

    SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async def _test():
        async with SessionLocal() as db:
            user_a = (await db.execute(select(User).limit(1))).scalar_one_or_none()
            if user_a is None:
                from backend.app.models import User as UserModel
                from backend.app.models import Project
                from backend.app.services.project_service import record_activity, activity_for_user
                user_a = UserModel(
                    id="iso-user-a",
                    email="a@test.local",
                    password_hash="hash",
                    display_name="User A",
                    is_active=True,
                    role="user",
                )
                db.add(user_a)

            user_b = (await db.execute(select(User).offset(1).limit(1))).scalar_one_or_none()
            if user_b is None:
                from backend.app.models import User as UserModel
                user_b = UserModel(
                    id="iso-user-b",
                    email="b@test.local",
                    password_hash="hash",
                    display_name="User B",
                    is_active=True,
                    role="user",
                )
                db.add(user_b)

            await db.commit()

            project_a = Project(
                user_id=user_a.id,
                title="User A Project",
                script="Alice finds a key.",
                genre="test",
                style="cinematic",
                orientation="landscape",
                aspect_ratio="16:9",
                target_duration_seconds=8,
                target_scene_count=1,
                scene_seconds=8,
                tier="fast",
                resolution="1280x720",
                quality="standard",
                provider="simulated",
                execution_mode="cloud",
                status="DRAFT",
            )
            db.add(project_a)

            project_b = Project(
                user_id=user_b.id,
                title="User B Project",
                script="Bob finds a key.",
                genre="test",
                style="cinematic",
                orientation="landscape",
                aspect_ratio="16:9",
                target_duration_seconds=8,
                target_scene_count=1,
                scene_seconds=8,
                tier="fast",
                resolution="1280x720",
                quality="standard",
                provider="simulated",
                execution_mode="cloud",
                status="DRAFT",
            )
            db.add(project_b)

            await db.commit()
            await db.refresh(project_a)
            await db.refresh(project_b)

            await record_activity(db, user_id=user_a.id, project_id=project_a.id, kind="event_a", title="User A Event", body="Event from user A")
            await record_activity(db, user_id=user_a.id, project_id=project_a.id, kind="event_a2", title="User A Event 2", body="Second event from user A")

            await record_activity(db, user_id=user_b.id, project_id=project_b.id, kind="event_b", title="User B Event", body="Event from user B")

            events_a = await activity_for_user(db, user_id=user_a.id, project_id=project_a.id)
            assert len(events_a) == 2, f"User A should see 2 events, got {len(events_a)}"
            for event in events_a:
                assert event.kind in ("event_a", "event_a2"), f"User A's event should be kind 'event_a' or 'event_a2', got {event.kind}"

            events_a_b = await activity_for_user(db, user_id=user_a.id, project_id=project_b.id)
            assert len(events_a_b) == 0, f"User A should not see User B's events, got {len(events_a_b)}"

            events_b = await activity_for_user(db, user_id=user_b.id, project_id=project_b.id)
            assert len(events_b) == 1, f"User B should see 1 event, got {len(events_b)}"
            assert events_b[0].kind == "event_b", f"User B's event should be kind 'event_b', got {events_b[0].kind}"

            events_b_a = await activity_for_user(db, user_id=user_b.id, project_id=project_a.id)
            assert len(events_b_a) == 0, f"User B should not see User A's events, got {len(events_b_a)}"

            print("--- test_activity_multi_user_isolation PASSED ---")

    asyncio.run(_test())


# ──────────────────────────────────────────────────────────────────────
# Test 4: Activity event kinds from real generation
# ──────────────────────────────────────────────────────────────────────

@pytest.mark.activity
def test_activity_event_kinds_from_generation():
    """Verify activity events cover the full generation pipeline."""
    from backend.app.database import engine as _engine
    from backend.app.models import Activity, Project, User, Scene
    from backend.app.services.project_service import record_activity

    tmp_dir = tempfile.mkdtemp(prefix="activity_kinds_test_")
    db_path = os.path.join(tmp_dir, "test.db")
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{db_path}"
    os.environ["STORAGE_DIR"] = os.path.join(tmp_dir, "storage")
    os.environ["AUTO_CREATE_SCHEMA"] = "true"

    engine = create_async_engine(os.environ["DATABASE_URL"], echo=False)
    from backend.app.database import Base

    async def _init_db():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(_init_db())

    SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async def _test():
        async with SessionLocal() as db:
            user = (await db.execute(select(User).limit(1))).scalar_one_or_none()
            if user is None:
                from backend.app.models import User as UserModel
                from backend.app.models import Project
                from backend.app.services.project_service import record_activity, activity_for_user
                user = UserModel(
                    id="kinds-test-user",
                    email="kinds@test.local",
                    password_hash="hash",
                    display_name="Kinds Tester",
                    is_active=True,
                    role="user",
                )
                db.add(user)
                await db.commit()
                await db.refresh(user)

            project = Project(
                user_id=user.id,
                title="Kinds Test Project",
                script="Alice starts her journey. She reaches her destination.",
                genre="test",
                style="cinematic photorealistic short film",
                orientation="landscape",
                aspect_ratio="16:9",
                target_duration_seconds=16,
                target_scene_count=2,
                scene_seconds=8,
                tier="fast",
                resolution="1280x720",
                quality="standard",
                provider="simulated",
                execution_mode="cloud",
                status="DRAFT",
            )
            db.add(project)
            await db.commit()
            await db.refresh(project)

            for i in range(1, 3):
                scene = Scene(
                    project_id=project.id,
                    scene_number=i,
                    title=f"Scene {i}: Test Scene",
                    narrative_purpose=f"Purpose of scene {i}",
                    duration=8.0,
                    environment="the story world",
                    character_presence=[],
                    actions=f"Action {i}",
                    camera="",
                    lighting="",
                    visual_style="cinematic",
                    prompt=f"Prompt for scene {i}",
                    negative_prompt="text, subtitles, captions, logos, watermarks",
                    continuity="",
                    previous_scene_relationship="Opening scene" if i == 1 else "Concludes the previous beat.",
                    next_scene_relationship="Sets up the next beat." if i < 2 else "Final scene.",
                    narration=f"Narration {i}",
                    dialogue="",
                    script_segment=f"Segment {i}",
                )
                db.add(scene)
            await db.commit()

            await record_activity(db, user_id=user.id, project_id=project.id, kind="project_created", title="Project created", body="New project for kinds testing")

            await record_activity(db, user_id=user.id, project_id=project.id, kind="planning_started", title="Planning started", body="Script analysis began")

            await record_activity(db, user_id=user.id, project_id=project.id, kind="planning_complete", title="Planning complete", body="Scenes and prompts generated")

            await record_activity(db, user_id=user.id, project_id=project.id, kind="generation_started", title="Generation started", body="Scene generation began")

            await record_activity(db, user_id=user.id, project_id=project.id, kind="scene_complete", title="Scene 1 generated", body="First scene clip generated successfully", meta={"scene_number": 1})

            await record_activity(db, user_id=user.id, project_id=project.id, kind="scene_complete", title="Scene 2 generated", body="Second scene clip generated successfully", meta={"scene_number": 2})

            await record_activity(db, user_id=user.id, project_id=project.id, kind="generation_complete", title="All scenes generated", body="All 2 scenes generated and ready for assembly")

            events = await activity_for_user(db, user_id=user.id, project_id=project.id)
            kinds = {e.kind for e in events}

            required_kinds = {
                "project_created",
                "planning_started",
                "planning_complete",
                "generation_started",
                "scene_complete",
                "generation_complete",
            }

            for kind in required_kinds:
                assert kind in kinds, f"Missing event kind: {kind}. Available kinds: {kinds}"

            # 7 events: the six event kinds above plus one scene_complete per
            # scene (this fixture has two scenes, so two scene_complete events).
            assert len(events) == 7, f"Expected 7 events, got {len(events)}"
            assert sum(1 for e in events if e.kind == "scene_complete") == 2

            print("--- test_activity_event_kinds_from_generation PASSED ---")

    asyncio.run(_test())


# ──────────────────────────────────────────────────────────────────────
# Run pytest
# ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v", "--tb=short"]))