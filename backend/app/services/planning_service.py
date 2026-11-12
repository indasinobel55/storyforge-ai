from __future__ import annotations

import asyncio

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from agent.core.errors import PlanningError
from agent.planner.deterministic import deterministic_plan
from agent.planner.planner import PlanRequest, build_plan
from agent.scenes.spec import CharacterSpec

from ..config import settings
from ..models import Character, GenerationAttempt, Project, Scene
from ..security import utcnow
from .project_service import notify, recompute_progress
from .queue import enqueue_job


def _project_characters(characters: list[Character]) -> list[CharacterSpec]:
    return [
        CharacterSpec(
            name=character.name,
            age_range=character.age_range,
            description=character.description,
            appearance=character.appearance or {},
            voice_description=character.voice_description,
            reference_notes=character.reference_notes,
        )
        for character in characters
    ]


async def execute_planning(db: AsyncSession, project: Project) -> dict:
    result = await db.execute(select(Scene).where(Scene.project_id == project.id))
    existing = list(result.scalars())
    if any(scene.status not in {"PENDING", "FAILED"} for scene in existing):
        raise PlanningError("Cannot regenerate a plan after generation has started")
    for scene in existing:
        await db.execute(delete(GenerationAttempt).where(GenerationAttempt.scene_id == scene.id))
        await db.delete(scene)
    await db.commit()

    characters = list(
        (
            await db.execute(
                select(Character).where(Character.project_id == project.id).order_by(Character.position)
            )
        ).scalars()
    )
    request = PlanRequest(
        title=project.title,
        script=project.script,
        style=project.style,
        scene_count=project.target_scene_count,
        scene_seconds=project.scene_seconds,
        target_duration_seconds=project.target_duration_seconds,
        orientation=project.orientation,
        aspect_ratio=project.aspect_ratio,
        genre=project.genre,
        characters=_project_characters(characters),
        reference_notes=project.reference_notes,
        provider="auto" if settings.planner_llm_enabled else "deterministic",
        llm_url=settings.planner_llm_url,
        llm_timeout_seconds=settings.planner_llm_timeout_seconds,
    )
    plan = await asyncio.to_thread(build_plan, request)

    if not characters and plan.characters:
        for position, spec in enumerate(plan.characters):
            db.add(
                Character(
                    project_id=project.id,
                    name=spec.name,
                    age_range=spec.age_range,
                    description=spec.description,
                    appearance=spec.appearance or {},
                    voice_description=spec.voice_description,
                    reference_notes=spec.reference_notes,
                    position=position,
                )
            )

    for spec in plan.scenes:
        db.add(
            Scene(
                project_id=project.id,
                scene_number=spec.scene_number,
                title=spec.title,
                narrative_purpose=spec.narrative_purpose,
                duration=spec.duration,
                environment=spec.environment,
                character_presence=spec.character_presence,
                actions=spec.actions,
                camera=spec.camera,
                lighting=spec.lighting,
                visual_style=spec.visual_style,
                prompt=spec.prompt,
                negative_prompt=spec.negative_prompt,
                reference_assets=spec.reference_assets,
                continuity=spec.continuity,
                previous_scene_relationship=spec.previous_scene_relationship,
                next_scene_relationship=spec.next_scene_relationship,
                narration=spec.narration,
                dialogue=spec.dialogue,
                script_segment=spec.narration or spec.actions or "",
                status="PENDING",
            )
        )
    project.logline = plan.logline or project.logline
    project.plan_revision += 1
    project.error = None
    project.status = "QUEUED" if project.auto_start else "AWAITING_APPROVAL"
    await db.commit()
    await recompute_progress(db, project)
    await notify(
        db,
        user_id=project.user_id,
        project_id=project.id,
        kind="planning_completed",
        title="Scene plan ready",
        body=f"{len(plan.scenes)} scenes planned for \"{project.title}\". Review and approve to start generation.",
    )
    if project.auto_start:
        await enqueue_job(
            db,
            user_id=project.user_id,
            project_id=project.id,
            kind="GENERATE",
            idempotency_key=f"generate:{project.id}:{project.plan_revision}",
            payload={"plan_revision": project.plan_revision},
            max_attempts=settings.worker_max_attempts,
        )
    return {
        "scene_count": len(plan.scenes),
        "planner": plan.provider,
        "logline": plan.logline,
        "plan_revision": project.plan_revision,
    }


async def regenerate_scene_prompt(db: AsyncSession, project: Project, scene: Scene) -> Scene:
    characters = list(
        (
            await db.execute(
                select(Character).where(Character.project_id == project.id).order_by(Character.position)
            )
        ).scalars()
    )
    source = scene.actions or scene.narration or scene.prompt
    plan = await asyncio.to_thread(
        deterministic_plan,
        source=source,
        title=project.title,
        style=project.style,
        orientation=project.orientation,
        aspect_ratio=project.aspect_ratio,
        target_scenes=1,
        scene_seconds=int(scene.duration),
        target_duration_seconds=project.target_duration_seconds,
        characters=_project_characters(characters),
        genre=project.genre,
        reference_notes=project.reference_notes,
    )
    regenerated = plan.scenes[0]
    scene.prompt = regenerated.prompt
    scene.camera = regenerated.camera
    scene.lighting = regenerated.lighting
    scene.negative_prompt = regenerated.negative_prompt
    scene.visual_style = regenerated.visual_style
    await db.commit()
    await db.refresh(scene)
    return scene


async def approve_plan(db: AsyncSession, project: Project) -> dict:
    scenes = list((await db.execute(select(Scene).where(Scene.project_id == project.id))).scalars())
    if not scenes:
        raise PlanningError("No scenes to approve")
    if any(scene.status in {"SUCCEEDED", "GENERATING"} for scene in scenes):
        return {"message": "Generation already in progress"}
    project.status = "QUEUED"
    project.error = None
    project.started_at = project.started_at or utcnow()
    await db.commit()
    await recompute_progress(db, project)
    await enqueue_job(
        db,
        user_id=project.user_id,
        project_id=project.id,
        kind="GENERATE",
        idempotency_key=f"generate:{project.id}:{project.plan_revision}",
        payload={"plan_revision": project.plan_revision},
        max_attempts=settings.worker_max_attempts,
        revive=True,
    )
    await notify(
        db,
        user_id=project.user_id,
        project_id=project.id,
        kind="project_started",
        title="Generation started",
        body=(
            f"\"{project.title}\" is running locally. Keep the local worker computer powered on."
            if settings.effective_execution_mode == "local"
            else f"\"{project.title}\" is running in the cloud. You can close the browser safely."
        ),
    )
    return {"message": "Generation queued"}
