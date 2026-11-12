from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: EmailStr
    display_name: str
    is_active: bool
    role: str
    storage_used_bytes: int = 0
    created_at: datetime


class AuthResponse(BaseModel):
    user: UserOut
    csrf_token: str


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(min_length=1, max_length=80)

    @field_validator("password")
    @classmethod
    def password_strength(cls, value: str) -> str:
        if value.lower() in {"password", "12345678", "qwertyui"}:
            raise ValueError("Password is too common")
        if not any(c.isalpha() for c in value) or not any(c.isdigit() for c in value):
            raise ValueError("Password must contain letters and numbers")
        return value


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class ProfileUpdateIn(BaseModel):
    display_name: str = Field(min_length=1, max_length=80)


class PasswordChangeIn(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)


class AccountDeleteIn(BaseModel):
    password: str


class PasswordResetRequestIn(BaseModel):
    email: EmailStr


class PasswordResetConfirmIn(BaseModel):
    token: str
    new_password: str = Field(min_length=8, max_length=128)


class CharacterIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=4000)
    age_range: str | None = Field(default=None, max_length=60)
    appearance: dict | None = None
    voice_description: str | None = None
    reference_notes: str | None = None


class ProjectCreateIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    script: str = Field(min_length=20, max_length=50000)
    genre: str | None = Field(default=None, max_length=80)
    style: str = Field(default="cinematic photorealistic short film", max_length=1000)
    orientation: Literal["landscape", "portrait", "square"] = "landscape"
    aspect_ratio: str = "16:9"
    target_duration_seconds: int = Field(default=48, ge=4, le=600)
    target_scene_count: int = Field(default=6, ge=1, le=20)
    scene_seconds: int = Field(default=8, ge=1, le=10)
    tier: Literal["fast", "quality"] = "fast"
    resolution: str = "1280x720"
    quality: Literal["standard", "high"] = "standard"
    provider: Literal["simulated", "taaft"] = "simulated"
    auto_start: bool = False
    start_planning: bool = True
    voiceover_instructions: str | None = Field(default=None, max_length=4000)
    music_instructions: str | None = Field(default=None, max_length=4000)
    reference_notes: str | None = Field(default=None, max_length=4000)
    characters: list[CharacterIn] = Field(default_factory=list)


class ProjectUpdateIn(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    genre: str | None = None
    style: str | None = Field(default=None, max_length=1000)
    auto_start: bool | None = None
    voiceover_instructions: str | None = None
    music_instructions: str | None = None
    reference_notes: str | None = None


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    script: str
    genre: str | None
    logline: str | None
    style: str
    orientation: str
    aspect_ratio: str
    target_duration_seconds: int
    target_scene_count: int
    scene_seconds: int
    tier: str
    resolution: str
    quality: str
    provider: str
    execution_mode: str
    executor: str | None
    status: str
    progress: int
    error: str | None
    auto_start: bool
    plan_revision: int
    final_video_id: str | None
    report: dict | None
    voiceover_instructions: str | None
    music_instructions: str | None
    reference_notes: str | None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


class ProjectListOut(BaseModel):
    items: list[ProjectOut]
    total: int


class ProjectDetailOut(ProjectOut):
    scenes: list["SceneOut"]
    characters: list["CharacterOut"]
    active_job: "JobOut | None" = None


class CharacterOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    age_range: str | None
    description: str
    appearance: dict | None
    voice_description: str | None
    reference_notes: str | None
    position: int


class SceneOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    scene_number: int
    title: str
    narrative_purpose: str | None
    duration: float
    environment: str | None
    character_presence: list | None
    actions: str | None
    camera: str | None
    lighting: str | None
    visual_style: str | None
    prompt: str
    negative_prompt: str | None
    reference_assets: list | None
    continuity: str | None
    previous_scene_relationship: str | None
    next_scene_relationship: str | None
    narration: str | None
    dialogue: str | None
    script_segment: str | None
    continuation_passage: str | None
    frame_analysis: str | None
    final_prompt: str | None
    status: str
    generation_id: str | None
    provider_status: str | None
    attempt_count: int
    download_status: str
    local_path: str | None
    output_checksum: str | None
    last_frame_path: str | None
    error: str | None
    duration_actual: float | None
    width: int | None
    height: int | None
    fps: float | None
    mode: str | None
    parent_generation_id: str | None
    started_at: datetime | None
    completed_at: datetime | None


class SceneUpdateIn(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    prompt: str | None = Field(default=None, max_length=8000)
    narration: str | None = None
    dialogue: str | None = None
    camera: str | None = None
    lighting: str | None = None
    continuity: str | None = None
    duration: float | None = Field(default=None, ge=1, le=10)
    negative_prompt: str | None = None
    environment: str | None = None
    narrative_purpose: str | None = None
    script_segment: str | None = None
    continuation_passage: str | None = None
    frame_analysis: str | None = None
    final_prompt: str | None = None


class SceneReorderIn(BaseModel):
    scene_ids: list[str] = Field(min_length=1)


class SceneReorderIn(BaseModel):
    scene_ids: list[str] = Field(min_length=1)


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str | None
    kind: str
    status: str
    attempts: int
    max_attempts: int
    last_error: str | None
    available_at: datetime
    created_at: datetime
    updated_at: datetime


class ProviderOut(BaseModel):
    provider: str
    display_name: str
    description: str
    status: str
    connectable: bool
    requires_consent: bool
    connected: bool
    account_ref: str | None = None
    usage: dict | None = None
    last_verified_at: datetime | None = None
    notes: str | None = None


class ProviderConnectIn(BaseModel):
    accept_terms: bool = False


class VideoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str | None
    scene_id: str | None
    kind: str
    filename: str
    size_bytes: int
    mime_type: str
    duration_seconds: float | None
    width: int | None
    height: int | None
    has_audio: bool
    checksum_sha256: str | None
    created_at: datetime
    stream_url: str | None = None
    download_url: str | None = None
    thumbnail_url: str | None = None


class VideoListOut(BaseModel):
    items: list[VideoOut]
    total: int


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str | None
    kind: str
    title: str
    body: str
    read_at: datetime | None
    created_at: datetime


class PushSubscribeIn(BaseModel):
    endpoint: str
    p256dh: str
    auth: str


class UsageOut(BaseModel):
    projects_total: int
    projects_active: int
    videos_total: int
    scenes_generated: int
    storage_used_bytes: int
    storage_quota_bytes: int
    generations_this_month: int


class PublicConfigOut(BaseModel):
    app_name: str
    environment: str
    execution_mode: str
    simulated_provider_enabled: bool
    taaft_enabled: bool
    max_scenes_per_project: int
    max_scene_seconds: int
    max_reference_upload_mb: int
    push_configured: bool


class LocalTokenCreateIn(BaseModel):
    label: str = Field(default="Local worker", max_length=120)


class LocalTokenOut(BaseModel):
    id: str
    label: str
    created_at: datetime
    last_used_at: datetime | None
    revoked_at: datetime | None


class LocalTokenCreatedOut(LocalTokenOut):
    token: str


class LocalClaimOut(BaseModel):
    job: dict
    project: dict
    scenes: list[dict]
    characters: list[dict]
    provider: dict
    execution_mode: str


class LocalCheckpointIn(BaseModel):
    project_status: str | None = None
    progress: int | None = None
    logline: str | None = None
    plan_scenes: list[dict] | None = None
    characters: list[dict] | None = None
    scene_updates: list[dict] | None = None
    enqueue_assemble: bool = False
    message: str | None = None


class LocalFailIn(BaseModel):
    error: str = Field(max_length=8000)


class MessageOut(BaseModel):
    message: str


class MediaAssetOut(BaseModel):
    kind: str
    key: str
    filename: str
    size_bytes: int
    content_type: str


class ActivityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    project_id: str | None
    kind: str
    title: str
    body: str
    meta: dict
    created_at: datetime


class ActivityListOut(BaseModel):
    items: list[ActivityOut]
    total: int


ProjectDetailOut.model_rebuild()
