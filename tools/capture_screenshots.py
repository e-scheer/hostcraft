"""One-shot screenshot capture for the README.

Runs against a live dev panel (Vue dev server + Django backend), authenticates
once via the JWT login endpoint, then visits each highlighted route and saves a
PNG to ``docs/screenshots/``.

Usage (run from the repo root, with ``docker compose -f docker-compose.dev.yml
up`` already running):

    docker run --rm --network=host \
        -v "$PWD/tools:/tools:ro" \
        -v "$PWD/docs/screenshots:/out" \
        mcr.microsoft.com/playwright/python:v1.49.0-noble \
        python /tools/capture_screenshots.py

The script is idempotent — re-running overwrites the PNGs.
"""

from __future__ import annotations

import json
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

FRONTEND_URL = "http://localhost:5173"
BACKEND_LOGIN = "http://localhost:5173/api/auth/login/"  # via Vite proxy
USERNAME = "admin"
PASSWORD = "admin"

OUT_DIR = Path("/out")

VIEWPORT = {"width": 1440, "height": 900}

# (slug, route, post-nav prep). Each entry yields docs/screenshots/<slug>.png.
SHOTS: list[tuple[str, str, str | None]] = [
    ("dashboard", "/",         None),
    ("console",   "/console",  None),
    ("mods",      "/mods",     "type:create"),  # type 'create' in search input
    ("runtime",   "/runtime",  None),
    ("network",   "/network",  None),
    # worldmap embeds a BlueMap iframe served on :8100; needs a long beat
    # for the WebGL tiles to download + render before the screenshot.
    ("worldmap",  "/worldmap", "wait:10000"),
]


def get_tokens() -> dict[str, str]:
    req = urllib.request.Request(
        BACKEND_LOGIN,
        data=json.dumps({"username": USERNAME, "password": PASSWORD}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode())


def prep_search(page: Page, query: str) -> None:
    """Type into the marketplace search input so the captured shot has cards
    on screen instead of the empty-state placeholder."""
    # The Browse tab has a single search input — first text input on the page.
    page.get_by_placeholder(_first_search_placeholder(page)).fill(query)
    page.wait_for_timeout(1500)  # debounce + first Modrinth request


def _first_search_placeholder(page: Page) -> str:
    """Best-effort: grab the actual placeholder string from the DOM so we
    don't hardcode the FR/EN copy. Falls back to a sensible default."""
    el = page.locator("input[placeholder]").first
    try:
        return el.get_attribute("placeholder") or "Search"
    except Exception:
        return "Search"


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print("[1/3] authenticating...")
    tokens = get_tokens()
    print(f"      got access token ({len(tokens['access'])} chars)")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(args=[
            "--no-sandbox",
            "--use-gl=swiftshader",         # software WebGL — BlueMap canvas needs it
            "--enable-webgl",
            "--ignore-gpu-blocklist",
        ])
        context = browser.new_context(viewport=VIEWPORT, device_scale_factor=1)

        # Inject the JWT pair before any page script runs — the auth store
        # reads from localStorage on init, so the SPA boots authenticated.
        context.add_init_script(
            f"""
            window.localStorage.setItem('hostcraft.token', {json.dumps(tokens["access"])});
            window.localStorage.setItem('hostcraft.refresh', {json.dumps(tokens["refresh"])});
            window.localStorage.setItem('hostcraft.theme', 'dark');
            """,
        )

        page = context.new_page()
        # Warm the cache once.
        page.goto(FRONTEND_URL, wait_until="domcontentloaded")
        page.wait_for_timeout(1000)

        print(f"[2/3] capturing {len(SHOTS)} routes...")
        for slug, route, prep in SHOTS:
            url = FRONTEND_URL + route
            print(f"      - {slug:10s} {url}")
            page.goto(url, wait_until="networkidle", timeout=30_000)

            # Some routes need a beat for animations / chart paints.
            page.wait_for_timeout(2000)

            if prep and prep.startswith("type:"):
                try:
                    prep_search(page, prep[len("type:"):])
                except Exception as e:  # noqa: BLE001
                    print(f"        warn: prep failed ({e}); capturing raw view")
            elif prep and prep.startswith("wait:"):
                page.wait_for_timeout(int(prep[len("wait:"):]))

            out = OUT_DIR / f"{slug}.png"
            page.screenshot(path=str(out), full_page=False)
            size_kb = out.stat().st_size // 1024
            print(f"        wrote {out.name} ({size_kb} KB)")

        browser.close()

    print(f"[3/3] done — {len(SHOTS)} PNGs in {OUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
