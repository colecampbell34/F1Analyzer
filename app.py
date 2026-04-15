import dash
import dash_bootstrap_components as dbc
from layout import app_layout
from callbacks import register_callbacks
import data
from feedback import setup_feedback_storage

app = dash.Dash(
    __name__,
    external_stylesheets=[dbc.themes.CYBORG],
    title="F1 Analyzer",
    update_title="Loading...",
    suppress_callback_exceptions=True
)

data.setup_cache()
setup_feedback_storage()
app.layout = app_layout
register_callbacks(app)

server = app.server

if __name__ == '__main__':
    data.clear_old_cache()
    app.run(host='0.0.0.0', port=5000)
