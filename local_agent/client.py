from __future__ import annotations

import time
from pathlib import Path
from urllib.parse import urljoin

import requests


class LocalApiError(RuntimeError):
    pass


class LocalApiClient:
    """HTTP client for the scoped local execution protocol.

    The bearer token is only ever sent in the Authorization header. It is never
    written to logs or persisted by this client.
    """

    def __init__(self, api_url: str, token: str, timeout: int = 60) -> None:
        self.api_url = api_url.rstrip("/")
        self.token = token
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(
            {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        )

    def _url(self, path: str) -> str:
        if path.startswith("http://") or path.startswith("https://"):
            return path
        if not path.startswith("/"):
            path = "/" + path
        return f"{self.api_url}{path}"

    def _request(self, method: str, path: str, **kwargs) -> requests.Response:
        response = self.session.request(method, self._url(path), timeout=self.timeout, **kwargs)
        if response.status_code >= 400:
            detail = response.text[:1000]
            raise LocalApiError(f"{method} {path} failed ({response.status_code}): {detail}")
        return response

    def claim(self) -> dict | None:
        response = self.session.post(self._url("/api/execution/claim"), timeout=self.timeout)
        if response.status_code == 204:
            return None
        if response.status_code >= 400:
            raise LocalApiError(f"claim failed ({response.status_code}): {response.text[:500]}")
        return response.json()

    def heartbeat(self, job_id: str) -> dict:
        return self._request("POST", f"/api/execution/jobs/{job_id}/heartbeat").json()

    def state(self, job_id: str) -> dict:
        return self._request("GET", f"/api/execution/jobs/{job_id}/state").json()

    def checkpoint(self, job_id: str, payload: dict) -> dict:
        return self._request("POST", f"/api/execution/jobs/{job_id}/checkpoint", json=payload).json()

    def complete(self, job_id: str, result: dict | None = None) -> dict:
        return self._request(
            "POST", f"/api/execution/jobs/{job_id}/complete", json=result or {}
        ).json()

    def fail(self, job_id: str, error: str) -> dict:
        return self._request("POST", f"/api/execution/jobs/{job_id}/fail", json={"error": error}).json()

    def upload_scene(self, job_id: str, scene_id: str, path: Path, kind: str = "video") -> dict:
        with path.open("rb") as handle:
            files = {"file": (path.name, handle, "application/octet-stream")}
            response = self.session.post(
                self._url(f"/api/execution/jobs/{job_id}/upload/scene"),
                params={"scene_id": scene_id, "kind": kind},
                files=files,
                timeout=600,
            )
        if response.status_code >= 400:
            raise LocalApiError(f"scene upload failed ({response.status_code}): {response.text[:1000]}")
        return response.json()

    def upload_final(self, job_id: str, final_path: Path, thumbnail: Path | None) -> dict:
        handles = []
        try:
            files = {"file": (final_path.name, final_path.open("rb"), "video/mp4")}
            handles.append(files["file"][1])
            if thumbnail is not None and thumbnail.exists():
                thumb_handle = thumbnail.open("rb")
                handles.append(thumb_handle)
                files["thumbnail"] = (thumbnail.name, thumb_handle, "image/jpeg")
            response = self.session.post(
                self._url(f"/api/execution/jobs/{job_id}/upload/final"),
                files=files,
                timeout=1800,
            )
            if response.status_code >= 400:
                raise LocalApiError(f"final upload failed ({response.status_code}): {response.text[:1200]}")
            return response.json()
        finally:
            for handle in handles:
                try:
                    handle.close()
                except Exception:
                    pass

    def download(self, signed_path: str, destination: Path, retries: int = 3) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        last_error: Exception | None = None
        for attempt in range(retries):
            try:
                with self.session.get(self._url(signed_path), stream=True, timeout=600) as response:
                    if response.status_code >= 400:
                        raise LocalApiError(f"download failed ({response.status_code})")
                    temp = destination.with_suffix(destination.suffix + ".part")
                    with temp.open("wb") as handle:
                        for chunk in response.iter_content(1024 * 1024):
                            if chunk:
                                handle.write(chunk)
                    temp.replace(destination)
                if destination.stat().st_size == 0:
                    raise LocalApiError("downloaded file is empty")
                return destination
            except Exception as error:  # noqa: BLE001
                last_error = error
                time.sleep(min(10, 2 ** attempt))
        raise LocalApiError(f"download failed after retries: {last_error}")
