# Vercel deployment

## Configuration

The app deploys as one Flask WSGI Vercel Function:

- entrypoint: root `app.py`
- root rewrite: none (Vercel's Flask integration preserves the requested path)
- deployment Python: 3.12 (`.python-version`)
- Fluid Compute: explicitly enabled for this deployment
- function timeout: 300 seconds, the current Hobby-plan maximum with Fluid
  Compute

Set these environment variables in Vercel as appropriate:

| Variable | Required | Purpose |
| --- | --- | --- |
| `PUBLIC_BASE_URL` | Recommended | Canonical Open Graph/share URL |
| `GEMINI_API_KEY` | Optional | Enables AI Analysis |
| `FEEDBACK_ADMIN_TOKEN` | Optional | Enables feedback review endpoints |
| `FASTF1_CACHE_DIR` | Optional | Overrides FastF1 writable cache directory |
| `AI_CACHE_DIR` | Optional | Overrides local AI cache directory |
| `FEEDBACK_DIR` | Optional | Overrides local feedback directory |
| `KV_REST_API_URL` | Recommended | Upstash REST endpoint injected by Vercel for the shared selected-lap cache |
| `KV_REST_API_TOKEN` | Recommended | Writable Upstash REST token injected by Vercel for the shared cache |

## Cache policy

Dash uses stable names for `custom.css`, `race-intelligence.css`,
`scripts.js`, and `manifest.json`. Those files revalidate so a deployment
cannot combine old JavaScript with a new Dash renderer. Only versioned icon
assets and Dash component-suite URLs are cached long-term. The service worker
also avoids cache-first handling for mutable application shell assets.

### Shared FastF1-derived cache

For consistently quick telemetry loads across separate Vercel instances,
install an Upstash Redis integration through the Vercel Marketplace and
connect it to this project. Confirm that the integration supplies
`KV_REST_API_URL` and writable `KV_REST_API_TOKEN` to the Production
environment (Preview is optional). No code or `vercel.json` change is needed.

The application stores a bounded, compressed, schema-versioned selected-lap
comparison payload: driver labels/colors, lap times, and the graph columns
needed for speed, delta, and position views. It does **not** serialize FastF1
session objects or copy FastF1's local cache directory. A short Redis lock
limits duplicate cold loads; a timeout or Redis outage falls back to direct
FastF1 loading without making a dashboard request fail.

Default retention is 6 hours for the current season and 30 days for historical
seasons. Override it with `SHARED_TELEMETRY_CURRENT_TTL_SECONDS` and
`SHARED_TELEMETRY_HISTORICAL_TTL_SECONDS` when needed. Check the protected
`/api/perf` endpoint after deployment: `cache.selected_lap_cache.shared`
reports whether the integration is configured and its hit/miss counters.

## Post-deploy smoke checks

1. Visit `/health` and confirm `status: ok`.
2. Load `/` in a clean browser window and confirm the title is *F1 Analyzer —
   Race Intelligence*.
3. Click **Latest Race**; the Grand Prix and session controls should populate.
4. Select a pair, click **Update Dashboard**, and load the Telemetry and Track
   Map tabs.
5. If an old client looks stale, refresh once; the new service worker activates
   immediately and releases prior caches.

## Limits to understand

The Vercel function filesystem and in-memory caches are ephemeral. Feedback,
AI-cache entries, request rate limits, and FastF1 cache hits can disappear
between invocations. Use a managed data store before treating any of those as
durable or globally shared production state.
