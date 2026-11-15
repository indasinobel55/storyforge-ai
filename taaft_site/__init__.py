"""Minimal TAAFT-only web service.

A deliberately lean, fully online alternative to the all-in-one platform:
FastAPI + a single static page + Playwright Chromium driving TAAFT directly.
No Node, no database, no background worker process - everything runs in one
uvicorn process so the free 512MB Render container can afford a browser.
"""
