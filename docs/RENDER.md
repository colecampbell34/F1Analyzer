# Render deployment

## Why use Render

The application is supported on Vercel and Render. For a regularly used
public instance, Render is the recommended host for this OpenF1-backed version:
one persistent Python process shares its bounded response cache and
process-local API limiter across requests, and can run background preloads.
Keep the service at one Gunicorn worker so requests use the same process state.

Render Free is useful for a low-traffic demo, but the service sleeps after
inactivity and local files are not durable through restart or redeploy. Use a
paid, always-on web service for a regularly used instance. The app itself does
not require a persistent disk for OpenF1 session data because historical API
responses are cached in process; feedback and AI response files remain
ephemeral unless connected to managed storage.

## Deploy

1. Push the repository, including `render.yaml`, to the branch to deploy.
2. In Render, choose **New → Blueprint**, connect the repository, and create
   the `f1-analyzer` web service.
3. Set optional environment variables in the service dashboard, then deploy.
4. Visit `https://YOUR-SERVICE.onrender.com/healthz`; expect
   `status: "ok"` and `runtime: "local"`.
5. Set `PUBLIC_BASE_URL` to the service URL or custom domain and redeploy.

The blueprint runs `gunicorn app:server` with one threaded worker, a 300-second
request timeout, and `/healthz` as the health check. It enables background
preloading because Render is persistent.

## Environment variables

| Variable | Required | Purpose |
| --- | --- | --- |
| `PUBLIC_BASE_URL` | Recommended | Canonical Open Graph URL |
| `GEMINI_API_KEY` | Optional | Enables AI analysis |
| `FEEDBACK_ADMIN_TOKEN` | Optional | Protects feedback review endpoints |
| `AI_CACHE_DIR` / `FEEDBACK_DIR` | Optional | Override local runtime file paths |
| `UPSTASH_REDIS_REST_URL` / `UPSTASH_REDIS_REST_TOKEN` | Optional | Shared selected-lap cache |
| `ENABLE_BACKGROUND_PRELOAD` | Blueprint sets `1` | Persistent-process preloads |

The Vercel Upstash names `KV_REST_API_URL` and `KV_REST_API_TOKEN` are also
accepted. Do not set `VERCEL`; runtime behavior is derived from that platform
environment automatically.

## Verification

1. Visit `/`, `/health`, and `/healthz`.
2. Select a completed 2023+ session and two drivers, then load the dashboard.
3. Exercise Telemetry and Track Map with a lap that has position samples.
4. Exercise Strategy and Race & Pace, then confirm missing optional feeds are
   shown as view-specific limitations.
5. Load the same session again and confirm the process-local cache reduces
   repeat API requests.

Use `/healthz?cache=1` only as an administrator diagnostic. It reports whether
the optional shared cache is reachable without returning its URL, token, or
cached data.

## Choosing one canonical host

Pick one public production URL. A Vercel deployment is still a valid choice
for serverless-first traffic and remains configured with native Flask routing,
Fluid Compute, and the 300-second function budget. Keep it on Vercel when that
deployment model is more useful than shared per-process state. For regular
traffic and the most predictable OpenF1 request pacing, prefer the single
persistent Render service described above.
