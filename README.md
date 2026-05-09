# F1 Analyzer

[![Python](https://img.shields.io/badge/Python-3.9+-blue.svg)](https://www.python.org/)
[![Dash](https://img.shields.io/badge/Dash-2.14+-008bb4.svg)](https://dash.plotly.com/)
[![FastF1](https://img.shields.io/badge/FastF1-3.3+-red.svg)](https://github.com/theOehrly/FastF1)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

An advanced Formula 1 telemetry and strategy analysis dashboard powered by Google Gemini AI. Compare driver performance, visualize track dominance, review race strategy, and ask data-grounded questions about a loaded session.

## Key Features

- Latest Race shortcut that selects the most recent completed race and defaults to the top two drivers.
- Telemetry traces for speed, throttle, braking, gears, delta, mini-map playback, and G-force.
- Track maps for dominance, braking, and speed overlays.
- Strategy, race gap, pit stop, tyre degradation, and grid pace views.
- AI analysis with session-specific telemetry, weather, messages, and lap context.
- Shareable URLs that preserve session, drivers, active tab, lap mode, lap numbers, and track-map mode.
- Feedback capture with optional admin review and CSV export.

## Sharing

Use the Share Comparison button to copy a direct link to the current analysis. Shared links include:

- Year, race, session, drivers
- Active tab
- Specific lap modes and lap numbers
- Track map overlay mode

## Technical Stack

- Data: FastF1, Pandas, NumPy, SciPy
- UI: Dash, Plotly, Dash Bootstrap Components
- AI: Google Gemini via `google-genai`
- Runtime: Flask, Gunicorn, Flask-Compress
- Frontend runtime: Dash's React renderer with clientside JavaScript for high-frequency chart interactions

## Project Structure

- `app.py` - Dash app setup, Flask server, health/warmup routes, runtime init.
- `layout.py` - Sidebar, tabs, modals, stores, and page structure.
- `callbacks.py` - Core dropdowns, URL sync, latest-race defaults, summary/status callbacks.
- `callbacks_telemetry.py` - Telemetry chart, mini-map, G-force, and playback callbacks.
- `callbacks_tabs.py` - Track map, strategy, race, and grid pace callbacks.
- `callbacks_ai.py` - AI context loading, question handling, and history callbacks.
- `callbacks_feedback.py` - Feedback modal, inbox, and CSV callbacks.
- `data.py` - FastF1 loading, caching, preloading, pruning, and schedule helpers.
- `telemetry_prep.py` - Shared selected-lap telemetry preparation.
- `graph_shared.py` - Shared graph config, colors, error figures, and graph helpers.
- `graphs.py` - Feature-specific Plotly figure builders.
- `ai_utils.py` - Gemini prompt construction and session context building.
- `ai_cache.py` - AI response cache and per-user rate limiting.
- `ui_utils.py` - UI formatting helpers, summaries, leaderboard, and feedback rendering.

## Local Setup

1. Clone the repo: `git clone https://github.com/colecampbell34/F1Analyzer.git`
2. Install dependencies: `pip install -r requirements.txt`
3. Create a `.env` file with your AI key if you want AI enabled.
4. Run the app: `python app.py`


## Environment Variables

- `GEMINI_API_KEY` - Enables AI Analysis.
- `FEEDBACK_ADMIN_TOKEN` - Enables the feedback inbox and CSV export for authorized admins.
- `CALLBACK_TIMING_THRESHOLD_MS` - Logs callbacks slower than this threshold. Default: `400`.
- `LOG_ALL_CALLBACKS=1` - Logs every timed callback.
- `LOG_SESSION_LOADING=1` - Logs session preload/load behavior.
- `FASTF1_CACHE_DIR` - Optional runtime cache directory. Defaults to `f1_cache/` locally and `/tmp/f1_cache` on Vercel.
- `AI_CACHE_DIR` - Optional AI response cache directory. Defaults to `ai_cache/` locally and `/tmp/ai_cache` on Vercel.
- `FEEDBACK_DIR` - Optional feedback storage directory. Defaults to `feedback/` locally and `/tmp/feedback` on Vercel.
- `PUBLIC_BASE_URL` - Optional production URL for Open Graph metadata and social share links.
- `ENABLE_VERCEL_ANALYTICS=1` - Opts into Vercel Web Analytics and Speed Insights scripts. They are disabled by default to keep the first frontend load lighter.

## Runtime Data

- `f1_cache/` stores FastF1 cache data and is pruned automatically.
- `ai_cache/responses.json` stores cached AI answers for repeated questions/context.
- `feedback/entries.jsonl` stores feedback submissions with hashed reporter IPs.

These directories are runtime artifacts and should not be committed.

## Testing

Run the current test suite with:

```bash
python3 -m unittest discover -s tests -q
```

## Deployment

Example Gunicorn command:

```bash
gunicorn app:server --bind 0.0.0.0:5000 --timeout 300 --workers 2 --threads 4 --worker-class gthread
```

The app exposes:

- `/health` and `/healthz` for cheap liveness checks.
- `/warmup` to start background runtime initialization and schedule cache warming.
- `/m` redirects to `/`; the app now uses one canonical URL with responsive layout.

### Vercel

This repo includes a Vercel WSGI entrypoint at `api/index.py`, plus `vercel.json`
and `.vercelignore` to keep the serverless bundle small. Set `PUBLIC_BASE_URL`
to your production URL so Open Graph metadata points at the Vercel domain.

The FastF1 cache is runtime data and is intentionally excluded from deployment.
First loads on a cold function can still take time while FastF1 rebuilds cache
data, so use `/warmup` after deployment if you want to prime lightweight startup
work before sharing the app.

---

*Note: This project is unofficial and not associated with Formula 1 or any of its teams. Data provided by FastF1.*
 
