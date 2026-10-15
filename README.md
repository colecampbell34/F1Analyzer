# F1 Analyzer — Race Intelligence

[![Python](https://img.shields.io/badge/Python-3.9+-blue.svg)](https://www.python.org/)
[![Dash](https://img.shields.io/badge/Dash-2.14+-008bb4.svg)](https://dash.plotly.com/)
[![FastF1](https://img.shields.io/badge/FastF1-3.3+-red.svg)](https://github.com/theOehrly/FastF1)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A technical Formula 1 analysis desk for comparing drivers through telemetry,
track position, race pace, and strategy. It is powered by FastF1 and can use
Google Gemini for data-grounded follow-up questions about the loaded session.

The interface is designed as an engineering workspace: restrained, dense where
it matters, and focused on explaining a performance delta rather than looking
like a generic dashboard.

## Key Features

- Latest Race shortcut that selects the most recent completed race and defaults to the top two drivers.
- Telemetry traces for speed, throttle, braking, gears, delta, smooth browser-side mini-map replay, and a live G-force monitor.
- Track maps for dominance, braking, and speed overlays.
- Compact tyre-stint plans, degradation, and strategy-call context alongside race gaps and representative grid pace.
- AI analysis with session-specific telemetry, weather, messages, and lap context.
- Bookmarkable URLs that preserve session, drivers, active tab, lap mode, lap numbers, and track-map mode.
- Feedback capture with optional admin review and CSV export.

## Bookmarks

The dashboard URL automatically retains the current analysis state, so a useful view can be bookmarked and returned to later. It includes:

- Year, race, session, drivers
- Active tab
- Specific lap modes and lap numbers
- Track map overlay mode

## Technical Stack

- Data: FastF1, Pandas, NumPy, SciPy
- UI: Dash, Plotly, Dash Bootstrap Components
- AI: Google Gemini via `google-genai`
- Runtime: Dash, Flask, Gunicorn, Flask-Compress
- Frontend runtime: Dash's React renderer with clientside JavaScript for high-frequency chart interactions

### Data-source decision

FastF1 remains the primary data layer because this app depends on telemetry,
lap timing, circuit geometry, weather, and race-control information. Jolpica
is a useful future supplement for lightweight historical results metadata, but
it cannot replace FastF1 for the product's core telemetry analysis.

## Project Structure

- `app.py` - Dash app setup, Flask server, health/warmup routes, runtime init.
- `runtime.py` - Central local versus serverless policy and writable runtime directories.
- `layout.py` - Sidebar, tabs, modals, stores, and page structure.
- `callbacks.py` - Core dropdowns, URL sync, latest-race defaults, summary/status callbacks.
- `callbacks_telemetry.py` - Telemetry chart, mini-map, G-force, and playback callbacks.
- `callbacks_tabs.py` - Track map, strategy, and combined Race & Pace callbacks.
- `callbacks_ai.py` - AI context loading, question handling, and history callbacks.
- `callbacks_feedback.py` - Feedback modal, inbox, and CSV callbacks.
- `data.py` - FastF1 loading, caching, preloading, pruning, and schedule helpers.
- `telemetry_prep.py` - Shared selected-lap telemetry preparation.
- `telemetry_dynamics.py` - Deterministic estimated-G helpers used by the Telemetry sidecar.
- `strategy_insights.py` - Deterministic stint and tyre-service summaries for Strategy and Race & Pace.
- `graph_shared.py` - Shared graph config, colors, error figures, and graph helpers.
- `graphs.py` - Feature-specific Plotly figure builders.
- `ai_utils.py` - Gemini prompt construction and session context building.
- `ai_cache.py` - AI response cache and per-user rate limiting.
- `ui_utils.py` - UI formatting helpers, summaries, leaderboard, and feedback rendering.
- `assets/race-intelligence.css` - Product visual system, loaded after base CSS.
- `docs/ARCHITECTURE.md` - Module boundaries, request flow, and storage model.
- `docs/DEPLOYMENT.md` - Vercel configuration and release smoke checks.
- `AGENTS.md` - Contributor rules, workflow, and guardrails for future agents.

## Local Setup

1. Use Python 3.12 (the deployment version).
2. Clone the repo: `git clone https://github.com/colecampbell34/F1Analyzer.git`
3. Install dependencies: `python -m pip install -r requirements.txt`
4. Create a `.env` file with your AI key if you want AI enabled.
5. Run the app: `python app.py`


## Environment Variables

- `GEMINI_API_KEY` - Enables AI Analysis.
- `FEEDBACK_ADMIN_TOKEN` - Enables the feedback inbox and CSV export for authorized admins.
- `CALLBACK_TIMING_THRESHOLD_MS` - Logs callbacks slower than this threshold. Default: `400`.
- `LOG_ALL_CALLBACKS=1` - Logs every timed callback.
- `LOG_SESSION_LOADING=1` - Logs session preload/load behavior.
- `FASTF1_CACHE_DIR` - Optional runtime cache directory. Defaults to `f1_cache/` locally and `/tmp/f1_cache` on Vercel.
- `OPENF1_FALLBACK_ENABLED` - Optional, defaults to `1`. OpenF1 is used only when FastF1 has valid session/lap data but an empty car-data stream; set `0` to disable this last-resort selected-lap fallback.
- `OPENF1_FALLBACK_TIMEOUT_SECONDS` - Optional per-request timeout for the OpenF1 fallback. Defaults to `8` seconds (range: 1–20).
- `AI_CACHE_DIR` - Optional AI response cache directory. Defaults to `ai_cache/` locally and `/tmp/ai_cache` on Vercel.
- `FEEDBACK_DIR` - Optional feedback storage directory. Defaults to `feedback/` locally and `/tmp/feedback` on Vercel.
- `PUBLIC_BASE_URL` - Optional production URL for Open Graph metadata.
- `ENABLE_VERCEL_ANALYTICS=1` - Opts into Vercel Web Analytics and Speed Insights scripts. They are disabled by default to keep the first frontend load lighter.
- `KV_REST_API_URL` / `KV_REST_API_TOKEN` - Optional shared Redis cache for prepared selected-lap traces on Vercel; these are the names provided by the Vercel Upstash integration. Direct Upstash connections may instead use `UPSTASH_REDIS_REST_URL` / `UPSTASH_REDIS_REST_TOKEN`. The aliases `F1_ANALYZER_REDIS_REST_URL` and `F1_ANALYZER_REDIS_REST_TOKEN` are also supported.
- `F1_ANALYZER_SHARED_CACHE_ENABLED=0` - Explicitly disables the shared cache, even when Redis credentials are configured.
- `SHARED_TELEMETRY_CURRENT_TTL_SECONDS` / `SHARED_TELEMETRY_HISTORICAL_TTL_SECONDS` - Optional cache TTLs. Defaults are 6 hours for the current season and 30 days for older seasons.
- `TELEMETRY_LAP_FALLBACK_ATTEMPTS` - Optional maximum alternate laps tried when Fastest has a recorded lap time but no usable trace. Defaults to `0` (try every valid lap); explicitly selected lap numbers are never substituted.

## Runtime Data

- `f1_cache/` stores FastF1 cache data and is pruned automatically.
- `ai_cache/responses.json` stores cached AI answers for repeated questions/context.
- `feedback/entries.jsonl` stores feedback submissions with hashed reporter IPs.

These directories are runtime artifacts and should not be committed. On Vercel,
they are ephemeral and instance-local. They reduce repeat work within a warm
function but are not durable storage or global cache/rate-limit state.

### Optional shared telemetry cache

Connect an Upstash Redis database from the Vercel Marketplace, which injects
`KV_REST_API_URL` and writable `KV_REST_API_TOKEN` into the project. The
app then shares compressed, validated two-driver lap traces between Vercel
instances. It never stores FastF1's raw filesystem cache, credentials, or
user data. Redis failures are non-fatal: the app falls back to FastF1 and its
in-process cache automatically. Cache diagnostics appear in the protected
`/api/perf` response.

## Testing

Run the current test suite with:

```bash
python -m unittest discover -s tests -q
```

For linting and optional browser smoke tests, install the development tools:

```bash
python -m pip install -r requirements-dev.txt
python -m ruff check .
RUN_BROWSER_SMOKE=1 F1_ANALYZER_BASE_URL=http://127.0.0.1:8000 python -m pytest tests/test_browser_smoke.py
```

## Deployment

Example Gunicorn command:

```bash
gunicorn app:server --bind 0.0.0.0:$PORT --timeout 300 --workers 1 --threads 4 --worker-class gthread
```

The app exposes:

- `/health` and `/healthz` for cheap liveness checks.
- `/warmup` to start background runtime initialization and schedule cache warming.

### Vercel

This repo deploys its root `app.py` Flask WSGI application on Vercel, plus
`vercel.json` and `.vercelignore` to keep the serverless bundle small. Do not
add a catch-all rewrite: Vercel's Flask integration preserves each Dash request
path, allowing CSS and component-suite JavaScript assets to be served correctly.
The project pins Python 3.12 with `.python-version`. Set `PUBLIC_BASE_URL` to your
production URL so Open Graph metadata points at the Vercel domain.

The FastF1 cache is runtime data and is intentionally excluded from deployment.
First loads on a cold function can still take time while FastF1 rebuilds cache
data. Vercel functions use direct, on-demand loads rather than background
preload threads; `/warmup` reports that behavior explicitly. Review
[`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) before deploying.

### Render (optional persistent-host alternative)

Vercel is a supported deployment target for this app. The included
[`vercel.json`](vercel.json) explicitly enables Fluid Compute and gives the
Python function a 300-second telemetry-load budget. The repository also
includes [`render.yaml`](render.yaml) for a free Render web service when you
prefer one long-lived Gunicorn process and its local FastF1 cache while the
service is awake. See [`docs/RENDER.md`](docs/RENDER.md) for its setup and
tradeoffs. Either host can use the same writable Upstash Redis variables:
`KV_REST_API_URL` and `KV_REST_API_TOKEN`.

---

*Note: This project is unofficial and not associated with Formula 1 or any of its teams. Data provided by FastF1.*
 
