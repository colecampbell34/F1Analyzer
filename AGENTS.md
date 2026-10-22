# F1 Analyzer contributor guide

## Product intent

F1 Analyzer is a technical comparison desk for Formula 1 sessions. The core
workflow is selecting a historical session, choosing two drivers, and
explaining performance through timing, telemetry, track position, race pace,
strategy, and optional AI analysis. Keep it fast and trustworthy. The interface
should feel like a motorsport engineering tool, not a game or generic admin
dashboard.

## Architecture map

- `app.py` owns Flask/Dash, HTTP routes, response caching, and startup policy.
- `layout.py` owns Dash components and stable IDs. Treat IDs as a public
  contract; update every dependent callback and browser test when changing one.
- `callbacks.py` owns selection, URL state, loading state, and common UI.
  Tab-specific callback registration lives in `callbacks_telemetry.py`,
  `callbacks_tabs.py`, `callbacks_ai.py`, and `callbacks_feedback.py`.
- `session_data.py` is the validated OpenF1/Jolpica HTTP and normalization
  boundary. `data.py` provides callback-facing session, cache, and preload
  helpers. Do not recreate FastF1 `Session`/`Laps` methods as a compatibility
  shim.
- `telemetry_prep.py`, `graphs_*.py`, `graph_shared.py`, and
  `strategy_insights.py` transform normalized frames into graph inputs and
  figures. Graph builders must stay deterministic and free of Dash request
  state.
- `runtime.py` is the only place that decides whether execution is local or
  serverless. Do not scatter `os.getenv("VERCEL")` checks through features.
- `assets/custom.css` maintains responsive mechanics;
  `assets/race-intelligence.css` owns the visual system and loads after it;
  `assets/scripts.js` contains clientside Dash and Plotly replay code.

## Local workflow

Use Python 3.12 for deployment parity. Create a virtual environment, then:

```bash
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -q
python -m ruff check .
python app.py
```

The OpenF1 probe is an opt-in read-only engineering tool:

```bash
python scripts/probe_openf1.py --year 2023 --event Monaco --session-type Race --skip-trace
```

`tests/test_browser_smoke.py` is opt-in because it needs a running app,
Playwright, and live OpenF1 availability. Run it for end-to-end changes:

```bash
RUN_BROWSER_SMOKE=1 F1_ANALYZER_BASE_URL=http://127.0.0.1:8000 \
  python -m pytest tests/test_browser_smoke.py
```

## Provider and data rules

- Support completed OpenF1 archive sessions from 2023 onward; do not offer
  live sessions. A session becomes eligible only when it is at least 30 minutes
  past its published end and not canceled.
- Keep OpenF1 as the primary source for sessions, drivers, laps, selected-lap
  telemetry, position, weather, tyre, pit, race-control, results, and grid.
  Jolpica may fill missing classification data or provide a cross-check. Retain
  provenance and never present a supplement or estimate as an official OpenF1
  value.
- Check the [OpenF1 API docs](https://openf1.org/docs/) before changing
  endpoint behavior or limits. Current published free limits are 3 requests per
  second and 30 per minute. The application caps each process at 25/minute and
  spaces requests; this is not a global Vercel-instance limit.
- Request the narrowest endpoint profile needed by each tab. Fetch car and
  location data only for selected lap windows. Keep response sizes bounded,
  validate fields independently, cache historical JSON with bounded TTLs, and
  sanitize provider errors.
- OpenF1 car/location samples are about 3.7 Hz. Location has an arbitrary
  origin and approximate coordinates. Integrated speed distance is a derived
  progress axis. Do not claim sub-sample precision, measured circuit distance,
  or globally aligned circuit geometry.
- A car-only trace can support speed, throttle, brake, gear, RPM, and DRS when
  position samples are incomplete. Track maps, replay, and estimated-G views
  require adequate location samples and must explain missing location clearly.
- Normalize OpenF1 brake values from 0/100 to 0/1 for existing chart
  semantics, retain DRS separately, merge location only within a bounded
  750 ms tolerance, and never interpolate across long gaps.
- When the fastest lap has a valid time but no usable trace, telemetry may use
  a faster-to-slower valid lap with a usable trace and must label it. Never
  substitute an explicitly selected lap number.
- OpenF1 does not provide FastF1-equivalent deleted-lap accuracy or exact
  per-lap track status. Use only published pit/race-control evidence, label
  derived status and degradation estimates, and never silently claim exact
  clean-lap filtering.
- Pit-lane duration and stationary service duration are different fields;
  never substitute one for the other. Qualifying phase arrays and lapped gap
  strings must retain their meaning.
- Never mutate a cached bundle, DataFrame, or figure input in place. Copy
  before transformations when a caller might reuse the value.
- Background preloading is for a persistent process only. Vercel must load on
  demand and never depend on a daemon finishing after the response. Redis may
  cache only bounded, JSON-safe selected-lap payloads; never serialize provider
  objects, pickle frames, store credentials, or claim a global rate limit.
- AI session/classification context must remain available when telemetry is
  unavailable. Include provenance and instruct the model not to infer
  unsupported telemetry or official result claims.

## Dash and frontend rules

- Preserve component IDs or update every dependent callback and browser test.
  Search with `rg "component-id"` before renaming one.
- Keep expensive work server-side and replay/hover work client-side. Avoid a
  Python callback on high-frequency playback events.
- Prefer graphite surfaces, hairline dividers, condensed editorial type, and
  signal red for action. Avoid gradients, large rounded cards, novelty effects,
  and gratuitous motion.
- Assets that are not filename-hashed (`custom.css`, `race-intelligence.css`,
  `scripts.js`, and `manifest.json`) must revalidate on every deploy. Do not add
  them to a cache-first service-worker list.
- For layout or CSS changes, inspect both narrow/mobile and desktop views.

## Hosting and runtime

- Vercel is supported for serverless-first use. Keep root `app.py` as the Flask
  WSGI function, retain native Dash asset paths, do not add a catch-all rewrite,
  and keep the configured Fluid Compute and 300-second function budget. Do not
  describe Vercel as unsupported without evidence of a platform failure.
- Vercel `/tmp`, Python LRU caches, API request counters, feedback files, and AI
  cache files are ephemeral and instance-local. They are performance aids, not
  durable storage or global rate limits.
- For regular public traffic, prefer a single persistent Render process so its
  local response cache and rate limiter are shared across requests. Keep one
  threaded Gunicorn worker unless memory is explicitly re-evaluated.
- `render.yaml` is the supported Render blueprint; its health check is
  `/healthz`. Redis credentials remain external to the repository.
- Before promising durable feedback, shared caching, analytics, authentication,
  or robust global rate limiting, introduce an approved managed store behind a
  small repository module.

## Secrets and safety

- Never commit `.env`, API keys, admin tokens, feedback, provider payload dumps,
  or runtime cache data.
- `GEMINI_API_KEY` and `FEEDBACK_ADMIN_TOKEN` belong in host environment
  variables. Do not include raw provider error bodies in user-facing UI/API
  responses.
- Admin tooling should use a header or cookie, never a query-string token.

## Change checklist

1. Add or adjust focused tests for behavior changes.
2. Run the unit suite and `ruff check .`.
3. For Dash changes, load `/`, `/health`, and a real browser interaction.
4. Inspect the final diff for cached data, secrets, unrelated generated files,
   accidental ID changes, and unused modules.
5. Update `README.md` and `docs/` when deployment or architecture changes.
