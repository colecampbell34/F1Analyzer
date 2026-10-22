# Architecture

## Data flow

```text
Dash control
  -> callback module
  -> data.py session facade
  -> session_data.py validated OpenF1/Jolpica records
  -> normalized SessionBundle and selected-lap traces
  -> telemetry_prep.py / graphs_*.py / strategy_insights.py
  -> Plotly figure and browser-side replay state
```

OpenF1 supplies the primary 2023+ historical session data. Jolpica is a
supplement for missing classification fields, not a replacement for telemetry.
`session_data.py` keeps provider response names at the HTTP boundary and emits
ordinary pandas frames with normalized driver, result, grid, lap, stint, pit,
weather, race-control, position, and interval fields. Each bundle includes
endpoint states, row counts, source labels, and caveat notes.

`data.py` provides stable callback-facing helpers, bounded in-process
session/driver caches, and optional preloads. It does not recreate FastF1's
`Session` or `Laps` APIs. Graph builders consume normalized columns and do not
read Flask or Dash request state.

## Request and cache profiles

- Session and driver selection loads schedule metadata and a small driver/result
  summary.
- Strategy and Race & Pace request laps, stints, pits, weather, and the race
  context needed by those views.
- Car and location samples are requested only for selected laps. A car-only
  trace supports speed and pedal views; map, replay, and estimated-G views
  require enough location points.
- Selected-lap results use bounded JSON-safe local caching and optional Redis
  sharing. The shared cache never stores complete session objects, credentials,
  or raw session-wide telemetry.
- Historical low-volume endpoint responses use process-local TTL caching.
  Requests are spaced and capped at 25 OpenF1 requests per minute per process.
  This does not provide a global limit across separate serverless instances.

The OpenF1 free API publishes historical data for 2023 onward without
authentication, with live access treated separately. Sessions remain
unavailable to this app until they are at least 30 minutes past their published
end. API field coverage and terms can change; review the [OpenF1
documentation](https://openf1.org/docs/) before changing provider behavior.

## Data quality and analysis limits

- Selected car/location streams are sampled at about 3.7 Hz. Location points
  are approximate with an arbitrary origin. They support relative shape and
  progress, not calibrated circuit coordinates.
- Distance is integrated from speed over sample intervals. It is a derived
  progress axis and is not asserted as official circuit distance.
- Location samples join to car samples only within 750 ms. Missing or sparse
  location does not block speed analysis, but position-dependent views return a
  clear limitation.
- The map labels local speed-minimum markers as heuristics. MultiViewer circuit
  corners are fetched only as an optional source; their coordinate frame is
  not currently verified against OpenF1 location traces.
- OpenF1 does not publish FastF1's deleted-lap accuracy flag or exact per-lap
  track-status field. Pit-in/out and explicit race-control lap references are
  used where published; any status window derived from event timestamps is a
  heuristic.
- A pit endpoint may publish total pit-lane duration without stationary
  service duration. The application labels those semantics separately.
- Race and qualifying results can be pending or incomplete. OpenF1 values are
  source-labeled; Jolpica supplements remain distinguishable and never become
  a claim of OpenF1 provenance.

These limitations are surfaced in the layout, figure subtitles, and AI context.
Missing optional data should not disable unrelated views.

## Module boundaries

| Area | Responsibility | Must not do |
| --- | --- | --- |
| `layout.py` | Component tree and stable IDs | Fetch provider data |
| `callbacks*.py` | Orchestration, selection, and validation | Implement graph math |
| `data.py` | Session facade, in-process cache, and preload policy | Render Dash components |
| `session_data.py` | OpenF1/Jolpica HTTP, validation, normalization, provenance | Read Dash request state |
| `telemetry_prep.py` | Selected-lap trace selection and bounded serialization | Cache provider session objects |
| `graphs*.py` | Deterministic Plotly figures | Read Flask request state |
| `telemetry_dynamics.py` / `strategy_insights.py` | Deterministic estimates and strategy summaries | Depend on Dash request state |
| `runtime.py` | Local versus serverless filesystem policy | Know product behavior |
| `assets/` | Styling and high-frequency browser interactions | Hold secrets or call server callbacks per replay frame |

## Runtime choices

Vercel is supported for on-demand serverless requests. In-memory endpoint and
rate-limit state is instance-local and ephemeral; the process never depends on
a preload thread completing after a response. Fluid Compute and the configured
300-second budget provide headroom for a cold selected-lap request, but do not
make those caches shared or durable.

For regular public traffic, a single persistent Render service is the
recommended profile. One threaded Gunicorn worker shares the local endpoint
cache and rate limiter across requests and can finish background preloads.
Render Free sleeps and has ephemeral local storage; a paid service avoids
sleeping. Add a managed store before promising durable feedback, global rate
limits, analytics, authentication, or shared AI response caching.
