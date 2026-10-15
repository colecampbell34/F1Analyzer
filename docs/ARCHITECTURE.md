# Architecture

## Why FastF1 remains the primary data source

FastF1 is the correct foundation for this product. The app's value is in
distance-aligned car telemetry, timing streams, lap data, circuit geometry,
weather, and race-control context. Lightweight public APIs such as Jolpica are
excellent supplements for historical classifications and schedules, but they
do not replace FastF1 telemetry. The boundary in `data.py` keeps a future
metadata provider additive instead of forcing a rewrite.

## Request path

```text
Dash control
  -> callback module
  -> data.py selects the smallest FastF1 load profile on a cache miss
  -> telemetry_prep.py checks a shared prepared-trace cache when a telemetry view is opened
  -> telemetry_prep.py / graphs_*.py transform it
  -> Plotly figure and browser-side replay state
```

The default `tab-trackmap` profile requests telemetry only when it is needed
for the circuit comparison. Track Map owns an independent pair of lap
selectors, while Telemetry keeps its own selected-lap context. The selector
option loader joins the telemetry profile so the default view does not open a
second competing FastF1 request.

The browser stores rendered-figure fingerprints and replay payloads. The
Python process stores bounded LRU session objects. This keeps repeated tab
switches quick without serialising large FastF1 objects to the browser.

Lap replay uses `requestAnimationFrame` to move existing Plotly marker traces
in the browser. Dash owns the controls and bounded telemetry payload, but it
does not re-render figures for every animation frame. The loading overlay
acknowledges a view switch immediately while the corresponding lazy profile is
prepared without reserving a permanent status strip in the workspace.

When `UPSTASH_REDIS_REST_URL` and `UPSTASH_REDIS_REST_TOKEN` are configured,
`shared_cache.py` also stores bounded, compressed selected-lap trace payloads.
It uses a short distributed lock to reduce duplicate FastF1 cold loads across
Vercel instances. Redis is optional and non-authoritative: a miss, timeout, or
outage falls back to the normal FastF1 path.

## Module boundaries

| Area | Responsibility | Must not do |
| --- | --- | --- |
| `layout.py` | Component tree and stable IDs | Fetch FastF1 data |
| `callbacks*.py` | Orchestration and validation | Implement graph math |
| `data.py` | External data, cache, preload policy | Render Dash components |
| `graphs*.py` | Deterministic Plotly figures | Read Flask request state |
| `telemetry_dynamics.py` / `strategy_insights.py` | Deterministic derived telemetry and tyre-strategy context | Depend on Dash request state |
| `runtime.py` | Host/runtime policy | Know product behavior |
| `assets/` | Styling and high-frequency browser interaction | Hold secrets |

## Serverless reality

Vercel is a sound host for the app shell and on-demand requests, but it is not
a durable data plane. An individual invocation can reuse `/tmp` and memory,
but neither is shared or guaranteed across invocations. The app therefore
disables background preloads on Vercel and labels runtime state correctly.

When durable capabilities become a requirement, introduce an explicit store
adapter rather than quietly relying on local files:

```text
feature -> repository interface -> managed store
                              -> local file only in development
```

Candidates are feedback records, AI response caching, rate-limit counters,
and precomputed sessions. FastF1 raw cache remains best-effort because of its
size and source-specific cache semantics.
