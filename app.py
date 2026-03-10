import dash
from dash import dcc, html
import dash_bootstrap_components as dbc
from dash.dependencies import Input, Output
import plotly.graph_objects as go
import fastf1
import os

# --- 1. SETUP F1 CACHE ---
cache_dir = 'f1_cache'
if not os.path.exists(cache_dir):
    os.makedirs(cache_dir)
fastf1.Cache.enable_cache(cache_dir)

# Initialize the app with a dark F1-style theme
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.CYBORG])

# List of common driver abbreviations for our dropdowns
driver_options = [{'label': d, 'value': d} for d in ['VER', 'NOR', 'LEC', 'SAI', 'HAM', 'RUS', 'PIA', 'ALO', 'PER']]

# --- 2. THE CONTROL PANEL (SIDEBAR) ---
sidebar = html.Div([
    html.H2("F1 AI Data", className="display-6"),
    html.Hr(),
    html.P("Select session parameters:", className="lead"),

    dbc.Label("Year"),
    dcc.Dropdown(
        id='year-dropdown',
        options=[{'label': str(y), 'value': y} for y in range(2023, 2027)],
        value=2024,
        style={'color': 'black'}
    ),
    html.Br(),

    dbc.Label("Grand Prix"),
    dcc.Dropdown(
        id='race-dropdown',
        options=[
            {'label': 'Bahrain', 'value': 'Bahrain'},
            {'label': 'Saudi Arabia', 'value': 'Saudi Arabia'},
            {'label': 'Australia', 'value': 'Australia'},
            {'label': 'Japan', 'value': 'Japan'}
        ],
        value='Australia',
        style={'color': 'black'}
    ),
    html.Br(),

    # NEW: Driver Dropdowns
    dbc.Label("Driver 1"),
    dcc.Dropdown(
        id='driver1-dropdown',
        options=driver_options,
        value='VER',
        style={'color': 'black'}
    ),
    html.Br(),

    dbc.Label("Driver 2"),
    dcc.Dropdown(
        id='driver2-dropdown',
        options=driver_options,
        value='NOR',
        style={'color': 'black'}
    ),
], style={"padding": "2rem", "background-color": "#111111", "height": "100vh"})

# --- 3. THE MAIN VIEWING AREA ---
content = html.Div([
    html.H3("Qualifying Telemetry Analysis", className="text-center mt-3"),
    html.Hr(),

    # NEW: The Loading Wrapper!
    # This automatically shows a spinner when the graph is updating.
    dcc.Loading(
        id="loading-graph",
        type="default",
        color="#ff0000",  # F1 Red Spinner
        children=dcc.Graph(id='telemetry-graph')
    )
], style={"padding": "2rem"})

# --- 4. APP LAYOUT ---
app.layout = dbc.Container([
    dbc.Row([
        dbc.Col(sidebar, width=3),
        dbc.Col(content, width=9)
    ])
], fluid=True, style={"padding": "0px"})


# --- 5. THE CALLBACK (THE BRAINS) ---
@app.callback(
    Output('telemetry-graph', 'figure'), [Input('year-dropdown', 'value'),
                                          Input('race-dropdown', 'value'),
                                          Input('driver1-dropdown', 'value'),
                                          Input('driver2-dropdown', 'value')]
)
def update_graph(year, race, driver1, driver2):
    # If the user clears a dropdown, don't try to run the code
    if not year or not race or not driver1 or not driver2:
        return go.Figure()

    try:
        # 1. Load the specific session based on dropdown inputs
        session = fastf1.get_session(year, race, 'Q')
        # We only need telemetry right now, so we turn off weather/messages to speed up loading
        session.load(telemetry=True, weather=False, messages=False)

        # 2. Extract laps for the two chosen drivers
        lap1 = session.laps.pick_driver(driver1).pick_fastest()
        lap2 = session.laps.pick_driver(driver2).pick_fastest()

        # 3. Extract telemetry
        tel1 = lap1.get_telemetry().add_distance()
        tel2 = lap2.get_telemetry().add_distance()

        # 4. Build the Plotly figure
        fig = go.Figure()

        # Driver 1 Trace (Cyan)
        fig.add_trace(go.Scatter(
            x=tel1['Distance'], y=tel1['Speed'], mode='lines',
            name=f'{driver1} ({lap1["LapTime"].total_seconds():.3f}s)',
            line=dict(color='#00ffff')
        ))

        # Driver 2 Trace (Magenta)
        fig.add_trace(go.Scatter(
            x=tel2['Distance'], y=tel2['Speed'], mode='lines',
            name=f'{driver2} ({lap2["LapTime"].total_seconds():.3f}s)',
            line=dict(color='#ff00ff')
        ))

        # Update layout styling
        fig.update_layout(
            title=f'{driver1} vs {driver2} - {year} {race} GP (Speed Trace)',
            xaxis_title='Distance along track (meters)',
            yaxis_title='Speed (km/h)',
            template='plotly_dark',
            hovermode='x unified',
            margin=dict(l=40, r=40, t=60, b=40)
        )

        return fig

    except Exception as e:
        # If a driver didn't race, or data is missing, return an empty graph with an error title
        fig = go.Figure()
        fig.update_layout(
            title=f"Error loading data: Ensure both drivers participated in {year} {race} Q.",
            template='plotly_dark'
        )
        return fig


# --- 6. RUN THE APP ---
if __name__ == '__main__':
    app.run(debug=False)