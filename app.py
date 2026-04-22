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
from flask import jsonify

app = dash.Dash(
    __name__,
    external_stylesheets=[dbc.themes.CYBORG],
    title="F1 Analyzer",
    update_title="Loading...",
    suppress_callback_exceptions=True
)

Compress(app.server)
server = app.server

_RUNTIME_INIT_LOCK = threading.Lock()
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


@server.before_request
def _ensure_runtime_initialized():
    """Kick off deferred runtime initialization once."""
    if _RUNTIME_INIT_DONE:
        return
    threading.Thread(target=_init_runtime_background, daemon=True).start()


@server.route('/health', strict_slashes=False)
@server.route('/healthz', strict_slashes=False)
def healthz():
    """Cheap liveness endpoint for host health checks."""
    return jsonify({'status': 'ok'}), 200


@server.route('/warmup')
def warmup():
    """Prime lightweight caches to reduce cold-start request latency."""
    threading.Thread(target=_init_runtime_background, daemon=True).start()
    threading.Thread(target=data.get_event_schedule_cached, args=(datetime.now().year,), daemon=True).start()
    return jsonify({'status': 'warming'}), 200


atexit.register(flush_ai_cache)
app.layout = app_layout
register_callbacks(app)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
