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

app = dash.Dash(
    __name__,
    external_stylesheets=[dbc.themes.CYBORG],
    title="F1 Analyzer",
    update_title="Loading...",
    suppress_callback_exceptions=True
)

Compress(app.server)
server = app.server

data.setup_cache()
threading.Thread(target=data.maybe_prune_cache, daemon=True).start()
setup_feedback_storage()
atexit.register(flush_ai_cache)
app.layout = app_layout
register_callbacks(app)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
