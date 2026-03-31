import dash
import dash_bootstrap_components as dbc
from layout import app_layout
from callbacks import register_callbacks
import data

app = dash.Dash(__name__, external_stylesheets=[dbc.themes.CYBORG])

data.setup_cache()
app.layout = app_layout
register_callbacks(app)

if __name__ == '__main__':
    data.clear_old_cache()
    app.run(port=8050)
