"""Probe whether TAAFT/Cloudflare is passable from a datacenter IP.

Modes (env PROBE_MODE, default "fresh"):
  fresh    - headed chromium, NO cookies.
  filtered - fetch the site's storage_state, strip Cloudflare cookies
             (cf_* are bound to the originating IP), keep site auth
             cookies, then load the generator page.
Env when filtered: SITE_URL, SITE_TOKEN.

Reports: page title evolution, generator presence, login form availability,
and saves screenshots + a storage_state for inspection.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import requests
from playwright.sync_api import sync_playwright

GEN_URL = "https://theresanaiforthat.com/@taaft/video-generator/?ref=header"
LOGIN_URL = "https://theresanaiforthat.com/login/"

OUT = Path("probe_out")


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def filtered_session(dest: Path) -> bool:
    site = os.environ["SITE_URL"].rstrip("/")
    token = os.environ["SITE_TOKEN"]
    r = requests.get(f"{site}/api/session/file", headers={"X-Site-Token": token}, timeout=120)
    if r.status_code != 200:
        log(f"no session on site: HTTP {r.status_code}")
        return False
    state = r.json()
    cookies = state.get("cookies", [])
    kept = [c for c in cookies if not c.get("name", "").lower().startswith("cf")]
    log(f"session cookies: {len(cookies)} total, {len(cookies) - len(kept)} cf_* stripped, {len(kept)} kept")
    state["cookies"] = kept
    dest.write_text(json.dumps(state), encoding="utf-8")
    return bool(kept)


def main() -> None:
    OUT.mkdir(exist_ok=True)
    mode = os.environ.get("PROBE_MODE", "fresh").strip().lower()
    log(f"probe mode: {mode}")

    session_file: Path | None = None
    if mode == "filtered":
        session_file = OUT / "filtered_state.json"
        if not filtered_session(session_file):
            log("filtered mode needs a session on the site; aborting")
            return

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-first-run",
                "--no-default-browser-check",
                "--start-maximized",
            ],
        )
        context = browser.new_context(viewport={"width": 1440, "height": 1100})
        if session_file is not None:
            context = browser.new_context(
                storage_state=str(session_file), viewport={"width": 1440, "height": 1100}
            )
        page = context.new_page()

        log("navigating GEN_URL (no cookies) ...")
        page.goto(GEN_URL, wait_until="domcontentloaded", timeout=90000)

        deadline = time.time() + 150
        seen: set[str] = set()
        reached = False
        while time.time() < deadline:
            try:
                title = page.title()
            except Exception as exc:  # noqa: BLE001
                title = f"<err {exc}>"
            try:
                has_input = page.locator("#user_input").count() > 0
            except Exception:
                has_input = False
            marker = f"title={title!r} user_input={has_input}"
            if marker not in seen:
                seen.add(marker)
                log(marker)
            if has_input and "Just a moment" not in title:
                reached = True
                break
            time.sleep(3)

        log(f"reached_generator={reached}")
        page.screenshot(path=str(OUT / "gen_result.png"))
        if reached:
            try:
                body = page.inner_text("body")[:300].replace("\n", " | ")
                log(f"body_start: {body}")
            except Exception as exc:  # noqa: BLE001
                log(f"body err: {exc}")
            context.storage_state(path=str(OUT / "probe_state.json"))
            log("probe storage_state saved")

        try:
            page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=60000)
            time.sleep(6)
            log(f"login title: {page.title()!r}")
            page.screenshot(path=str(OUT / "login.png"))
            for sel in (
                "input[type=email]",
                "input[type=password]",
                "#user_email",
                "#user_password",
                "iframe[src*='challenges']",
                "iframe[src*='turnstile']",
            ):
                log(f"login {sel}: {page.locator(sel).count()}")
        except Exception as exc:  # noqa: BLE001
            log(f"login probe err: {exc}")

        browser.close()
    log("PROBE DONE")


if __name__ == "__main__":
    main()
