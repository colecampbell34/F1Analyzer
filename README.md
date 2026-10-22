# F1 Analyzer — Race Intelligence

[![Python](https://img.shields.io/badge/Python-3.12-blue.svg)](https://www.python.org/)
[![Dash](https://img.shields.io/badge/Dash-3.x-008bb4.svg)](https://dash.plotly.com/)
[![OpenF1](https://img.shields.io/badge/data-OpenF1-red.svg)](https://openf1.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A technical Formula 1 analysis desk for comparing drivers through lap timing,
telemetry, track position, race pace, and strategy. Google Gemini can answer
follow-up questions using the selected session's published data.

The interface is designed as an engineering workspace: restrained, dense where
it matters, and focused on explaining a performance delta.

## Coverage and data limits

- The app supports completed sessions from 2023 onward. A session is eligible
  once its published end time is at least 30 minutes in the past and it is not
  marked canceled. Live timing is not supported.
- OpenF1 is the primary source for sessions, drivers, laps, selected-lap car
  and location traces, results, starting grid, stints, pits, weather, and race
  control. Jolpica-F1 can supplement missing classification data; the
  interface retains source labels so supplements are not presented as OpenF1
  values.
- Selected-lap car and location streams are sampled at about 3.7 Hz. The map
  uses approximate, session-relative coordinates, and integrated distance is a
  progress estimate rather than official circuit distance. Speed and other
  car-only analysis can work without location data; track maps and replay
  require sufficient aligned location samples.
- OpenF1 does not publish FastF1-equivalent deleted-lap accuracy or exact
  per-lap track status. Pit and race-control records support useful exclusions
  and derived status overlays, but cannot guarantee exact parity with FastF1.
- Pit-lane duration and stationary tyre-service duration are different
  measurements. The dashboard keeps them distinct and does not infer service
  time from pit-lane time.
- OpenF1 documents historical access from 2023 onward and publishes limits of
  3 requests per second and 30 per minute. Its public API is intended for
  educational, research, and non-commercial fan engagement. Review the
  [OpenF1 terms and API documentation](https://openf1.org/docs/) before
  commercial use.

## Key features

- Latest Race shortcut and historical year, event, session, and driver pickers.
- Speed, throttle, brake, gear, RPM, DRS, and lap-delta comparison with
  browser-side replay controls.
- Track-map dominance, braking, and speed overlays; corner markers are
  heuristic because third-party circuit geometry is not yet verified against
  OpenF1's session-relative coordinates.
- Tyre-stint plans, estimated degradation, weather, race gaps, grid-to-finish
  context, and field pace distribution when the relevant provider data is
  available.
- Grounded AI analysis with session, selected-lap, strategy, weather, and
  race-control context when those feeds are available and `GEMINI_API_KEY` is
  configured.
- Bookmarkable URLs, feedback capture, chart downloads, and responsive
  desktop/mobile layouts.

## Architecture

- `app.py` owns Flask/Dash routes, HTTP cache headers, and startup policy.
- `layout.py` owns components and stable IDs; callbacks treat those IDs as a
  public contract.
- `callbacks.py`, `callbacks_telemetry.py`, `callbacks_tabs.py`, and
  `callbacks_ai.py` orchestrate selection and views.
- `session_data.py` is the validated OpenF1/Jolpica HTTP and normalized-data
  boundary. `data.py` provides callback-facing session, cache, and preload
  helpers.
- `telemetry_prep.py`, `graphs_*.py`, `graph_shared.py`, and
  `strategy_insights.py` transform normalized frames into deterministic
  figures and summaries.
- `runtime.py` owns local versus serverless storage policy.
- `assets/race-intelligence.css` owns the visual system; `assets/scripts.js`
  contains browser-side replay and high-frequency interactions.

See [architecture](docs/ARCHITECTURE.md), [deployment](docs/DEPLOYMENT.md),
[Render deployment](docs/RENDER.md), and the completed
[OpenF1 migration record](docs/OPENF1_MIGRATION_PLAN.md).

## Local setup

Use Python 3.12 for deployment parity. The app listens on port 8000 when run
directly:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python app.py
```

Optional environment variables (set secrets in the host environment; do not
commit `.env`):

- `GEMINI_API_KEY` enables AI analysis.
- `FEEDBACK_ADMIN_TOKEN` protects feedback review and performance endpoints.
- `PUBLIC_BASE_URL` sets the Open Graph canonical URL.
- `AI_CACHE_DIR` and `FEEDBACK_DIR` override local runtime file directories.
- `ENABLE_BACKGROUND_PRELOAD` controls background session loads; it defaults
  off on Vercel and on for persistent, non-serverless processes.
- `KV_REST_API_URL` / `KV_REST_API_TOKEN`,
  `UPSTASH_REDIS_REST_URL` / `UPSTASH_REDIS_REST_TOKEN`, or
  `F1_ANALYZER_REDIS_REST_URL` / `F1_ANALYZER_REDIS_REST_TOKEN` enable the
  optional Upstash shared cache for prepared selected-lap comparisons.
  `F1_ANALYZER_SHARED_CACHE_ENABLED=0` disables it, and
  `F1_ANALYZER_REDIS_TIMEOUT_SECONDS` adjusts its request timeout.
- `OPENF1_TELEMETRY_CURRENT_TTL_SECONDS` and
  `OPENF1_TELEMETRY_HISTORICAL_TTL_SECONDS` set prepared-telemetry cache TTLs;
  defaults are 6 hours and 30 days. `OPENF1_TELEMETRY_MAX_POINTS` caps
  serialized trace points (default 3,600). `TELEMETRY_PREP_CACHE_MAXSIZE`
  sets the process-local prepared-comparison cache size (default 8).
- `OPENF1_TELEMETRY_LOCK_WAIT_SECONDS` sets how long a request waits for
  another instance to populate a shared-cache miss (default 18 seconds).
- `CALLBACK_TIMING_THRESHOLD_MS` sets the slow-callback logging threshold
  (default 400 ms); `LOG_ALL_CALLBACKS=1` logs every callback.
- `ENABLE_VERCEL_ANALYTICS=1` adds Vercel Analytics scripts to the page.

Provider responses are cached in bounded process memory (up to 512 entries and
64 MB); historical session-key data is retained for up to 30 days, while an
empty result/grid response is retried after 5 minutes. Normalized session
bundles have a separate process-local LRU cache. Prepared selected-lap
comparisons have a bounded local cache and can optionally be shared through
Upstash; Upstash does not store raw session-wide telemetry. OpenF1 requests are
paced and capped at 25 per minute per process. That limiter is not global
across Vercel instances. Process memory and local runtime files are ephemeral
on Vercel and are not durable storage on Render Free; use managed storage for
durable data or globally coordinated rate limiting.

## Tests and checks

```bash
python -m unittest discover -s tests -q
python -m ruff check .
```

The opt-in Playwright browser smoke test needs a running app and live OpenF1
availability:

```bash
RUN_BROWSER_SMOKE=1 F1_ANALYZER_BASE_URL=http://127.0.0.1:8000 \
  python -m pytest tests/test_browser_smoke.py
```

## Hosting

Both Vercel and Render are supported. For regularly used public traffic, a
single persistent Render web service is the recommended profile: its single
Gunicorn worker shares one process-local OpenF1 cache and request limiter
across its threads, and can run background preloads. Render Free sleeps after
inactivity and has ephemeral local files. Vercel is suitable for
serverless-first hosting; its function-local caches and limiter are ephemeral
and do not coordinate across instances.

The root Flask WSGI app remains configured for Vercel with native path
routing, Fluid Compute, and a 300-second function budget. Do not add a
catch-all rewrite because it can return dashboard HTML for Dash asset paths.
For Render, `render.yaml` keeps one threaded Gunicorn worker and checks
`/healthz`. See [Vercel deployment](docs/DEPLOYMENT.md) and
[Render deployment](docs/RENDER.md).

---

*Unofficial project, not associated with Formula 1 or its teams. Historical
timing data is provided by OpenF1; optional classification supplements may be
provided by Jolpica-F1.*
