from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent.providers.taaft import GEN_URL, LOGIN_URL, TaaftProvider


def main() -> None:
    provider = TaaftProvider(
        enabled=True,
        profile_dir=Path(".taaft_chrome_profile"),
        headless=False,
        tier="fast",
    )
    chrome = provider._resolve_chrome()
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        kwargs = {"headless": False}
        if chrome:
            kwargs["executable_path"] = chrome
        context = playwright.chromium.launch_persistent_context(
            str(Path(".taaft_chrome_profile").resolve()),
            viewport={"width": 1440, "height": 1100},
            accept_downloads=True,
            args=["--disable-blink-features=AutomationControlled", "--start-maximized"],
            **kwargs,
        )
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=90000)
        print("Log in to TAAFT in the opened Chrome window...")
        deadline = time.time() + 600
        authed = False
        while time.time() < deadline:
            time.sleep(4)
            try:
                account = provider._api_json(page, "/api/account/?obj_type=0&obj_id=0")
                if account.get("id"):
                    print("Logged in! account_id:", account.get("id"))
                    authed = True
                    break
            except Exception:
                pass
        if authed:
            page.goto(GEN_URL, wait_until="domcontentloaded", timeout=90000)
            print("Session saved to .taaft_chrome_profile - you can close the window now.")
            time.sleep(3)
        else:
            print("Timed out waiting for login (10 min). Run this script again.")
        context.close()


if __name__ == "__main__":
    main()
