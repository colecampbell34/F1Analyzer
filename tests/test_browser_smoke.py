"""Optional browser smoke test for the main dashboard flow.

Run manually against a local server:

    RUN_BROWSER_SMOKE=1 F1_ANALYZER_BASE_URL=http://127.0.0.1:8000 python3 -m pytest tests/test_browser_smoke.py

The test is skipped during normal unit-test runs because it needs Playwright,
a running Dash app, and live OpenF1 historical data availability.
"""
import os
from urllib.parse import urlencode

import pytest


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_BROWSER_SMOKE") != "1",
    reason="Browser smoke test is opt-in; set RUN_BROWSER_SMOKE=1.",
)


@pytest.mark.parametrize(
    ("viewport", "mobile"),
    [
        ({"width": 1440, "height": 1000}, False),
        ({"width": 390, "height": 844}, True),
    ],
    ids=("desktop", "mobile"),
)
def test_url_restore_numbered_laps_replay_feedback_download_and_views(viewport, mobile):
    sync_api = pytest.importorskip("playwright.sync_api")

    base_url = os.getenv("F1_ANALYZER_BASE_URL", "http://127.0.0.1:8000")
    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport=viewport, is_mobile=mobile, has_touch=mobile)
        try:
            query = urlencode({
                "year": 2023,
                "race": "Monaco Grand Prix",
                "session": "Race",
                "driver1": "VER",
                "driver2": "ALO",
                "tab": "tab-telemetry",
            })
            page.goto(f"{base_url.rstrip('/')}?{query}", wait_until="domcontentloaded")
            dismiss_phone_notice = page.locator("#phone-disclaimer-dismiss-btn")
            if mobile:
                dismiss_phone_notice.wait_for(state="visible", timeout=20_000)
                dismiss_phone_notice.click()
            speed_plot = page.locator("#speed-graph .js-plotly-plot")
            speed_plot.wait_for(timeout=180_000)
            page.wait_for_function(
                "() => (document.querySelector('#speed-graph .js-plotly-plot')?.data?.length || 0) > 0",
                timeout=180_000,
            )

            # Selection is serialized so a copied/reloaded analysis keeps the
            # chosen session, drivers, view and numbered laps.
            page.wait_for_function(
                "() => new URL(window.location.href).searchParams.has('year') && "
                "new URL(window.location.href).searchParams.has('session')",
                timeout=30_000,
            )
            saved_url = page.url
            page.goto(saved_url, wait_until="domcontentloaded")
            if mobile and dismiss_phone_notice.is_visible():
                dismiss_phone_notice.click()
            speed_plot.wait_for(timeout=180_000)
            page.wait_for_function(
                "() => (document.querySelector('#speed-graph .js-plotly-plot')?.data?.length || 0) > 0",
                timeout=180_000,
            )

            if not mobile:
                page.locator("#d1-lap-dropdown").click()
                page.get_by_role("option", name="Lap 2", exact=True).click()
                page.locator("#d2-lap-dropdown").click()
                page.get_by_role("option", name="Lap 2", exact=True).click()

            for control in ("#play-lap-btn", "#pause-resume-lap-btn"):
                page.locator(control).wait_for(state="visible", timeout=30_000)
            play = page.locator("#play-lap-btn")
            if play.is_enabled():
                play.click()
                page.locator("#pause-resume-lap-btn").click()
                focus = page.locator("#replay-focus-btn")
                if focus.is_visible():
                    focus.click()

            page.locator("#download-active-chart-btn").wait_for(state="visible")
            page.locator("#download-active-chart-btn").click()
            page.wait_for_function(
                "() => document.querySelector('#export-status')?.textContent.includes('Chart download started')",
                timeout=30_000,
            )

            feedback_button = page.locator("#mobile-open-feedback-modal-btn") if mobile else page.locator("#open-feedback-modal-btn")
            feedback_button.click()
            page.locator("#feedback-modal").wait_for(state="visible", timeout=10_000)
            page.locator("#cancel-feedback-btn").click()

            page.locator("#main-tabs").click()
            page.get_by_role("option", name="Track map", exact=True).click()
            page.locator("#trackmap-lap-summary", has_text="Lap").wait_for(timeout=30_000)
            map_plot = page.locator('[id="2d-dominance-graph"] .js-plotly-plot')
            map_plot.wait_for(timeout=180_000)

            if not mobile:
                page.get_by_label("Braking").check()
                map_plot.wait_for(timeout=180_000)
                page.get_by_label("Speed").check()
                map_plot.wait_for(timeout=180_000)

            page.locator("#main-tabs").click()
            page.get_by_role("option", name="Race & pace", exact=True).click()
            page.locator("#race-gaps-graph .js-plotly-plot").wait_for(timeout=180_000)
            page.wait_for_function(
                "() => (document.querySelector('#race-gaps-graph .js-plotly-plot')?.data?.length || 0) > 0",
                timeout=180_000,
            )
        finally:
            browser.close()
