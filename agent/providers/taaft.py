from __future__ import annotations

import asyncio
import json
import os
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import requests

from agent.core.errors import DownloadError, GenerationError, ProviderAuthError, ProviderDisabledError
from agent.providers.base import GenerationResult, UsageInfo, VideoProvider

GEN_URL = "https://theresanaiforthat.com/@taaft/video-generator/?ref=header"
LOGIN_URL = "https://theresanaiforthat.com/login/?redirect_to=%2F%40taaft%2Fvideo-generator%2F"
TERMINAL_FAIL = {"failed", "error", "canceled", "cancelled"}
TERMINAL_OK = {"succeeded", "success", "completed"}

TRANSIENT_STATUS = {408, 425, 429, 500, 502, 503, 504, 520, 521, 522, 523, 524}
TRANSIENT_RETRY_ATTEMPTS = 5
TRANSIENT_BACKOFF_SECONDS = 5.0

FEASIBILITY_MESSAGE = (
    "Real TAAFT automation is disabled. TAAFT's Terms of Service (updated 2026-03-19) prohibit automated "
    "access and circumventing security without prior written consent. See TAAFT_INTEGRATION_FEASIBILITY.md. "
    "Use the simulated provider until written authorization is obtained."
)


class TaaftProvider(VideoProvider):
    """Isolated per-user TAAFT adapter, ported from the original ``taaft_agent.py``.

    All network automation is gated behind ``TAAFT_ENABLED``. The adapter never
    shares browser profiles between users; it requires a per-user encrypted
    Playwright ``storage_state`` file that is hydrated only inside the worker
    process. It is intentionally not enabled by default.
    """

    name = "taaft"
    display_name = "TAAFT (gated)"
    requires_consent = True

    def __init__(
        self,
        *,
        enabled: bool,
        storage_state_path: Path | None = None,
        profile_dir: Path | None = None,
        chrome_path: str | None = None,
        headless: bool = True,
        poll_seconds: int = 20,
        job_timeout_seconds: int = 3600,
        enhance: bool = False,
        tier: str = "quality",
        orientation: str = "landscape",
    ) -> None:
        self.enabled = enabled
        self.storage_state_path = storage_state_path
        self.profile_dir = Path(profile_dir) if profile_dir else None
        self.chrome_path = chrome_path or os.environ.get("CHROME_PATH") or None
        self.headless = headless
        self.poll_seconds = max(5, poll_seconds)
        self.job_timeout = max(60, job_timeout_seconds)
        self.enhance = enhance
        self.tier = tier
        self.orientation = orientation
        self._sticky_page: Any = None
        self._sticky_context: Any = None

    def _assert_enabled(self) -> None:
        if not self.enabled:
            raise ProviderDisabledError(FEASIBILITY_MESSAGE)

    def _assert_session(self) -> None:
        self._assert_enabled()
        if self.profile_dir is not None:
            return
        if not self.storage_state_path or not self.storage_state_path.exists():
            raise ProviderAuthError("No stored TAAFT session for this user; connect the account first")

    def _resolve_chrome(self) -> str | None:
        for candidate in (
            self.chrome_path,
            "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
            "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
        ):
            if candidate and Path(candidate).exists():
                return str(candidate)
        return None

    @contextmanager
    def _browser_page(self):
        if self._sticky_page is not None:
            yield self._sticky_page
            return
        from playwright.sync_api import sync_playwright

        if self.profile_dir is not None:
            self._assert_enabled()
        else:
            self._assert_session()
        with sync_playwright() as playwright:
            if self.profile_dir is not None:
                # Persistent real-Chrome profile mode: login and Cloudflare trust
                # survive between operations, mirroring the original taaft agent.
                self.profile_dir.mkdir(parents=True, exist_ok=True)
                launch_kwargs: dict[str, Any] = {"headless": self.headless}
                chrome = self._resolve_chrome()
                if chrome:
                    launch_kwargs["executable_path"] = chrome
                context = playwright.chromium.launch_persistent_context(
                    str(self.profile_dir),
                    viewport={"width": 1440, "height": 1100},
                    accept_downloads=True,
                    args=["--disable-blink-features=AutomationControlled", "--start-maximized"],
                    **launch_kwargs,
                )
                page = context.pages[0] if context.pages else context.new_page()
                try:
                    page.goto(GEN_URL, wait_until="domcontentloaded", timeout=90000)
                    self._wait_for_generator(page)
                    yield page
                finally:
                    context.close()
            else:
                launch_kwargs = {"headless": self.headless}
                if self.chrome_path and Path(self.chrome_path).exists():
                    launch_kwargs["executable_path"] = self.chrome_path
                browser = playwright.chromium.launch(**launch_kwargs)
                context = browser.new_context(
                    storage_state=str(self.storage_state_path),
                    viewport={"width": 1440, "height": 1100},
                    accept_downloads=True,
                )
            page = context.new_page()
            try:
                page.goto(GEN_URL, wait_until="domcontentloaded", timeout=90000)
                self._wait_for_generator(page)
                yield page
            finally:
                context.close()
                browser.close()

    @contextmanager
    def session(self):
        """Open ONE browser + page and reuse it for every operation inside the block.

        Prevents the submit/poll/download cycle from spawning a new browser per
        call. All sync methods reuse the sticky page while a session is active.
        """
        from playwright.sync_api import sync_playwright

        if self.profile_dir is not None:
            self._assert_enabled()
        else:
            self._assert_session()
        if self._sticky_page is not None:
            yield self._sticky_page
            return
        with sync_playwright() as playwright:
            chrome = self._resolve_chrome()
            if self.profile_dir is not None:
                self.profile_dir.mkdir(parents=True, exist_ok=True)
                launch_kwargs: dict[str, Any] = {"headless": self.headless}
                if chrome:
                    launch_kwargs["executable_path"] = chrome
                context = playwright.chromium.launch_persistent_context(
                    str(self.profile_dir),
                    viewport={"width": 1440, "height": 1100},
                    accept_downloads=True,
                    args=["--disable-blink-features=AutomationControlled", "--start-maximized"],
                    **launch_kwargs,
                )
                page = context.pages[0] if context.pages else context.new_page()
            else:
                launch_kwargs = {"headless": self.headless}
                if chrome:
                    launch_kwargs["executable_path"] = chrome
                browser = playwright.chromium.launch(**launch_kwargs)
                context = browser.new_context(
                    storage_state=str(self.storage_state_path),
                    viewport={"width": 1440, "height": 1100},
                    accept_downloads=True,
                )
                page = context.new_page()
            self._sticky_page = page
            self._sticky_context = context
            try:
                page.goto(GEN_URL, wait_until="domcontentloaded", timeout=120000)
                self._wait_for_generator(page)
                yield page
            finally:
                self._sticky_page = None
                self._sticky_context = None
                context.close()

    def _wait_for_generator(self, page, timeout: int = 180) -> None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                if page.locator("#user_input").count() > 0 and "Just a moment" not in page.title():
                    return
            except Exception:
                pass
            time.sleep(2)
        raise ProviderAuthError("Timed out waiting for the TAAFT generator page or Cloudflare challenge")

    def _api_json(self, page, path: str) -> dict[str, Any]:
        attempt = 0
        while True:
            try:
                result = page.evaluate(
                    """async (path) => {
                        const response = await fetch(path, {
                            credentials: 'include',
                            headers: {'X-Requested-With': 'XMLHttpRequest'}
                        });
                        return {status: response.status, text: await response.text()};
                    }""",
                    path,
                )
            except Exception:
                if attempt >= TRANSIENT_RETRY_ATTEMPTS:
                    raise
                attempt += 1
                time.sleep(TRANSIENT_BACKOFF_SECONDS * (2 ** (attempt - 1)))
                continue
            status = int(result.get("status") or 0)
            text = result.get("text") or ""
            try:
                data = json.loads(text)
            except Exception:
                data = {"raw": text}
            if status == 401:
                raise ProviderAuthError("TAAFT session expired; reconnect the account")
            if status in TRANSIENT_STATUS and attempt < TRANSIENT_RETRY_ATTEMPTS:
                attempt += 1
                time.sleep(TRANSIENT_BACKOFF_SECONDS * (2 ** (attempt - 1)))
                continue
            if status >= 400:
                raise GenerationError(f"TAAFT API {path} returned {status}")
            return data

    def _read_config(self, page) -> dict[str, Any]:
        return page.evaluate("window.VIDEOGEN_GENERATOR_CONFIG || {}")

    def _set_tier(self, page, tier: str) -> None:
        tier = tier if tier in {"fast", "quality"} else "fast"
        button = page.locator(f'.videogen_pill[data-videogen-tier="{tier}"]')
        if button.count() == 0:
            raise GenerationError(f"Tier button not found: {tier}")
        button.click()

    def _set_orientation(self, page, orientation: str) -> None:
        orientation = orientation if orientation in {"landscape", "portrait"} else "landscape"
        page.locator(f'input[name="videogen_orientation"][value="{orientation}"]').check()

    def _set_enhance(self, page, enabled: bool, extend: bool = False) -> None:
        selector = ".videogen_extend_enhance" if extend else "#videogen_enhance_prompt"
        locator = page.locator(selector)
        if locator.count() == 0:
            return
        if enabled:
            locator.check()
        else:
            locator.uncheck()

    def _set_reference(self, page, image_path: Path) -> None:
        page.locator("#videogen_image_input").set_input_files(str(image_path))
        deadline = time.time() + 30
        while time.time() < deadline:
            if page.locator(".videogen_image_chip").count() > 0:
                return
            time.sleep(0.5)
        raise GenerationError(f"Reference image did not attach: {image_path}")

    def _parse_generation_response(self, response) -> dict[str, Any]:
        status = int(response.status)
        text = response.text()
        try:
            data = json.loads(text)
        except Exception:
            data = {}
        if status == 401:
            raise ProviderAuthError("TAAFT session expired; reconnect the account")
        if status == 409 and data.get("active_generation_id"):
            return {"id": data["active_generation_id"], "status": "queued", "adopted": True}
        if status < 200 or status >= 300 or not data.get("generation"):
            raise GenerationError(f"TAAFT generation submission failed ({status})")
        return data["generation"]

    def _wait_for_extend_button(self, page, timeout: int = 180) -> None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                if page.locator("#videogen_extend_open").is_visible():
                    return
            except Exception:
                pass
            time.sleep(2)
        raise GenerationError("TAAFT extend button did not become available")

    def _load_generation(self, page, job_id: str) -> None:
        page.goto(GEN_URL, wait_until="domcontentloaded", timeout=90000)
        selector = f'button[data-videogen-generation-id="{job_id}"]'
        deadline = time.time() + 60
        item = page.locator(selector).first
        while time.time() < deadline and item.count() == 0:
            time.sleep(2)
        if item.count() == 0:
            item = page.locator(f'[data-videogen-generation-id="{job_id}"]').first
            while time.time() < deadline and item.count() == 0:
                time.sleep(2)
        if item.count() == 0:
            raise GenerationError(f"Could not find parent generation {job_id} in TAAFT history")
        item.click()
        self._wait_for_extend_button(page, timeout=120)

    def _wait_for_job(self, page, job_id: str) -> dict[str, Any]:
        deadline = time.time() + self.job_timeout
        url_deadline = None
        while time.time() < deadline:
            data = self._api_json(page, f"/api/video-generation/?id={job_id}")
            generation = data.get("generation")
            if not isinstance(generation, dict):
                raise GenerationError(f"TAAFT job {job_id} disappeared")
            status = str(generation.get("status") or "")
            if status in TERMINAL_FAIL:
                raise GenerationError("TAAFT generation failed")
            if status in TERMINAL_OK or generation.get("terminal"):
                if generation.get("video_url"):
                    return generation
                if url_deadline is None:
                    url_deadline = time.time() + 90
                if time.time() < url_deadline:
                    time.sleep(5)
                    continue
                raise GenerationError(f"TAAFT generation {job_id} finished without a video URL")
            time.sleep(self.poll_seconds)
        raise GenerationError(f"Timed out waiting for TAAFT job {job_id}")

    # ----- sync implementations (run in a worker thread) -----

    def _sync_verify(self) -> dict:
        with self._browser_page() as page:
            account = self._api_json(page, "/api/account/?obj_type=0&obj_id=0")
            if not account.get("id"):
                raise ProviderAuthError("TAAFT session is not authenticated")
            return {"provider": self.name, "account_id": account.get("id"), "status": "connected"}

    def _sync_usage(self) -> UsageInfo:
        with self._browser_page() as page:
            data = self._api_json(page, "/api/video-generation/?resume=1")
            quota = data.get("quota") or {}
            return UsageInfo(
                credits_remaining=quota.get("remaining"),
                credits_total=quota.get("total"),
                plan=quota.get("plan"),
                detail={"quota": quota},
            )

    def _sync_submit(self, prompt: str, tier: str, orientation: str, reference: Path | None) -> dict:
        with self._browser_page() as page:
            page.locator("#user_input").fill(prompt)
            if reference is not None:
                self._set_reference(page, reference)
            self._set_tier(page, tier)
            self._set_orientation(page, orientation)
            self._set_enhance(page, self.enhance, extend=False)
            with page.expect_response(
                lambda response: "/api/video-generation" in response.url
                and response.request.method == "POST",
                timeout=120000,
            ) as response_info:
                page.locator("#generate").click()
            return self._parse_generation_response(response_info.value)

    def _try_extend(self, parent_id: str, prompt: str) -> dict[str, Any]:
        with self._browser_page() as page:
            self._load_generation(page, parent_id)
            page.locator("#videogen_extend_open").click()
            textarea = page.locator(".videogen_extend_prompt")
            textarea.wait_for(state="visible", timeout=30000)
            textarea.fill(prompt)
            self._set_enhance(page, self.enhance, extend=True)
            with page.expect_response(
                lambda response: "/api/video-generation" in response.url
                and response.request.method == "POST",
                timeout=120000,
            ) as response_info:
                page.locator(".videogen_extend_submit").click()
            generation = self._parse_generation_response(response_info.value)
            generation["parent_id"] = generation.get("parent_id") or parent_id
            generation["mode"] = generation.get("mode") or "extend"
            return generation

    def _active_generation(self) -> dict[str, Any] | None:
        with self._browser_page() as page:
            data = self._api_json(page, "/api/video-generation/?resume=1")
            generation = data.get("generation")
            return generation if isinstance(generation, dict) else None

    REFERENCE_PREFIX = (
        "Use <Image 1> as the exact first frame of this shot. "
        "Continue seamlessly from that frame. Preserve the subject, environment, "
        "lighting direction, and color grade.\n\n"
    )

    def _sync_extend(
        self,
        parent_id: str,
        prompt: str,
        reference: Path | None,
        tier: str = "quality",
        orientation: str = "landscape",
    ) -> dict[str, Any]:
        try:
            return self._try_extend(parent_id, prompt)
        except Exception:
            pass
        active = self._active_generation()
        if active and active.get("id"):
            active["parent_id"] = active.get("parent_id") or parent_id
            active["mode"] = active.get("mode") or "extend_adopted"
            return active
        if reference is None or not reference.exists():
            raise GenerationError(
                f"TAAFT extend failed for parent {parent_id} and no reference frame is available"
            )
        return self._sync_submit(self.REFERENCE_PREFIX + prompt, tier, orientation, reference)

    def _sync_status(self, generation_id: str, wait: bool) -> dict:
        with self._browser_page() as page:
            if wait:
                return self._wait_for_job(page, generation_id)
            data = self._api_json(page, f"/api/video-generation/?id={generation_id}")
            generation = data.get("generation")
            if not isinstance(generation, dict):
                raise GenerationError(f"TAAFT job {generation_id} disappeared")
            return generation

    # ----- async provider interface -----

    async def verify_account(self) -> dict:
        return await asyncio.to_thread(self._sync_verify)

    async def get_usage(self) -> UsageInfo:
        return await asyncio.to_thread(self._sync_usage)

    async def submit_generation(
        self,
        *,
        prompt: str,
        tier: str,
        orientation: str,
        duration: float,
        reference_image_path: Path | None = None,
        idempotency_key: str | None = None,
    ) -> GenerationResult:
        self._assert_enabled()
        if idempotency_key:
            existing = await self.find_generation_by_idempotency(idempotency_key)
            if existing is not None:
                return existing
        raw = await asyncio.to_thread(self._sync_submit, prompt, tier, orientation, reference_image_path)
        return GenerationResult(
            generation_id=str(raw.get("id")),
            status=str(raw.get("status") or "queued"),
            video_url=raw.get("video_url"),
            mode=raw.get("mode"),
            parent_generation_id=raw.get("parent_id"),
            segment_index=raw.get("segment_index"),
            raw=raw,
        )

    async def get_generation_status(self, generation_id: str) -> GenerationResult:
        self._assert_enabled()
        raw = await asyncio.to_thread(self._sync_status, generation_id, False)
        return GenerationResult(
            generation_id=generation_id,
            status=str(raw.get("status") or "queued"),
            video_url=raw.get("video_url"),
            mode=raw.get("mode"),
            parent_generation_id=raw.get("parent_id"),
            segment_index=raw.get("segment_index"),
            error=str(raw.get("error")) if raw.get("error") else None,
            raw=raw,
        )

    async def wait_for_generation(self, generation_id: str) -> GenerationResult:
        self._assert_enabled()
        raw = await asyncio.to_thread(self._sync_status, generation_id, True)
        return GenerationResult(
            generation_id=generation_id,
            status=str(raw.get("status") or "succeeded"),
            video_url=raw.get("video_url"),
            mode=raw.get("mode"),
            parent_generation_id=raw.get("parent_id"),
            segment_index=raw.get("segment_index"),
            raw=raw,
        )

    async def extend_generation(
        self,
        *,
        parent_generation_id: str,
        prompt: str,
        tier: str,
        orientation: str,
        duration: float,
        reference_image_path: Path | None = None,
    ) -> GenerationResult:
        self._assert_enabled()
        tier_normalized = tier if tier in {"fast", "quality"} else self.tier
        orientation_normalized = orientation if orientation in {"landscape", "portrait"} else self.orientation
        raw = await asyncio.to_thread(
            self._sync_extend,
            parent_generation_id,
            prompt,
            reference_image_path,
            tier_normalized,
            orientation_normalized,
        )
        return GenerationResult(
            generation_id=str(raw.get("id")),
            status=str(raw.get("status") or "queued"),
            video_url=raw.get("video_url"),
            mode=raw.get("mode") or "extend",
            parent_generation_id=str(raw.get("parent_id") or parent_generation_id),
            segment_index=raw.get("segment_index"),
            raw=raw,
        )

    async def download_generation(self, generation: GenerationResult, destination: Path) -> Path:
        self._assert_enabled()
        if not generation.video_url:
            raise DownloadError("TAAFT generation has no video URL")
        destination.parent.mkdir(parents=True, exist_ok=True)
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140 Safari/537.36",
            "Referer": GEN_URL,
        }
        response = requests.get(generation.video_url, headers=headers, timeout=180)
        response.raise_for_status()
        destination.write_bytes(response.content)
        if destination.stat().st_size == 0:
            raise DownloadError("Downloaded empty TAAFT video")
        return destination

    async def cancel_generation(self, generation_id: str) -> bool:
        # No documented cancellation endpoint was verified in the original agent.
        return False

    async def find_generation_by_idempotency(self, idempotency_key: str) -> GenerationResult | None:
        """Best-effort reconciliation using TAAFT's resume endpoint.

        TAAFT does not expose a documented lookup by client key. The resume
        endpoint reports the currently active generation, which is the only
        safe way to adopt a submission whose response was lost.
        """
        self._assert_enabled()

        def _lookup() -> dict | None:
            with self._browser_page() as page:
                data = self._api_json(page, "/api/video-generation/?resume=1")
                generation = data.get("generation")
                return generation if isinstance(generation, dict) else None

        raw = await asyncio.to_thread(_lookup)
        if not raw or not raw.get("id"):
            return None
        return GenerationResult(
            generation_id=str(raw.get("id")),
            status=str(raw.get("status") or "queued"),
            video_url=raw.get("video_url"),
            mode=raw.get("mode"),
            parent_generation_id=raw.get("parent_id"),
            raw={"reconciled": True, **raw},
        )
