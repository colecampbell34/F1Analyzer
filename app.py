import logging
import os
import dash
import dash_bootstrap_components as dbc
from layout import app_layout
from callbacks import register_callbacks
import data
from feedback import setup_feedback_storage
from ai_cache import flush_ai_cache
from flask_compress import Compress
import threading
import atexit
from datetime import datetime
from flask import jsonify, redirect, request, send_from_directory
import pandas as pd
from ui_utils import _feedback_admin_authorized
from perf_monitor import get_perf_snapshot

# Set global log level to WARNING
logging.basicConfig(level=logging.WARNING)
logging.getLogger('werkzeug').setLevel(logging.WARNING)
logging.getLogger('dash').setLevel(logging.WARNING)
logging.getLogger('flask').setLevel(logging.WARNING)
logging.getLogger('google.genai').setLevel(logging.WARNING)

PUBLIC_BASE_URL = os.getenv('PUBLIC_BASE_URL', 'https://f-1-analyzer--colecampbell34.replit.app').rstrip('/')

app = dash.Dash(
    __name__,
    external_stylesheets=[dbc.themes.CYBORG, "https://use.fontawesome.com/releases/v5.15.4/css/all.css"],
    title="F1 Analyzer - Advanced Telemetry Dashboard",
    update_title=None,
    suppress_callback_exceptions=True,
    meta_tags=[
        {"name": "viewport", "content": "width=device-width, initial-scale=1"},
        {"rel": "manifest", "href": "/assets/manifest.json"},
        {"name": "mobile-web-app-capable", "content": "yes"},
        {"name": "apple-mobile-web-app-capable", "content": "yes"},
        {"name": "apple-mobile-web-app-title", "content": "F1 Analyzer"},
        {"name": "description", "content": "Advanced Formula 1 telemetry and strategy analysis dashboard. Compare driver performance, track dominance, and get AI-powered race insights using FastF1 and Google Gemini."},
        {"property": "og:title", "content": "F1 Analyzer - Advanced Telemetry & AI Insights"},
        {"property": "og:description", "content": "Interactive F1 telemetry, strategy analysis, and Gemini AI insights. Compare laps, visualize track dominance, and analyze race pace."},
        {"property": "og:type", "content": "website"},
        {"property": "og:url", "content": PUBLIC_BASE_URL},
        {"property": "og:image", "content": f"{PUBLIC_BASE_URL}/assets/og-image.png"},
        {"name": "twitter:card", "content": "summary_large_image"},
        {"name": "twitter:site", "content": "@F1Analyzer"},
        {"name": "theme-color", "content": "#ff0000"}
    ]
)

# Inject Vercel Web Analytics script into the HTML head
app.index_string = '''
<!DOCTYPE html>
<html>
    <head>
        {%metas%}
        <title>{%title%}</title>
        {%favicon%}
        {%css%}
        <script defer src="https://cdn.vercel-insights.com/v1/script.js"></script>
    </head>
    <body>
        {%app_entry%}
        <footer>
            {%config%}
            {%scripts%}
            {%renderer%}
        </footer>
    </body>
</html>
'''

Compress(app.server)
server = app.server
server.config['SEND_FILE_MAX_AGE_DEFAULT'] = 31536000

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


@server.after_request
def _set_deployment_cache_headers(response):
    """Keep static payloads CDN-friendly without caching live Dash/API responses."""
    path = request.path or ''
    if path == '/service-worker.js':
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    elif path.startswith('/assets/') or path.startswith('/_dash-component-suites/'):
        response.headers['Cache-Control'] = 'public, max-age=31536000, immutable'
    elif path in ('/', '/m', '/m/') or path.startswith('/api/') or path in ('/health', '/healthz', '/warmup'):
        response.headers['Cache-Control'] = 'no-store'
    return response


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


@server.route('/m')
@server.route('/m/')
def mobile_entry():
    """Canonicalize the former mobile route to the single app URL."""
    suffix = f"?{request.query_string.decode('utf-8')}" if request.query_string else ""
    return redirect(f"/{suffix}", code=308)


@server.route('/service-worker.js')
def service_worker():
    """Serve the PWA service worker from the root scope."""
    return send_from_directory('assets', 'service-worker.js', mimetype='application/javascript', max_age=0)


def _api_bool(value, default=False):
    if value is None:
        return default
    return str(value).strip().lower() in ('1', 'true', 'yes', 'on')


def _api_session_args(source):
    try:
        year = int(source.get('year'))
    except (TypeError, ValueError):
        year = None
    race = source.get('race')
    session_name = source.get('session') or source.get('session_type')
    if not year or not race or not session_name:
        return None, jsonify({'error': 'year, race, and session are required'}), 400
    return (year, str(race), str(session_name)), None, None


@server.route('/api/session-summary')
def api_session_summary():
    args, error_response, status = _api_session_args(request.args)
    if error_response is not None:
        return error_response, status
    year, race, session_name = args
    try:
        session = data.load_session_summary(year, race, session_name, include_laps=False)
        drivers = data.get_driver_info(session)
        results = []
        if getattr(session, 'results', None) is not None and not session.results.empty:
            for _, row in session.results.iterrows():
                abbr = row.get('Abbreviation')
                if not isinstance(abbr, str) or len(abbr) != 3:
                    continue
                pos = row.get('Position')
                results.append({
                    'abbr': abbr,
                    'position': int(pos) if pd.notna(pos) else None,
                    'team': row.get('TeamName') if isinstance(row.get('TeamName'), str) else '',
                    'status': row.get('Status') if isinstance(row.get('Status'), str) else '',
                })
        return jsonify({
            'year': year,
            'race': race,
            'session': session_name,
            'drivers': drivers,
            'results': results[:24],
        })
    except Exception as exc:
        logging.warning("[api] session-summary failed: %s", exc)
        return jsonify({'error': str(exc)}), 502


@server.route('/api/preload-session', methods=['POST'])
def api_preload_session():
    payload = request.get_json(silent=True) or {}
    args, error_response, status = _api_session_args(payload)
    if error_response is not None:
        return error_response, status
    year, race, session_name = args
    kwargs = {
        'laps': _api_bool(payload.get('laps'), True),
        'telemetry': _api_bool(payload.get('telemetry'), False),
        'weather': _api_bool(payload.get('weather'), False),
        'messages': _api_bool(payload.get('messages'), False),
    }
    data.preload_session(year, race, session_name, **kwargs)
    return jsonify(data.get_preload_status(year, race, session_name, **kwargs)), 202


@server.route('/api/preload-status')
def api_preload_status():
    args, error_response, status = _api_session_args(request.args)
    if error_response is not None:
        return error_response, status
    year, race, session_name = args
    kwargs = {
        'laps': _api_bool(request.args.get('laps'), True),
        'telemetry': _api_bool(request.args.get('telemetry'), False),
        'weather': _api_bool(request.args.get('weather'), False),
        'messages': _api_bool(request.args.get('messages'), False),
    }
    return jsonify(data.get_preload_status(year, race, session_name, **kwargs))


@server.route('/api/perf')
def api_perf():
    if not _feedback_admin_authorized(request.query_string.decode('utf-8')):
        return jsonify({'error': 'admin token required'}), 403
    return jsonify({
        'perf': get_perf_snapshot(),
        'preload_jobs': data.get_preload_registry_snapshot(),
        'cache': data.get_cache_stats(),
    })


atexit.register(flush_ai_cache)
app.layout = app_layout
register_callbacks(app)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
