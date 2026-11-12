"""Interactive TAAFT session bootstrap.

Opens a headed, persistent Chrome window on the TAAFT generator, lets you
complete the login (including Google/Facebook or Cloudflare challenges) in the
visible browser, then verifies the account and prints the remaining quota.

The profile directory keeps the session, so subsequent automated runs never
need a login again.
"""

from __future__ import annotations

import time
from pathlib import Path

from agent.providers.taaft import GEN_URL, LOGIN_URL, TaaftProvider


def run_login(
    *,
    profile_dir: Path | None,
    chrome_path: str | None = None,
    headless: bool = False,
    wait_seconds: int = 900,
    log=None,
) -> dict:
    log = log or (lambda message: print(message, flush=True))
    provider = TaaftProvider(
        enabled=True,
        profile_dir=profile_dir or Path.cwd() / ".taaft_chrome_profile",
        chrome_path=chrome_path,
        headless=headless,
    )
    with provider._browser_page() as page:
        account = provider._api_json(page, "/api/account/?obj_type=0&obj_id=0")
        if not account.get("id"):
            log("Not logged in. Opening the TAAFT login page - finish sign-in in the browser window.")
            page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=90000)
            deadline = time.time() + wait_seconds
            account = None
            while time.time() < deadline:
                try:
                    account = provider._api_json(page, "/api/account/?obj_type=0&obj_id=0")
                    if account.get("id"):
                        break
                except Exception:
                    pass
                time.sleep(3)
            if not account or not account.get("id"):
                raise RuntimeError("Timed out waiting for the manual TAAFT login")
            page.goto(GEN_URL, wait_until="domcontentloaded", timeout=90000)
            log(f"Login detected for account id {account.get('id')}")
        else:
            log(f"Existing session is active for account id {account.get('id')}")
        try:
            quota = provider._api_json(page, "/api/video-generation/?resume=1").get("quota") or {}
        except Exception:
            quota = {}
        log(f"Quota: {quota}")
        return {"provider": "taaft", "account_id": account.get("id"), "quota": quota, "status": "connected"}
