import os
import dash
import dash_bootstrap_components as dbc
from layout import app_layout
from callbacks import register_callbacks
import data

app = dash.Dash(__name__, external_stylesheets=[dbc.themes.CYBORG])
server = app.server  # Expose Flask server for gunicorn

data.setup_cache()
app.layout = app_layout
register_callbacks(app)

if __name__ == '__main__':
    data.clear_old_cache()
    port = int(os.environ.get('PORT', 8050))
    app.run(host='0.0.0.0', port=port)
