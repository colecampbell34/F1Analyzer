# F1 Analyzer

An interactive Formula 1 telemetry and strategy dashboard built with Python Dash.

## Overview

Allows users to visualize and analyze F1 session data including telemetry, track dominance, race pace, and strategy. Includes an integrated AI assistant powered by Google Gemini.

## Tech Stack

- **Language**: Python 3.12
- **Web Framework**: Dash (built on Flask + React + Plotly)
- **UI Components**: Dash Bootstrap Components (CYBORG theme)
- **Data**: FastF1 (F1 telemetry), Pandas, NumPy
- **AI**: Google Gemini (via `google-genai`)
- **Production Server**: Gunicorn

## Project Structure

- `app.py` - Entry point; initializes Dash app, exposes `server` for gunicorn
- `layout.py` - UI structure (sidebar controls + tabbed content area)
- `callbacks.py` - Reactive Dash callbacks
- `graphs.py` - Plotly figure builders
- `data.py` - Data fetching, FastF1 caching, cache cleanup
- `ai_utils.py` - Google Gemini integration
- `assets/custom.css` - Custom styling

## Running the App

```bash
python app.py
```

Runs on `http://0.0.0.0:5000`

## Environment Variables

- `GEMINI_API_KEY` - Google Gemini API key for the AI assistant feature

## Key Features

- Telemetry comparison (speed, throttle, braking, gears)
- Track dominance map (2D visualization)
- Strategy & tyre analysis with race pace
- AI data assistant for natural language queries
- Auto-caching of F1 session data (pruned at 2GB)

## Deployment

Configured for autoscale deployment using gunicorn:
```
gunicorn --bind=0.0.0.0:5000 --reuse-port app:server
```
