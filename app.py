import logging
import dash
import dash_bootstrap_components as dbc
from layout import app_layout
from callbacks import register_callbacks
import data
from feedback import setup_feedback_storage
from ai_utils import flush_ai_cache
from flask_compress import Compress
import threading
import atexit
from datetime import datetime
from flask import jsonify, request

# Set global log level to WARNING
logging.basicConfig(level=logging.WARNING)
logging.getLogger('werkzeug').setLevel(logging.WARNING)
logging.getLogger('dash').setLevel(logging.WARNING)
logging.getLogger('flask').setLevel(logging.WARNING)
logging.getLogger('google.genai').setLevel(logging.WARNING)

app = dash.Dash(
    __name__,
    external_stylesheets=[dbc.themes.CYBORG, "https://use.fontawesome.com/releases/v5.15.4/css/all.css"],
    title="F1 Analyzer - Advanced Telemetry Dashboard",
    update_title=None,
    suppress_callback_exceptions=True,
    meta_tags=[
        {"name": "viewport", "content": "width=device-width, initial-scale=1"},
        {"rel": "manifest", "href": "/assets/manifest.json"},
        {"name": "description", "content": "Advanced Formula 1 telemetry and strategy analysis dashboard. Compare driver performance, track dominance, and get AI-powered race insights using FastF1 and Google Gemini."},
        {"property": "og:title", "content": "F1 Analyzer - Advanced Telemetry & AI Insights"},
        {"property": "og:description", "content": "Interactive F1 telemetry, strategy analysis, and Gemini AI insights. Compare laps, visualize track dominance, and analyze race pace."},
        {"property": "og:type", "content": "website"},
        {"property": "og:url", "content": "https://f-1-analyzer--colecampbell34.replit.app"},
        {"property": "og:image", "content": "https://f-1-analyzer--colecampbell34.replit.app/assets/og-image.png"},
        {"name": "twitter:card", "content": "summary_large_image"},
        {"name": "twitter:site", "content": "@F1Analyzer"},
        {"name": "theme-color", "content": "#ff0000"}
    ]
)

Compress(app.server)
server = app.server

_RUNTIME_INIT_LOCK = threading.Lock()
_RUNTIME_INIT_STARTED = False
_RUNTIME_INIT_DONE = False


def _init_runtime_background():
    """Run non-critical startup tasks outside the first paint path."""
    global _RUNTIME_INIT_DONE
    with _RUNTIME_INIT_LOCK:
        if _RUNTIME_INIT_DONE:
            return
        try:
            data.setup_cache()
            threading.Thread(target=data.maybe_prune_cache, daemon=True).start()
            setup_feedback_storage()
        finally:
            _RUNTIME_INIT_DONE = True


def _start_runtime_init_once():
    """Start lazy runtime initialization once per process."""
    global _RUNTIME_INIT_STARTED
    if _RUNTIME_INIT_STARTED or _RUNTIME_INIT_DONE:
        return

    with _RUNTIME_INIT_LOCK:
        if _RUNTIME_INIT_STARTED or _RUNTIME_INIT_DONE:
            return
        _RUNTIME_INIT_STARTED = True

    threading.Thread(target=_init_runtime_background, daemon=True).start()


@server.before_request
def _ensure_runtime_initialized():
    """Kick off deferred runtime initialization once, outside health/static probes."""
    if request.path in ('/health', '/healthz') or request.path.startswith((
        '/assets/',
        '/_dash-component-suites/',
        '/_favicon.ico',
    )):
        return
    _start_runtime_init_once()


@server.route('/health', strict_slashes=False)
@server.route('/healthz', strict_slashes=False)
def healthz():
    """Cheap liveness endpoint for host health checks."""
    return jsonify({'status': 'ok'}), 200


@server.route('/warmup')
def warmup():
    """Prime lightweight caches to reduce cold-start request latency."""
    _start_runtime_init_once()
    threading.Thread(target=data.get_event_schedule_cached, args=(datetime.now().year,), daemon=True).start()
    return jsonify({'status': 'warming'}), 200


atexit.register(flush_ai_cache)
app.layout = app_layout
register_callbacks(app)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)
