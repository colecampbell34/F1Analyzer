# F1 Analyzer

An interactive F1 telemetry and strategy dashboard built with Python, Dash, Plotly, FastF1, and powered by Google Gemini AI. 

This application provides a comprehensive suite of tools for visualizing and analyzing Formula 1 session data. It allows users to compare driver telemetry, track dominance, race pace, and strategy, all while chatting with an integrated AI that understands the intricate lap-by-lap session details.

## Features

- **Telemetry Traces**: Compare two drivers' speed, throttle, braking, and gear usage across their fastest laps with synchronized distance tracking.
- **2D Track Dominance**: High-resolution track map colored by micro-sectors, visually highlighting which driver was faster in specific corners and straights.
- **Strategy & Weather**: Dual-axis plot tracking race pace across stints, tyre compounds, pit windows, Track Status (SC, VSC, Red Flags), and live Track Temperature overlays.
- **AI Data Assistant**: Ask questions directly to Google Gemini, which is fed comprehensive context regarding the session, including every lap time, sector time, and tyre compound for the entire grid.

## Prerequisites

- Python 3.8+
- A Google Gemini API Key

## Installation

1. **Clone the repository:**
   ```bash
   git clone <your-repo-url>
   cd F1Analyzer
   ```

2. **Install requirements:**
   ```bash
   pip install dash dash-bootstrap-components plotly fastf1 pandas numpy google-genai python-dotenv
   ```

3. **Set up your API Key:**
   Create a `.env` file in the same directory as `app.py` and add: `GEMINI_API_KEY="your-actual-api-key"`

## Usage

Run the app locally:
```bash
python app.py
```
Then, open your web browser and navigate to port 8050 (or whatever port you're running it on).

## Important Notes
- The app uses `fastf1` which downloads session data heavily. The app automatically creates an `f1_cache` folder in the project directory to cache this data and speed up subsequent loads.
- The cache has an automatic clearer that will prune the data if it exceeds 2.0GB to save disk space.