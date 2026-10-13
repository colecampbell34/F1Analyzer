# F1 Analyzer contributor guide

## Product intent

F1 Analyzer is a technical comparison desk for Formula 1 sessions. The core
experience is selecting a historical or current session, choosing two drivers,
and explaining the performance difference through telemetry, track position,
race pace, strategy, and optional AI analysis. Keep that workflow fast and
trustworthy. The interface should feel like a motorsport engineering tool, not
a game or a generic admin dashboard.

## Architecture map

- `app.py` owns the Flask/Dash application, HTTP routes, response caching, and
  process startup policy.
- `layout.py` owns all Dash components and their stable IDs. Callback modules
  depend on those IDs; treat them as a public contract.
- `callbacks.py` owns selection, URL state, loading state, and common UI.
  Tab-specific callback registration lives in `callbacks_telemetry.py`,
  `callbacks_tabs.py`, `callbacks_ai.py`, and `callbacks_feedback.py`.
- `data.py` is the FastF1 boundary: session loading, in-process caching,
  preloading, schedules, and driver metadata belong there.
- `telemetry_prep.py`, `graphs_*.py`, and `graph_shared.py` transform loaded
  data into figure inputs and Plotly figures. Keep graph builders deterministic
  and free of Dash request state.
- `runtime.py` is the only place that decides whether execution is local or
  serverless. Do not scatter `os.getenv("VERCEL")` checks through features.
- `assets/custom.css` maintains existing responsive and component mechanics;
  `assets/race-intelligence.css` owns the product visual system and loads after
  it. `assets/scripts.js` contains clientside Dash callbacks and Plotly replay
  work.

## Local workflow

Use Python 3.12 for deployment parity. Create a virtual environment, then:

```bash
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -q
python -m ruff check .
python app.py
```

`tests/test_browser_smoke.py` is opt-in because it needs a running app, a
browser, and live FastF1 availability. Run it only for an end-to-end change:

```bash
RUN_BROWSER_SMOKE=1 F1_ANALYZER_BASE_URL=http://127.0.0.1:8000 \
  python -m pytest tests/test_browser_smoke.py
```

## Data and performance rules

- Keep FastF1 as the telemetry source. Jolpica is useful for lightweight
  results metadata but cannot replace FastF1's lap telemetry, circuit data,
  and timing streams.
- Request the narrowest FastF1 profile needed by a tab. Do not load telemetry,
  weather, or race-control messages globally by default.
- Never mutate a cached session, telemetry DataFrame, or figure input in place.
  Copy before transformation when a caller might reuse the data.
- Background preloading is for a persistent local process only. Vercel must
  load on demand; a serverless invocation must never depend on a daemon thread
  finishing after the response.
- Treat FastF1 data as incomplete until validated. Graphs should return a
  useful empty/error figure rather than failing the entire dashboard.

## Dash and frontend rules

- Preserve component IDs or update every dependent callback and browser test
  in the same change. Search with `rg "component-id"` before renaming one.
- Keep expensive work server-side and replay/hover work client-side. Avoid a
  Python callback on high-frequency playback events.
- Prefer a small number of purposeful visual tokens: graphite surfaces,
  hairline dividers, condensed editorial type, and signal red for action.
  Avoid gradients, large rounded cards, novelty effects, and gratuitous motion.
- Assets that are not filename-hashed (`custom.css`, `race-intelligence.css`,
  `scripts.js`, and `manifest.json`) must revalidate on every deploy. Do not
  add them to a cache-first service-worker list.
- Test both a narrow/mobile and desktop viewport after changing layout or CSS.

## Vercel constraints

- Vercel detects the Flask WSGI object exported by root `app.py`; configure
  `app.py` in `functions` and do not add a catch-all rewrite. A rewrite to a
  fixed function URL discards the requested Dash asset path, returning the
  dashboard HTML for CSS and component-suite JavaScript URLs.
- `/tmp` cache, AI-response cache, feedback file, rate-limit state, and Python
  LRU caches are instance-local and ephemeral on Vercel. They are performance
  aids, not durable storage or globally consistent rate limits.
- Before promising durable feedback, shared caching, analytics, authentication,
  or robust rate limiting, introduce an approved managed store (for example
  Vercel KV/Postgres) behind a small repository module.
- Keep `vercel.json` function exclusions aligned with source structure. Do not
  exclude `assets/`: Flask serves the root service worker and Dash needs the
  custom assets.

## Secrets and safety

- Never commit `.env`, API keys, admin tokens, feedback, FastF1 cache data, or
  AI cache data.
- `GEMINI_API_KEY` and `FEEDBACK_ADMIN_TOKEN` belong in Vercel environment
  variables. Do not include raw provider error bodies in user-facing UI/API
  responses.
- Query-string admin tokens are legacy-only; prefer a header or cookie for any
  admin tooling and remove the fallback when a proper admin path exists.

## Change checklist

1. Add/adjust focused unit tests for behavior changes.
2. Run the unit suite and `ruff check .`.
3. For Dash, load `/`, `/health`, and at least one real browser interaction.
4. Check the diff for accidental cache data or unrelated generated files.
5. Update `README.md` and `docs/` when deployment or architecture changes.
