# 🏎️ F1 Analyzer

[![Python](https://img.shields.io/badge/Python-3.9+-blue.svg)](https://www.python.org/)
[![Dash](https://img.shields.io/badge/Dash-2.14+-008bb4.svg)](https://dash.plotly.com/)
[![FastF1](https://img.shields.io/badge/FastF1-3.3+-red.svg)](https://github.com/theOehrly/FastF1)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

An advanced Formula 1 telemetry and strategy analysis dashboard powered by **Google Gemini AI**. Compare driver performance, visualize track dominance, and get deep technical insights into every F1 session.

**Try it out:** [https://f-1-analyzer--colecampbell34.replit.app](https://f-1-analyzer--colecampbell34.replit.app)

## 🌟 Key Features

- **📊 Advanced Telemetry Traces**: Compare speed, throttle, braking, and gear usage with millisecond precision.
- **🛣️ 2D Track Dominance Maps**: See exactly where drivers gain or lose time through high-resolution micro-sector analysis.
- **📈 Strategy & Race Pace**: Analyze tyre compounds, pit windows, and track conditions with live overlays.
- **🤖 AI Race Engineer**: Chat with an integrated Gemini-powered assistant that has full context of the session data.
- **🏁 Session Leaderboards**: Instant access to live timing and results for any GP since 2018.
- **📱 Mobile Friendly**: Responsive design optimized for both desktop and mobile viewing.

## 🚀 Getting Seen & Sharing

F1 Analyzer is built for the F1 community. Here is how you can help it grow:

1.  **Share Findings**: Use the **"Share Comparison"** button in the sidebar to copy a direct link to your current analysis.
2.  **Reddit & Twitter**: Found an interesting strategy or a massive telemetry gap? Share it on r/formula1 or Twitter and tag your favorite F1 analysts!
3.  **GitHub Stars**: If you find this tool useful, consider leaving a ⭐ on the repository to help others discover it.

## 🛠️ Technical Stack

- **Data**: [FastF1](https://github.com/theOehrly/FastF1) (Open-source F1 data API)
- **UI**: [Dash](https://dash.plotly.com/) & [Plotly](https://plotly.com/python/)
- **AI**: [Google Gemini Pro](https://deepmind.google/technologies/gemini/)
- **Styling**: Dash Bootstrap Components (Cyborg Theme)

## 💻 Local Setup

1. Clone the repo: `git clone https://github.com/colecampbell34/F1Analyzer.git`
2. Install dependencies: `pip install -r requirements.txt`
3. Create a `.env` file with your `GOOGLE_API_KEY`.
4. Run the app: `python app.py`

---

*Note: This project is unofficial and not associated with Formula 1 or any of its teams. Data provided by FastF1.*
 