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

- Completed 2023 onward sessions are available after OpenF1 marks them
  historical. Live timing is not supported.
- OpenF1 is the primary source for sessions, drivers, laps, selected-lap car
  and location traces, results, grid, stints, pits, weather, and race control.
  Jolpica-F1 can supplement missing results; the interface retains source
  labels for those values.
- Selected-lap car and location streams are sampled at about 3.7 Hz. The map
  uses approximate relative coordinates, and integrated distance is a progress
  estimate rather than official circuit distance. Replay and map views require
  sufficient location samples.
- OpenF1 does not publish FastF1-equivalent deleted-lap accuracy or exact
  per-lap track status. Pit and race-control data support useful exclusions and
  status overlays, but those are documented approximations.
- Pit-lane total time is not stationary tyre-service time. The dashboard keeps
  those measurements distinct.
- OpenF1 describes its free historical API as intended for educational,
  research, and non-commercial fan use. Review the [OpenF1 terms and API
  documentation](https://openf1.org/docs/) before commercial use.

## Key features

- Latest Race shortcut and historical year, event, session, and driver pickers.
- Speed, throttle, brake, gear, RPM, DRS, and lap-delta comparison with
  browser-side replay controls.
- Track-map dominance, braking, and speed overlays with heuristic corner
  markers when circuit geometry is not aligned.
- Tyre-stint plans, estimated degradation, weather, race gaps, grid-to-finish
  context, and field pace distribution.
- Grounded AI analysis with session, selected-lap, strategy, weather, and
  race-control context when those feeds are available.
- Bookmarkable URLs, feedback capture, chart downloads, and responsive layout.

## Architecture

- `app.py` owns Flask/Dash routes, response caching, and startup policy.
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

See [architecture](docs/ARCHITECTURE.md), [deployment](docs/DEPLOYMENT.md), and
the completed [migration record](docs/OPENF1_MIGRATION_PLAN.md).

## Local setup

Use Python 3.12 for deployment parity:

```bash
python -m pip install -r requirements-dev.txt
python app.py
```

Optional environment variables:

- `GEMINI_API_KEY` enables AI analysis.
- `FEEDBACK_ADMIN_TOKEN` protects feedback review endpoints.
- `PUBLIC_BASE_URL` sets the Open Graph canonical URL.
- `CALLBACK_TIMING_THRESHOLD_MS` and `LOG_ALL_CALLBACKS=1` control callback
  timing logs.
- `LOG_SESSION_LOADING=1` enables provider load logs.
- `AI_CACHE_DIR` and `FEEDBACK_DIR` override local runtime directories.
- `ENABLE_BACKGROUND_PRELOAD` controls persistent-process background loads;
  it defaults off on Vercel and on for other hosts.
- `KV_REST_API_URL` / `KV_REST_API_TOKEN` or
  `UPSTASH_REDIS_REST_URL` / `UPSTASH_REDIS_REST_TOKEN` enable the optional
  shared cache for bounded selected-lap traces.
- `F1_ANALYZER_SHARED_CACHE_ENABLED=0` disables that cache. Cache TTL and
  selected-lap trace size can be tuned with the `SHARED_TELEMETRY_*` and
  `OPENF1_TELEMETRY_*` variables.

The provider caches historical JSON responses in-process and spaces OpenF1
requests below its published free-tier limit. A process-local limiter does not
coordinate separate Vercel instances; Redis shares derived traces, not API
rate-limit state. Runtime files, feedback, AI responses, and memory caches are
not durable storage.

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

Both Vercel and Render remain supported. For a regularly used public instance,
the current provider architecture favors a single persistent Render web
service: it keeps one process-local OpenF1 cache and request limiter, and can
use background preloading. Render Free is suitable for a low-traffic demo but
sleeps and loses local state on restart. Vercel remains a good fit for
serverless-first hosting or an infrequently used demo; its function-local
caches and rate limiter are ephemeral and do not coordinate across instances.

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
