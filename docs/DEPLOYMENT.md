# Vercel deployment

## Configuration

The project deploys as one Flask WSGI function:

- Entrypoint: root `app.py`
- Root rewrite: none; native Flask path handling preserves Dash asset URLs.
- Python: 3.12 (`.python-version`)
- Fluid Compute: enabled in `vercel.json`
- Function timeout: 300 seconds

Set these environment variables as needed:

| Variable | Required | Purpose |
| --- | --- | --- |
| `PUBLIC_BASE_URL` | Recommended | Canonical Open Graph URL |
| `GEMINI_API_KEY` | Optional | Enables AI analysis |
| `FEEDBACK_ADMIN_TOKEN` | Optional | Protects feedback review endpoints |
| `AI_CACHE_DIR` | Optional | Overrides AI-response cache path |
| `FEEDBACK_DIR` | Optional | Overrides feedback file path |
| `KV_REST_API_URL` / `KV_REST_API_TOKEN` | Optional | Upstash REST connection for selected-lap cache |
| `UPSTASH_REDIS_REST_URL` / `UPSTASH_REDIS_REST_TOKEN` | Optional | Alternative Upstash REST variable names |
| `ENABLE_BACKGROUND_PRELOAD` | Optional | Defaults off under Vercel; serverless loads are on demand |

Do not add a catch-all rewrite. Dash requests CSS and component-suite assets at
their own paths; routing every path to a fixed function path can return the
dashboard HTML in place of JavaScript or CSS.

## Cache and rate policy

Mutable assets (`custom.css`, `race-intelligence.css`, `scripts.js`, and
`manifest.json`) revalidate on deploy. The service worker does not cache those
assets cache-first.

The application keeps bounded in-memory OpenF1 response data and selected-lap
traces. Optional Upstash stores only the bounded, compressed selected-lap
comparison payload, never provider session objects or raw session-wide
telemetry. A Redis miss, timeout, or outage falls back to the local trace path.
Vercel instances do not share process-local rate-limit state, so this cache
does not make the OpenF1 request budget globally consistent.

`/health` and `/healthz` are local, inexpensive checks. Add `?cache=1` to
`/healthz` only when you need a secret-free shared-cache reachability check.
`/warmup` reports direct on-demand loading on Vercel; it does not start a
background preload.

## Release checks

1. Visit `/healthz` and confirm `status: ok` and `runtime: vercel`.
2. Load `/` and confirm the current dashboard assets load rather than HTML
   responses for CSS/JavaScript.
3. Use Latest Race, choose drivers, and load the dashboard.
4. Open Telemetry, Track Map, Strategy, and Race & Pace for a completed
   2023+ session. Missing location, result, weather, or race-control data should
   be reported only for the affected view.
5. Check `/api/session-summary?year=2023&race=Monaco%20Grand%20Prix&session=Race`
   for normalized driver/result fields and source labels.

## Limitations

The function filesystem and memory are ephemeral and per-instance. Feedback,
AI-response cache entries, API request counters, and local provider caches are
not durable. Add a managed shared store before treating any of those as durable
product data or a global rate-limit mechanism.

Vercel remains a supported host for serverless-first or infrequently used
deployments. For regular public traffic, see the [Render profile](RENDER.md):
one persistent process provides a shared local cache and limiter across its
requests.
