import dash
from dash import dcc, html
import dash_bootstrap_components as dbc
from dash.dependencies import Input, Output, State
import plotly.graph_objects as go
import fastf1
import fastf1.plotting
import os
import pandas as pd

# --- 1. SETUP F1 CACHE ---
cache_dir = 'f1_cache'
if not os.path.exists(cache_dir):
    os.makedirs(cache_dir)
fastf1.Cache.enable_cache(cache_dir)

app = dash.Dash(__name__, external_stylesheets=[dbc.themes.CYBORG])

# --- 2. THE CONTROL PANEL (SIDEBAR) ---
sidebar = html.Div([
    html.H2("F1 AI Data", className="display-6", style={"fontSize": "1.5rem"}),
    html.Hr(),

    dbc.Label("Year", style={"fontSize": "0.9rem"}),
    dcc.Dropdown(id='year-dropdown', options=[{'label': str(y), 'value': y} for y in range(2018, 2027)], value=2024,
                 style={'color': 'black', 'fontSize': '0.9rem'}),
    html.Br(),

    dbc.Label("Grand Prix", style={"fontSize": "0.9rem"}),
    # Options populated dynamically by Callback 1!
    dcc.Dropdown(id='race-dropdown', style={'color': 'black', 'fontSize': '0.9rem'}),
    html.Br(),

    dbc.Label("Session", style={"fontSize": "0.9rem"}),
    # Options populated dynamically by Callback 2!
    dcc.Dropdown(id='session-dropdown', style={'color': 'black', 'fontSize': '0.9rem'}),
    html.Br(),

    dbc.Label("Driver 1", style={"fontSize": "0.9rem"}),
    # Options populated dynamically by Callback 3!
    dcc.Dropdown(id='driver1-dropdown', style={'color': 'black', 'fontSize': '0.9rem'}),
    html.Br(),

    dbc.Label("Driver 2", style={"fontSize": "0.9rem"}),
    dcc.Dropdown(id='driver2-dropdown', style={'color': 'black', 'fontSize': '0.9rem'}),
    html.Br(),
    html.Hr(),

    dbc.Label("Telemetry Metric", style={"fontSize": "0.9rem"}),
    dcc.Dropdown(
        id='metric-dropdown',
        options=[
            {'label': 'Speed (km/h)', 'value': 'Speed'}, {'label': 'Throttle (%)', 'value': 'Throttle'},
            {'label': 'Brake (%)', 'value': 'Brake'}, {'label': 'Gear', 'value': 'nGear'},
            {'label': 'Engine RPM', 'value': 'RPM'}
        ],
        value='Speed', style={'color': 'black', 'fontSize': '0.9rem'}
    ),

], style={"padding": "1rem", "background-color": "#111111", "height": "100vh", "overflowY": "auto"})

# --- 3. THE MAIN VIEWING AREA ---
content = html.Div([
    html.H3("Session Telemetry Analysis", className="text-center mt-2", id='main-title'),
    html.Hr(),

    dcc.Tabs([
        dcc.Tab(label='Telemetry Traces', children=[
            dcc.Loading(type="default", color="#ff0000", children=dcc.Graph(id='speed-graph', style={'height': '75vh'}))
        ], style={'backgroundColor': '#222', 'color': 'white'},
                selected_style={'backgroundColor': '#ff0000', 'color': 'white'}),

        dcc.Tab(label='Track Dominance Map', children=[
            dcc.Loading(type="default", color="#ff0000",
                        children=dcc.Graph(id='dominance-graph', style={'height': '75vh'}))
        ], style={'backgroundColor': '#222', 'color': 'white'},
                selected_style={'backgroundColor': '#ff0000', 'color': 'white'}),

        dcc.Tab(label='3D Elevation Map', children=[
            dcc.Loading(type="default", color="#ff0000", children=dcc.Graph(id='3d-graph', style={'height': '75vh'}))
        ], style={'backgroundColor': '#222', 'color': 'white'},
                selected_style={'backgroundColor': '#ff0000', 'color': 'white'})
    ])
], style={"padding": "1rem"})

app.layout = dbc.Container([
    dbc.Row([dbc.Col(sidebar, width=2), dbc.Col(content, width=10)])
], fluid=True, style={"padding": "0px"})


# ==============================================================================
# --- 4. THE CASCADING CALLBACKS (The Ripple Effect) ---
# ==============================================================================

# Callback 1: Year -> Populates Races
@app.callback([Output('race-dropdown', 'options'), Output('race-dropdown', 'value')], [Input('year-dropdown', 'value')]
              )
def update_races(year):
    if not year: return dash.no_update, dash.no_update
    schedule = fastf1.get_event_schedule(year)
    schedule = schedule[schedule['EventFormat'] != 'testing']
    races = schedule['EventName'].tolist()
    options = [{'label': r.replace("Grand Prix", "GP"), 'value': r} for r in races]
    return options, races[0] if races else None


# Callback 2: Race -> Populates Actual Sessions for that specific weekend
@app.callback([Output('session-dropdown', 'options'), Output('session-dropdown', 'value')],
              [Input('race-dropdown', 'value')], [State('year-dropdown', 'value')]
              )
def update_sessions(race, year):
    if not race or not year: return dash.no_update, dash.no_update
    event = fastf1.get_event(year, race)

    options = []
    # Every F1 event has up to 5 sessions. This extracts their exact names (e.g. "Sprint Qualifying")
    for i in range(1, 6):
        s_name = event[f'Session{i}']
        if pd.notna(s_name) and s_name:
            options.append({'label': s_name, 'value': s_name})

    # Default to Qualifying if it exists, otherwise the last session (Race)
    val = options[-1]['value'] if options else None
    for opt in options:
        if opt['label'] == 'Qualifying':
            val = opt['value']

    return options, val


# Callback 3: Session -> Populates Drivers who ACTUALLY drove in that session
@app.callback([Output('driver1-dropdown', 'options'), Output('driver1-dropdown', 'value'),
               Output('driver2-dropdown', 'options'), Output('driver2-dropdown', 'value')],
              [Input('session-dropdown', 'value')], [State('race-dropdown', 'value'), State('year-dropdown', 'value')]
              )
def update_drivers(session_name, race, year):
    if not session_name or not race or not year: return dash.no_update, dash.no_update, dash.no_update, dash.no_update

    try:
        session = fastf1.get_session(year, race, session_name)
        # We load ONLY the results, turning off telemetry/weather to make this lightning fast (1-2 seconds)
        session.load(telemetry=False, laps=False, weather=False, messages=False)

        results = session.results['Abbreviation'].dropna().tolist()
        valid_drivers = [d for d in results if isinstance(d, str) and len(d) == 3]

        # Sort options alphabetically for the dropdown list
        options = [{'label': d, 'value': d} for d in sorted(valid_drivers)]

        # Smart Default: Pick the 1st and 2nd place drivers from the results!
        val1 = valid_drivers[0] if len(valid_drivers) > 0 else None
        val2 = valid_drivers[1] if len(valid_drivers) > 1 else val1

        return options, val1, options, val2
    except Exception as e:
        return [], None, [], None


# Callback 4: Update All Graphs (Only fires when everything is selected!)
@app.callback([Output('speed-graph', 'figure'), Output('dominance-graph', 'figure'), Output('3d-graph', 'figure'),
               Output('main-title', 'children')],
              [Input('driver1-dropdown', 'value'), Input('driver2-dropdown', 'value'),
               Input('metric-dropdown', 'value')],
              [State('session-dropdown', 'value'), State('race-dropdown', 'value'), State('year-dropdown', 'value')]
              )
def update_graphs(driver1, driver2, metric, session_type, race, year):
    empty_fig = go.Figure().update_layout(template='plotly_dark')
    if not all([year, race, session_type, driver1, driver2, metric]):
        return empty_fig, empty_fig, empty_fig, "Select parameters to load data..."

    try:
        session = fastf1.get_session(year, race, session_type)
        session.load(telemetry=True, weather=False, messages=False)

        lap1 = session.laps.pick_drivers(driver1).pick_fastest()
        lap2 = session.laps.pick_drivers(driver2).pick_fastest()

        if pd.isna(lap1['LapTime']) or pd.isna(lap2['LapTime']):
            raise ValueError("One or both drivers did not set a valid lap.")

        tel1 = lap1.get_telemetry().add_distance()
        tel2 = lap2.get_telemetry().add_distance()
        t1 = lap1['LapTime'].total_seconds()
        t2 = lap2['LapTime'].total_seconds()

        try:
            c1 = fastf1.plotting.get_driver_color(driver1, session)
            c2 = fastf1.plotting.get_driver_color(driver2, session)
        except:
            c1, c2 = '#00ffff', '#ff00ff'

        if not c1.startswith('#'): c1 = f"#{c1}"
        if not c2.startswith('#'): c2 = f"#{c2}"
        if c1.lower() == c2.lower(): c2 = '#ffffff' if c1.lower() != '#ffffff' else '#ffff00'

        if t1 <= t2:
            fast_driver, fast_tel, fast_c, fast_t = driver1, tel1, c1, t1
            slow_driver, slow_tel, slow_c, slow_t = driver2, tel2, c2, t2
        else:
            fast_driver, fast_tel, fast_c, fast_t = driver2, tel2, c2, t2
            slow_driver, slow_tel, slow_c, slow_t = driver1, tel1, c1, t1

        # ==========================================
        # GRAPH 1: TELEMETRY TRACE
        # ==========================================
        fig_speed = go.Figure()
        fig_speed.add_trace(
            go.Scatter(x=fast_tel['Distance'], y=fast_tel[metric], mode='lines', name=f'{fast_driver} ({fast_t:.3f}s)',
                       line=dict(color=fast_c)))
        fig_speed.add_trace(
            go.Scatter(x=slow_tel['Distance'], y=slow_tel[metric], mode='lines', name=f'{slow_driver} ({slow_t:.3f}s)',
                       line=dict(color=slow_c)))

        y_labels = {'Speed': 'Speed (km/h)', 'Throttle': 'Throttle (%)', 'Brake': 'Brake Pressure (%)', 'nGear': 'Gear',
                    'RPM': 'Engine RPM'}
        fig_speed.update_layout(title=f'{metric} Trace', xaxis_title='Distance along track (meters)',
                                yaxis_title=y_labels.get(metric, metric), template='plotly_dark', hovermode='x unified',
                                margin=dict(l=40, r=40, t=40, b=40),
                                legend=dict(yanchor="top", y=0.99, xanchor="right", x=0.99))

        # ==========================================
        # GRAPH 2: DOMINANCE MAP
        # ==========================================
        num_minisectors = 15
        sector_length = max(tel1['Distance'].max(), tel2['Distance'].max()) / num_minisectors
        tel1['MiniSector'] = (tel1['Distance'] // sector_length).astype(int)
        tel2['MiniSector'] = (tel2['Distance'] // sector_length).astype(int)

        v1_avg = tel1.groupby('MiniSector')['Speed'].mean()
        v2_avg = tel2.groupby('MiniSector')['Speed'].mean()

        winner_list = [driver1 if v1_avg.get(i, 0) > v2_avg.get(i, 0) else driver2 for i in range(num_minisectors + 1)]
        fig_map = go.Figure()

        fig_map.add_trace(go.Scatter(x=[None], y=[None], mode='lines', line=dict(color=fast_c, width=10),
                                     name=f'{fast_driver} Faster ({fast_t:.3f}s)'))
        fig_map.add_trace(go.Scatter(x=[None], y=[None], mode='lines', line=dict(color=slow_c, width=10),
                                     name=f'{slow_driver} Faster ({slow_t:.3f}s)'))

        for ms in range(num_minisectors):
            sector_data = tel1[tel1['MiniSector'] == ms]
            if sector_data.empty: continue
            next_sector_data = tel1[tel1['MiniSector'] == ms + 1]
            if not next_sector_data.empty: sector_data = pd.concat([sector_data, next_sector_data.iloc[[0]]])
            winner = winner_list[ms]
            color = c1 if winner == driver1 else c2
            fig_map.add_trace(
                go.Scatter(x=sector_data['X'], y=sector_data['Y'], mode='lines', line=dict(color=color, width=10),
                           showlegend=False, hoverinfo='skip'))

        fig_map.update_layout(title="Track Dominance (15 Mini-Sectors)", template='plotly_dark',
                              yaxis=dict(scaleanchor="x", scaleratio=1, visible=False), xaxis=dict(visible=False),
                              margin=dict(l=0, r=0, t=40, b=0),
                              legend=dict(yanchor="top", y=0.99, xanchor="right", x=0.99))

        # ==========================================
        # GRAPH 3: 3D ELEVATION MAP
        # ==========================================
        x_range = fast_tel['X'].max() - fast_tel['X'].min()
        y_range = fast_tel['Y'].max() - fast_tel['Y'].min()
        max_range = max(x_range, y_range)
        x_ratio, y_ratio = x_range / max_range, y_range / max_range

        fig_3d = go.Figure()
        fig_3d.add_trace(go.Scatter3d(x=fast_tel['X'], y=fast_tel['Y'], z=fast_tel['Z'], mode='lines',
                                      line=dict(color=fast_tel['Speed'], colorscale='Turbo', width=6,
                                                colorbar=dict(title='Speed (km/h)', x=0.9)),
                                      name=f'{fast_driver} Path'))
        fig_3d.add_trace(go.Scatter3d(x=slow_tel['X'], y=slow_tel['Y'], z=slow_tel['Z'], mode='lines',
                                      line=dict(color=slow_c, width=4), name=f'{slow_driver} Path (Click to view)',
                                      visible='legendonly'))

        fig_3d.update_layout(title=f"3D Track Elevation & Speed Profile", template='plotly_dark',
                             scene=dict(xaxis=dict(visible=False), yaxis=dict(visible=False), zaxis=dict(visible=False),
                                        aspectmode='manual', aspectratio=dict(x=x_ratio, y=y_ratio, z=0.15)),
                             margin=dict(l=0, r=0, t=40, b=0),
                             legend=dict(yanchor="top", y=0.99, xanchor="left", x=0.01))

        title_text = f"{year} {race} | {session_type} | {fast_driver} vs {slow_driver}"
        return fig_speed, fig_map, fig_3d, title_text

    except Exception as e:
        print(f"Graph Error: {e}")
        err_fig = go.Figure().update_layout(title=f"Error Loading Telemetry Data", template='plotly_dark')
        return err_fig, err_fig, err_fig, "Data Unavailable"


if __name__ == '__main__':
    app.run(debug=True)