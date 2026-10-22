import logging
import os
import dash
import dash_bootstrap_components as dbc
from layout import app_layout
from callbacks import register_callbacks
from flask_compress import Compress
import threading
import atexit
from flask import jsonify, request, send_from_directory
from runtime import is_serverless, storage_scope

# Set global log level to WARNING
logging.basicConfig(level=logging.WARNING)
logging.getLogger('werkzeug').setLevel(logging.WARNING)
logging.getLogger('dash').setLevel(logging.WARNING)
logging.getLogger('flask').setLevel(logging.WARNING)
logging.getLogger('google.genai').setLevel(logging.WARNING)

PUBLIC_BASE_URL = os.getenv('PUBLIC_BASE_URL', '').rstrip('/')
# Both supported hosts expose the deployed revision through an environment
# variable. Keeping this in the liveness response makes a Render rollback or
# a Vercel preview straightforward to identify without exposing secrets.
APP_VERSION = (
    os.getenv('VERCEL_GIT_COMMIT_SHA')
    or os.getenv('RENDER_GIT_COMMIT')
    or 'local'
)[:12]

META_TAGS = [
    {"name": "viewport", "content": "width=device-width, initial-scale=1"},
    {"name": "mobile-web-app-capable", "content": "yes"},
    {"name": "apple-mobile-web-app-capable", "content": "yes"},
    {"name": "apple-mobile-web-app-title", "content": "F1 Analyzer"},
    {"name": "description", "content": "A technical Formula 1 analysis desk for telemetry, race pace, track position, and strategy."},
    {"property": "og:title", "content": "F1 Analyzer"},
    {"property": "og:description", "content": "Compare historical Formula 1 laps, race pace, strategy, and track position using OpenF1 timing data."},
    {"property": "og:type", "content": "website"},
    {"name": "theme-color", "content": "#0a0b0d"}
]

if PUBLIC_BASE_URL:
    META_TAGS.extend([
        {"property": "og:url", "content": PUBLIC_BASE_URL},
        {"property": "og:image", "content": f"{PUBLIC_BASE_URL}/assets/og-image.png"},
    ])

dash_app = dash.Dash(
    __name__,
    external_stylesheets=[dbc.themes.CYBORG, "https://use.fontawesome.com/releases/v5.15.4/css/all.css"],
    title="F1 Analyzer",
    update_title=None,
    suppress_callback_exceptions=True,
    assets_ignore='service-worker\\.js',
    meta_tags=META_TAGS
)

ANALYTICS_HEAD = ''
if os.getenv('ENABLE_VERCEL_ANALYTICS') == '1':
    ANALYTICS_HEAD = '''
        <script defer src="https://cdn.vercel-insights.com/v1/script.js"></script>
        <script>
            window.si = window.si || function () { (window.siq = window.siq || []).push(arguments); };
        </script>
        <script defer src="/_vercel/speed-insights/script.js"></script>
    '''

dash_app.index_string = '''
<!DOCTYPE html>
<html>
    <head>
        {%metas%}
        <title>{%title%}</title>
        <link rel="manifest" href="/assets/manifest.json">
        {%favicon%}
        {%css%}
        {analytics_head}
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
'''.replace('{analytics_head}', ANALYTICS_HEAD)

dash_app.renderer = '''
(function waitForDashRenderer() {
    // Dash 4 exposes DashRenderer as a script-level binding, not necessarily
    // as window.DashRenderer.  Using typeof works with both Dash 2/3 and 4.
    if (typeof DashRenderer !== 'undefined') {
        window.renderer = new DashRenderer();
        return;
    }
    window.setTimeout(waitForDashRenderer, 50);
}());
'''

Compress(dash_app.server)
server = dash_app.server
app = server
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
            from feedback import setup_feedback_storage

            setup_feedback_storage()
        finally:
            _RUNTIME_INIT_DONE = True


def _start_runtime_init_once():
    """Start lazy runtime initialization once per process."""
    global _RUNTIME_INIT_STARTED, _RUNTIME_INIT_DONE
    if _RUNTIME_INIT_STARTED or _RUNTIME_INIT_DONE:
        return
    if is_serverless():
        # Serverless runtimes should not rely on background work after a response.
        # Data and feedback modules still initialize their writable /tmp storage on demand.
        _RUNTIME_INIT_DONE = True
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
def _set_cache_headers(response):
    """Keep static payloads CDN-friendly without caching live Dash/API responses."""
    path = request.path or ''
    if path == '/service-worker.js':
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    elif path.startswith('/assets/') and path.endswith(('.css', '.js', '.json')):
        response.headers['Cache-Control'] = 'no-cache, max-age=0, must-revalidate'
    elif path.startswith('/assets/') or path.startswith('/_dash-component-suites/'):
        response.headers['Cache-Control'] = 'public, max-age=31536000, immutable'
    elif path in ('/', '/m', '/m/') or path.startswith('/api/') or path in ('/health', '/healthz', '/warmup'):
        response.headers['Cache-Control'] = 'no-store'
    return response


@server.route('/health', strict_slashes=False)
@server.route('/healthz', strict_slashes=False)
def healthz():
    """Cheap liveness endpoint for host health checks and deployment probes."""
    payload = {
        'status': 'ok',
        'version': APP_VERSION,
        'runtime': 'vercel' if is_serverless() else 'local',
        'filesystem_storage': storage_scope(),
    }
    # Opt-in only: host health checks should stay local and cheap, while a
    # deployment investigation can verify the Upstash path without exposing
    # its URL, token, or cached data.
    if request.args.get('cache') == '1':
        from shared_cache import probe
        payload['shared_cache'] = probe()
    return jsonify(payload), 200


@server.route('/warmup')
def warmup():
    """Prime local runtime state when a persistent process is available."""
    _start_runtime_init_once()
    return jsonify({
        'status': 'direct-load' if is_serverless() else 'warming',
        'message': (
            'Serverless instances load historical OpenF1 data on demand.' if is_serverless()
            else 'Local runtime initialization has started.'
        ),
    }), 200


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
    import pandas as pd
    import data

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
                abbr = row.get('abbreviation')
                if not isinstance(abbr, str) or len(abbr) != 3:
                    continue
                pos = row.get('position')
                results.append({
                    'abbr': abbr,
                    'position': int(pos) if pd.notna(pos) else None,
                    'team': row.get('team_name') if isinstance(row.get('team_name'), str) else '',
                    'status': row.get('status') if isinstance(row.get('status'), str) else '',
                    'source': row.get('source') if isinstance(row.get('source'), str) else '',
                })
        return jsonify({
            'year': year,
            'race': race,
            'session': session_name,
            'drivers': drivers,
            'results': results[:24],
        })
    except Exception as exc:
        logging.warning("[api] session-summary failed error_type=%s", type(exc).__name__)
        return jsonify({'error': 'Session data is temporarily unavailable.'}), 502


@server.route('/api/preload-session', methods=['POST'])
def api_preload_session():
    import data

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
    import data

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
    import data
    from perf_monitor import get_perf_snapshot
    from ui_utils import _feedback_admin_authorized

    if not _feedback_admin_authorized():
        return jsonify({'error': 'admin token required'}), 403
    return jsonify({
        'perf': get_perf_snapshot(),
        'preload_jobs': data.get_preload_registry_snapshot(),
        'cache': data.get_cache_stats(),
    })


def _flush_ai_cache_on_exit():
    from ai_cache import flush_ai_cache
    flush_ai_cache()


atexit.register(_flush_ai_cache_on_exit)
dash_app.layout = app_layout
register_callbacks(dash_app)

if __name__ == '__main__':
    dash_app.run(host='0.0.0.0', port=8000)
