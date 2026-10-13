# Vercel deployment

## Configuration

The app deploys as one Flask WSGI Vercel Function:

- entrypoint: `api/index.py`
- root rewrite: `/api/index`
- deployment Python: 3.12 (`.python-version`)
- function timeout: 60 seconds, compatible with the conservative Vercel plan
  limit while first FastF1 loads remain bounded

Set these environment variables in Vercel as appropriate:

| Variable | Required | Purpose |
| --- | --- | --- |
| `PUBLIC_BASE_URL` | Recommended | Canonical Open Graph/share URL |
| `GEMINI_API_KEY` | Optional | Enables AI Analysis |
| `FEEDBACK_ADMIN_TOKEN` | Optional | Enables feedback review endpoints |
| `FASTF1_CACHE_DIR` | Optional | Overrides FastF1 writable cache directory |
| `AI_CACHE_DIR` | Optional | Overrides local AI cache directory |
| `FEEDBACK_DIR` | Optional | Overrides local feedback directory |

## Cache policy

Dash uses stable names for `custom.css`, `race-intelligence.css`,
`scripts.js`, and `manifest.json`. Those files revalidate so a deployment
cannot combine old JavaScript with a new Dash renderer. Only versioned icon
assets and Dash component-suite URLs are cached long-term. The service worker
also avoids cache-first handling for mutable application shell assets.

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
