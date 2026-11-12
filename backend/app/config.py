from __future__ import annotations

import secrets
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(ROOT_DIR / ".env"), env_file_encoding="utf-8", extra="ignore")

    app_name: str = "StoryForge AI"
    environment: str = "development"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    frontend_origin: str = "http://localhost:3000"
    public_api_url: str = "http://localhost:8000"

    secret_key: str = Field(default_factory=lambda: secrets.token_urlsafe(48))
    session_encryption_key: str | None = None
    session_ttl_hours: int = 24 * 14
    ws_ticket_ttl_seconds: int = 120
    signed_url_ttl_seconds: int = 900
    cookie_secure: bool = False
    auto_create_schema: bool = True
    dev_expose_reset_token: bool = True

    database_url: str = f"sqlite+aiosqlite:///{(ROOT_DIR / 'data' / 'studio.db').as_posix()}"
    storage_dir: str = str(ROOT_DIR / "data" / "storage")
    storage_backend: str = "local"
    s3_endpoint_url: str | None = None
    s3_bucket: str | None = None
    s3_access_key_id: str | None = None
    s3_secret_access_key: str | None = None
    s3_region: str = "auto"

    execution_mode: str = "cloud"  # cloud | local
    simulated_provider_enabled: bool = True
    simulated_generation_seconds: float = 1.5
    simulated_clip_seconds: float = 2.0
    simulated_scene_palette: str = "0x101826|0x1b2a3a|0x23384d|0x2d4a5e|0x3a5d70|0x4a7080"
    taaft_enabled: bool = False
    taaft_poll_seconds: int = 20
    taaft_job_timeout_seconds: int = 3600
    taaft_headless: bool = True
    taaft_chrome_path: str = ""

    planner_llm_enabled: bool = False
    planner_llm_url: str = "https://text.pollinations.ai/openai"
    planner_llm_timeout_seconds: int = 180

    worker_poll_seconds: float = 1.0
    worker_lease_seconds: int = 90
    worker_max_attempts: int = 3
    worker_id_prefix: str = "worker"
    max_active_projects_per_user: int = 1
    max_scenes_per_project: int = 20
    max_reference_upload_mb: int = 12
    max_scene_seconds: int = 10
    usage_storage_quota_mb: int = 2048

    @property
    def storage_path(self) -> Path:
        path = Path(self.storage_dir)
        if not path.is_absolute():
            path = ROOT_DIR / path
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def is_production(self) -> bool:
        return self.environment.lower() in {"production", "prod"}

    @property
    def effective_execution_mode(self) -> str:
        return "local" if self.execution_mode.lower().strip() == "local" else "cloud"

    @property
    def cloud_execution_enabled(self) -> bool:
        return self.effective_execution_mode == "cloud"

    @property
    def local_execution_enabled(self) -> bool:
        return self.effective_execution_mode == "local"

    @property
    def fernet_key(self) -> bytes:
        import base64
        import hashlib

        if self.session_encryption_key:
            return self.session_encryption_key.encode()
        digest = hashlib.sha256(self.secret_key.encode()).digest()
        return base64.urlsafe_b64encode(digest)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
