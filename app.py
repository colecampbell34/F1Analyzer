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
import time

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
        start = time.perf_counter()
        try:
            data.setup_cache()
            threading.Thread(target=data.maybe_prune_cache, daemon=True).start()
            setup_feedback_storage()
        finally:
            _RUNTIME_INIT_DONE = True
            print(f"[startup] deferred_init_ms={(time.perf_counter() - start) * 1000:.1f}")


@server.before_request
def _ensure_runtime_initialized():
    """Kick off deferred runtime initialization once."""
    if _RUNTIME_INIT_DONE:
        return
    threading.Thread(target=_init_runtime_background, daemon=True).start()


atexit.register(flush_ai_cache)
app.layout = app_layout
register_callbacks(app)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
