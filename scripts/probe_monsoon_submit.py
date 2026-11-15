from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent.providers.taaft import GEN_URL, TaaftProvider
from agent.scenes.spec import ScenePlan

PLAN = Path("stories/child_of_the_monsoon/ep01/plan.json")
prompt = ScenePlan.model_validate_json(PLAN.read_text(encoding="utf-8")).scenes[0].prompt
print(f"scene 1 prompt length: {len(prompt)} chars")

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

with sync_playwright() as pw:
    context = pw.chromium.launch_persistent_context(
        str(Path(".taaft_chrome_profile")),
        viewport={"width": 1440, "height": 1100},
        accept_downloads=True,
        args=["--disable-blink-features=AutomationControlled", "--start-maximized"],
    )
    page = context.pages[0] if context.pages else context.new_page()
    page.goto(GEN_URL, wait_until="domcontentloaded", timeout=90000)
    provider._wait_for_generator(page)
    config = page.evaluate("window.VIDEOGEN_GENERATOR_CONFIG || {}")
    print("config keys:", list(config.keys()))
    limits = {
        k: config.get(k)
        for k in config
        if any(word in str(k).lower() for word in ("max", "length", "limit", "prompt"))
    }
    print("limit-related config:", limits)
    provider._set_tier(page, "quality")
    provider._set_orientation(page, "landscape")
    page.locator("#user_input").fill(prompt)
    with page.expect_response(
        lambda response: "/api/video-generation" in response.url and response.request.method == "POST",
        timeout=120000,
    ) as response_info:
        page.locator("#generate").click()
    response = response_info.value
    print("STATUS:", response.status)
    print("BODY:", response.text()[:1500])
    context.close()
