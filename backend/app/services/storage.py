from __future__ import annotations

import shutil
from abc import ABC, abstractmethod
from pathlib import Path

from ..config import settings


class StorageError(RuntimeError):
    pass


class StorageBackend(ABC):
    @abstractmethod
    async def save_bytes(self, key: str, data: bytes) -> int: ...

    @abstractmethod
    async def save_file(self, key: str, source: Path) -> int: ...

    @abstractmethod
    def local_path(self, key: str) -> Path: ...

    @abstractmethod
    async def delete(self, key: str) -> None: ...

    @abstractmethod
    async def exists(self, key: str) -> bool: ...


class LocalStorage(StorageBackend):
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        if not key or key.startswith(("/", "\\")) or ".." in Path(key).parts:
            raise StorageError("Invalid storage key")
        path = (self.root / key).resolve()
        if not path.is_relative_to(self.root):
            raise StorageError("Storage key escapes root")
        return path

    async def save_bytes(self, key: str, data: bytes) -> int:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(path.suffix + ".part")
        temp.write_bytes(data)
        temp.replace(path)
        return len(data)

    async def save_file(self, key: str, source: Path) -> int:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(path.suffix + ".part")
        shutil.copyfile(source, temp)
        temp.replace(path)
        return path.stat().st_size

    def local_path(self, key: str) -> Path:
        return self._path(key)

    async def delete(self, key: str) -> None:
        path = self._path(key)
        if path.exists():
            path.unlink()

    async def exists(self, key: str) -> bool:
        return self._path(key).exists()


class S3Storage(StorageBackend):
    """S3-compatible storage (Cloudflare R2 / AWS S3 / Backblaze B2).

    Requires the optional ``boto3`` dependency and credentials in the environment.
    """

    def __init__(self) -> None:
        try:
            import boto3
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise StorageError("boto3 is required for S3 storage") from exc
        if not settings.s3_bucket:
            raise StorageError("S3_BUCKET is not configured")
        self.bucket = settings.s3_bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            aws_access_key_id=settings.s3_access_key_id,
            aws_secret_access_key=settings.s3_secret_access_key,
            region_name=settings.s3_region,
        )
        self.cache_root = (Path(settings.storage_dir) / "_s3_cache").resolve()
        self.cache_root.mkdir(parents=True, exist_ok=True)

    async def save_bytes(self, key: str, data: bytes) -> int:  # pragma: no cover - needs S3
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data)
        return len(data)

    async def save_file(self, key: str, source: Path) -> int:  # pragma: no cover - needs S3
        self.client.upload_file(str(source), self.bucket, key)
        return source.stat().st_size

    def local_path(self, key: str) -> Path:  # pragma: no cover - needs S3
        path = self.cache_root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            self.client.download_file(self.bucket, key, str(path))
        return path

    async def delete(self, key: str) -> None:  # pragma: no cover - needs S3
        self.client.delete_object(Bucket=self.bucket, Key=key)

    async def exists(self, key: str) -> bool:  # pragma: no cover - needs S3
        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
            return True
        except Exception:
            return False


def get_storage() -> StorageBackend:
    if settings.storage_backend.lower() == "s3":
        return S3Storage()
    return LocalStorage(settings.storage_path)


storage = get_storage()
