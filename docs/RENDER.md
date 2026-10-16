# Render deployment

## When Render makes sense for FastF1

The Dash application is supported on Vercel. This repository enables Vercel
Fluid Compute and a 300-second Python-function limit, so a Vercel deployment
is the first option to validate.

Render is an alternative if you deliberately prefer a single long-lived
Gunicorn process. While it is awake, that process can reuse FastF1's local
cache across requests and can use the app's background preload workflow.

Render runs this application as one long-lived Gunicorn process while the
service is awake. That lets FastF1 complete a cold car-data download, reuse
its local cache for later requests, and use the app's background preload
workflow. The supplied [`render.yaml`](../render.yaml) uses one worker so a
large FastF1 session is not duplicated in memory.

Free Render services sleep after 15 minutes without inbound traffic and their
filesystem is erased when they restart or redeploy. This is acceptable for a
hobby deployment: the first request after a wake can be slow, while shared
Redis keeps prepared two-driver telemetry traces available across processes.

## Deploy

1. Push the repository, including `render.yaml`, to the branch you want to
   deploy.
2. In Render, choose **New > Blueprint**, connect the repository, and select
   it. Render discovers the root `render.yaml`; confirm the `f1-analyzer`
   service and create it on the **Free** plan defined by the Blueprint. For a
   regularly used production service, change the instance type to a paid web
   service after the first deploy; that prevents sleeping and permits a
   persistent disk.
3. Open the service's **Environment** page and set the variables below. Trigger
   a manual deploy after adding them.
4. When the service is live, open `https://YOUR-SERVICE.onrender.com/healthz`.
   It should return JSON with `status: "ok"` and `runtime: "local"`.
5. Set `PUBLIC_BASE_URL` to the new `https://YOUR-SERVICE.onrender.com` URL
   (or your custom domain) and redeploy once more.

## Environment variables

| Variable | Required | Value / purpose |
| --- | --- | --- |
| `PUBLIC_BASE_URL` | Recommended | The Render service URL, without a trailing slash. |
| `KV_REST_API_URL` | Recommended | Existing Vercel/Upstash REST URL. |
| `KV_REST_API_TOKEN` | Recommended | Existing writable Vercel/Upstash REST token. |
| `GEMINI_API_KEY` | Optional | Enables AI Analysis. |
| `FEEDBACK_ADMIN_TOKEN` | Optional | Protects the feedback/performance-admin endpoints. |
| `ENABLE_BACKGROUND_PRELOAD` | Set by blueprint | Keep as `1` for the persistent service. |

Do not set `VERCEL`, `FASTF1_CACHE_DIR`, `AI_CACHE_DIR`, or `FEEDBACK_DIR` on
Render unless you have a specific reason. The app chooses suitable local paths
automatically. Do not copy `KV_REST_API_READ_ONLY_TOKEN`: the cache needs the
writable `KV_REST_API_TOKEN`.

### Recommended paid-service cache setup

Free Render instances spin down after 15 minutes of inactivity and lose their
local filesystem when they sleep, restart, or redeploy. For a regularly used
instance, attach a persistent disk in **Settings > Disks** and mount it at
`/var/data`. Then add these environment variables:

| Variable | Value |
| --- | --- |
| `FASTF1_CACHE_DIR` | `/var/data/f1_cache` |
| `AI_CACHE_DIR` | `/var/data/ai_cache` |
| `FEEDBACK_DIR` | `/var/data/feedback` |

The application creates these directories itself. A persistent disk is
single-instance storage, so keep the service at one instance—the supplied
Blueprint already does this—and retain Redis for derived telemetry sharing.
Feedback and the AI-response cache are still local files, not a collaborative
or durable database; use a managed store before treating either as durable
product data.

## Verification

After deployment, select a known finished event such as **2025 Australian
Grand Prix — Qualifying**, choose **NOR** and **PIA**, then open **Telemetry**.
The first cold load can take a little while; a repeat load should be much
faster. `/warmup` can be opened after the service wakes to start non-critical
cache initialization, but it does not replace loading an actual session.

When validating a paid disk, trigger a manual deploy after the first telemetry
load, then repeat the same comparison. The FastF1 cache directory should
survive the deploy and avoid rebuilding the raw timing data. Use
`/healthz?cache=1` only as an administrator diagnostic: it reports whether
the optional shared cache is reachable without returning cache contents.

## Choosing one canonical host

Use one host as the public production URL. Hosting the same live app on both
Vercel and Render splits their local FastF1 caches and makes investigations
harder. If you move to Render after validating it, set `PUBLIC_BASE_URL` to its
URL; otherwise leave the Vercel URL as canonical.
