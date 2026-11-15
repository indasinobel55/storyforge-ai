from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent.providers.taaft import GEN_URL, TaaftProvider
from agent.scenes.spec import ScenePlan

SHOTS = Path("local_work/monsoon_probe_shots")
PLAN = Path("stories/child_of_the_monsoon/ep01/plan.json")
prompt = ScenePlan.model_validate_json(PLAN.read_text(encoding="utf-8")).scenes[0].prompt

provider = TaaftProvider(
    enabled=True,
    profile_dir=Path(".taaft_chrome_profile"),
    headless=False,
    poll_seconds=20,
    job_timeout_seconds=3600,
    tier="quality",
    orientation="landscape",
)

from playwright.sync_api import sync_playwright

chrome = provider._resolve_chrome()
print(f"chrome resolved: {chrome}", flush=True)
with sync_playwright() as pw:
    print("playwright started", flush=True)
    launch_kwargs = {"headless": False}
    if chrome:
        launch_kwargs["executable_path"] = chrome
    context = pw.chromium.launch_persistent_context(
        str(Path(".taaft_chrome_profile")),
        viewport={"width": 1440, "height": 1100},
        accept_downloads=True,
        args=["--disable-blink-features=AutomationControlled", "--start-maximized"],
        **launch_kwargs,
    )
    print("browser launched", flush=True)
    page = context.pages[0] if context.pages else context.new_page()
    page.goto(GEN_URL, wait_until="domcontentloaded", timeout=90000)
    provider._wait_for_generator(page)
    SHOTS.mkdir(parents=True, exist_ok=True)

    page.screenshot(path=str(SHOTS / "01_form_before.png"), full_page=True)

    provider._set_tier(page, "quality")
    provider._set_orientation(page, "landscape")
    page.locator("#user_input").fill(prompt)
    print(f"filled prompt: {len(prompt)} chars", flush=True)
    page.screenshot(path=str(SHOTS / "02_form_filled.png"), full_page=True)

    with page.expect_response(
        lambda response: "/api/video-generation" in response.url and response.request.method == "POST",
        timeout=120000,
    ) as response_info:
        page.locator("#generate").click()
    response = response_info.value
    print("STATUS:", response.status, flush=True)
    print("BODY:", response.text()[:2000], flush=True)

    page.wait_for_timeout(3000)
    page.screenshot(path=str(SHOTS / "03_form_after.png"), full_page=True)

    for selector in (".error", ".alert", "[class*=error]", "[class*=alert]", ".toast", "[role=alert]"):
        try:
            elements = page.locator(selector)
            for i in range(min(elements.count(), 5)):
                text = elements.nth(i).inner_text().strip()
                if text:
                    print(f"UI[{selector}]: {text[:300]}", flush=True)
        except Exception:
            continue
    context.close()
