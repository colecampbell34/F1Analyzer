"""Optional browser smoke test for the main dashboard flow.

Run manually against a local server:

    RUN_BROWSER_SMOKE=1 F1_ANALYZER_BASE_URL=http://127.0.0.1:8000 python3 -m pytest tests/test_browser_smoke.py

The test is skipped during normal unit-test runs because it needs Playwright,
a running Dash app, and enough FastF1 cache/network availability to load a
session.
"""
import os

import pytest


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_BROWSER_SMOKE") != "1",
    reason="Browser smoke test is opt-in; set RUN_BROWSER_SMOKE=1.",
)


def test_select_session_numbered_laps_and_trackmap_updates():
    sync_api = pytest.importorskip("playwright.sync_api")

    base_url = os.getenv("F1_ANALYZER_BASE_URL", "http://127.0.0.1:8000")
    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        try:
            page.goto(base_url, wait_until="networkidle")
            page.get_by_role("button", name="Latest Race").click()
            page.get_by_role("button", name="Update Dashboard").click()
            page.locator("#speed-graph .js-plotly-plot").wait_for(timeout=180_000)

            page.locator("#d1-lap-dropdown .Select-control").click()
            page.locator(".Select-option", has_text="Lap ").nth(1).click()
            page.locator("#d2-lap-dropdown .Select-control").click()
            page.locator(".Select-option", has_text="Lap ").nth(1).click()

            page.get_by_text("Track Map", exact=True).click()
            page.locator("#trackmap-lap-summary", has_text="Lap").wait_for(timeout=30_000)
            page.locator("#2d-dominance-graph .js-plotly-plot").wait_for(timeout=180_000)

            page.get_by_label("Braking").check()
            page.locator("#2d-dominance-graph .js-plotly-plot").wait_for(timeout=180_000)
            page.get_by_label("Speed").check()
            page.locator("#2d-dominance-graph .js-plotly-plot").wait_for(timeout=180_000)
        finally:
            browser.close()
