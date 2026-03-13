import dash
from dash import dcc, html
import dash_bootstrap_components as dbc
from dash.dependencies import Input, Output, State
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import fastf1
import fastf1.plotting
import os
import pandas as pd
import shutil

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
    dcc.Dropdown(id='year-dropdown', options=[{'label': str(y), 'value': y} for y in range(2018, 2027)], value=2026,
                 style={'color': 'black', 'fontSize': '0.9rem'}),
    html.Br(),

    dbc.Label("Grand Prix", style={"fontSize": "0.9rem"}),
    dcc.Dropdown(id='race-dropdown', style={'color': 'black', 'fontSize': '0.9rem'}),
    html.Br(),

    dbc.Label("Session", style={"fontSize": "0.9rem"}),
    dcc.Dropdown(id='session-dropdown', style={'color': 'black', 'fontSize': '0.9rem'}),
    html.Br(),

    dbc.Label("Driver 1", style={"fontSize": "0.9rem"}),
    dcc.Dropdown(id='driver1-dropdown', style={'color': 'black', 'fontSize': '0.9rem'}),
    html.Br(),

    dbc.Label("Driver 2", style={"fontSize": "0.9rem"}),
    dcc.Dropdown(id='driver2-dropdown', style={'color': 'black', 'fontSize': '0.9rem'}),
    html.Br(),
    dbc.Label("Strategy Chart Filter", style={"fontSize": "0.9rem"}),
    dcc.Dropdown(
        id='pace-filter',
        options=[
            {'label': 'Racing Laps', 'value': 'racing'},
            {'label': 'All Laps', 'value': 'all'}
        ],
        value='racing', style={'color': 'black', 'fontSize': '0.9rem'}
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

        # TAB 2: The Merged 2D Dominance Map
        dcc.Tab(label='2D Track Dominance', children=[
            dcc.Loading(type="default", color="#ff0000",
                        children=dcc.Graph(id='2d-dominance-graph', style={'height': '75vh'}))
        ], style={'backgroundColor': '#222', 'color': 'white'},
                selected_style={'backgroundColor': '#ff0000', 'color': 'white'}),

        dcc.Tab(label='Strategy & Weather', children=[
            dcc.Loading(type="default", color="#ff0000",
                        children=dcc.Graph(id='strategy-graph', style={'height': '75vh'}))
        ], style={'backgroundColor': '#222', 'color': 'white'},
                selected_style={'backgroundColor': '#ff0000', 'color': 'white'})
    ])
], style={"padding": "1rem"})

app.layout = dbc.Container([
    dbc.Row([dbc.Col(sidebar, width=2), dbc.Col(content, width=10)])
], fluid=True, style={"padding": "0px"})


def _get_driver_colors(driver1, driver2, session):
    """Fetches driver colors and handles teammate color collisions."""
    try:
        c1 = fastf1.plotting.get_driver_color(driver1, session)
        c2 = fastf1.plotting.get_driver_color(driver2, session)
    except Exception:
        c1, c2 = '#00ffff', '#ff00ff'

    if not c1.startswith('#'): c1 = f"#{c1}"
    if not c2.startswith('#'): c2 = f"#{c2}"
    if c1.lower() == c2.lower():
        c2 = '#ffffff' if c1.lower() != '#ffffff' else '#ffff00'

    return c1, c2


def _sort_fastest_driver(d1, tel1, c1, lap1, d2, tel2, c2, lap2):
    """Compares lap times and returns (fast_data, slow_data) tuples to standardize plotting."""
    t1 = lap1['LapTime'].total_seconds()
    t2 = lap2['LapTime'].total_seconds()

    data1 = (d1, tel1, c1, t1, lap1)
    data2 = (d2, tel2, c2, t2, lap2)

    return (data1, data2) if t1 <= t2 else (data2, data1)


def _build_telemetry_fig(fast_data, slow_data):
    """Builds the 4-Row Telemetry Subplot (Delta, Speed, Throttle/Brake, Gear)."""
    fast_driver, fast_tel, fast_c, fast_t, fast_lap = fast_data
    slow_driver, slow_tel, slow_c, slow_t, slow_lap = slow_data

    delta_time, ref_tel, comp_tel = fastf1.utils.delta_time(fast_lap, slow_lap)

    fig = make_subplots(
        rows=4, cols=1, shared_xaxes=True, vertical_spacing=0.03,
        specs=[[{"secondary_y": False}], [{"secondary_y": False}], [{"secondary_y": True}], [{"secondary_y": False}]],
        row_heights=[0.15, 0.35, 0.25, 0.25]
    )

    # Row 1: Time Delta
    fig.add_trace(
        go.Scatter(x=ref_tel['Distance'], y=delta_time, mode='lines', name="Time Delta", line=dict(color='white')),
        row=1, col=1)
    fig.add_annotation(xref="paper", yref="y domain", x=0.94, y=1, text=f"{fast_driver} faster", showarrow=False,
                       xanchor="left")
    fig.add_annotation(xref="paper", yref="y domain", x=0.94, y=0, text=f"{slow_driver} faster", showarrow=False,
                       xanchor="left")

    # Row 2: Speed
    fig.add_trace(go.Scatter(x=fast_tel['Distance'], y=fast_tel['Speed'], mode='lines', name=f'{fast_driver} Speed',
                             line=dict(color=fast_c)), row=2, col=1)
    fig.add_trace(go.Scatter(x=slow_tel['Distance'], y=slow_tel['Speed'], mode='lines', name=f'{slow_driver} Speed',
                             line=dict(color=slow_c)), row=2, col=1)

    # Row 3: Throttle and Brake
    fig.add_trace(
        go.Scatter(x=fast_tel['Distance'], y=fast_tel['Throttle'], mode='lines', name=f'{fast_driver} Throttle',
                   line=dict(color=fast_c, dash='solid')), row=3, col=1, secondary_y=False)
    fig.add_trace(
        go.Scatter(x=slow_tel['Distance'], y=slow_tel['Throttle'], mode='lines', name=f'{slow_driver} Throttle',
                   line=dict(color=slow_c, dash='solid')), row=3, col=1, secondary_y=False)
    fig.add_trace(go.Scatter(x=fast_tel['Distance'], y=fast_tel['Brake'], mode='lines', name=f'{fast_driver} Brake',
                             line=dict(color=fast_c, dash='dot'), opacity=0.7), row=3, col=1, secondary_y=True)
    fig.add_trace(go.Scatter(x=slow_tel['Distance'], y=slow_tel['Brake'], mode='lines', name=f'{slow_driver} Brake',
                             line=dict(color=slow_c, dash='dot'), opacity=0.7), row=3, col=1, secondary_y=True)

    # Row 4: Gear
    fig.add_trace(go.Scatter(x=fast_tel['Distance'], y=fast_tel['nGear'], mode='lines', name=f'{fast_driver} Gear',
                             line=dict(color=fast_c)), row=4, col=1)
    fig.add_trace(go.Scatter(x=slow_tel['Distance'], y=slow_tel['nGear'], mode='lines', name=f'{slow_driver} Gear',
                             line=dict(color=slow_c)), row=4, col=1)

    fig.update_layout(
        title=f'Telemetry Traces: {fast_driver} ({fast_t:.3f}s) vs {slow_driver} ({slow_t:.3f}s)',
        template='plotly_dark', hovermode='x unified', margin=dict(l=40, r=40, t=80, b=40),
        legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="center", x=0.5)
    )

    fig.update_yaxes(title_text="Delta (s)", row=1, col=1)
    fig.update_yaxes(title_text="Speed (km/h)", row=2, col=1)
    fig.update_yaxes(title_text="Throttle (%)", row=3, col=1, secondary_y=False)
    fig.update_yaxes(title_text="Brake (%)", row=3, col=1, secondary_y=True, showgrid=False)
    fig.update_yaxes(title_text="Gear", row=4, col=1, tickvals=[1, 2, 3, 4, 5, 6, 7, 8])
    fig.update_xaxes(title_text="Distance along track (meters)", row=4, col=1)

    return fig


def _build_dominance_fig(driver1, driver2, c1, c2, tel1, tel2, fast_data, slow_data):
    """Builds the 2D Track Dominance Map colored by mini-sectors."""
    fast_driver, fast_tel, fast_c, fast_t, _ = fast_data
    slow_driver, _, slow_c, slow_t, _ = slow_data

    num_minisectors = 20
    sector_length = max(tel1['Distance'].max(), tel2['Distance'].max()) / num_minisectors
    tel1['MiniSector'] = (tel1['Distance'] // sector_length).astype(int)
    tel2['MiniSector'] = (tel2['Distance'] // sector_length).astype(int)

    v1_avg = tel1.groupby('MiniSector')['Speed'].mean()
    v2_avg = tel2.groupby('MiniSector')['Speed'].mean()
    winner_list = [driver1 if v1_avg.get(i, 0) > v2_avg.get(i, 0) else driver2 for i in range(num_minisectors + 1)]

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=[None], y=[None], mode='lines', line=dict(color=fast_c, width=6),
                             name=f'{fast_driver} Faster ({fast_t:.3f}s)'))
    fig.add_trace(go.Scatter(x=[None], y=[None], mode='lines', line=dict(color=slow_c, width=6),
                             name=f'{slow_driver} Faster ({slow_t:.3f}s)'))

    for ms in range(num_minisectors):
        sector_data = fast_tel[fast_tel['MiniSector'] == ms]
        if sector_data.empty: continue

        next_sector = fast_tel[fast_tel['MiniSector'] == ms + 1]
        if not next_sector.empty: sector_data = pd.concat([sector_data, next_sector.iloc[[0]]])

        winner = winner_list[ms]
        color = c1 if winner == driver1 else c2

        fig.add_trace(go.Scatter(
            x=sector_data['X'], y=sector_data['Y'], mode='lines',
            line=dict(color=color, width=8), showlegend=False, hoverinfo='skip'
        ))

    fig.update_layout(
        title="2D High-Res Track Dominance Map", template='plotly_dark',
        xaxis=dict(visible=False, scaleanchor="y", scaleratio=1), yaxis=dict(visible=False),
        margin=dict(l=40, r=40, t=60, b=40), legend=dict(yanchor="top", y=0.99, xanchor="left", x=0.01)
    )
    return fig


def _build_strategy_fig(session, pace_filter, driver1, driver2, c1, c2):
    """Builds the Race Pace, Pits, Tyres & Weather dual-axis strategy plot."""
    # 1. Fetch unfiltered laps
    unf_1 = session.laps.pick_drivers(driver1).reset_index(drop=True)
    unf_2 = session.laps.pick_drivers(driver2).reset_index(drop=True)

    # 2. Apply Filters
    if pace_filter == 'racing':
        all_laps1 = unf_1.pick_wo_box().pick_track_status('1').loc[unf_1['LapNumber'] > 1].reset_index(drop=True)
        all_laps2 = unf_2.pick_wo_box().pick_track_status('1').loc[unf_2['LapNumber'] > 1].reset_index(drop=True)
    else:
        all_laps1, all_laps2 = unf_1, unf_2

    # 3. Calculate seconds, fallback for red flags (NaT)
    for laps_df in [all_laps1, all_laps2]:
        laps_df['LapTime_Sec'] = laps_df['LapTime'].dt.total_seconds()
        laps_df['LapTime_Sec'] = laps_df['LapTime_Sec'].fillna(
            (laps_df['Time'] - laps_df['LapStartTime']).dt.total_seconds())

    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.05,
        row_heights=[0.75, 0.25], subplot_titles=("Race Pace", "Track Temperature (°C)")
    )

    comp_colors = {'SOFT': '#ff3333', 'MEDIUM': '#ffff00', 'HARD': '#ffffff', 'INTERMEDIATE': '#00ff00',
                   'WET': '#0099ff'}
    comp_drawn = set()

    # 4. Plot Pace & Tyres
    for lap_data, drv, col, unf in [(all_laps1, driver1, c1, unf_1), (all_laps2, driver2, c2, unf_2)]:
        if pace_filter == 'racing':
            if 'Compound' in lap_data.columns:
                comp_drawn.update(lap_data['Compound'].dropna().unique())
                for comp in lap_data['Compound'].dropna().unique():
                    comp_subset = lap_data[lap_data['Compound'] == comp].sort_values(by='LapNumber')
                    fig.add_trace(go.Scatter(
                        x=comp_subset['LapNumber'], y=comp_subset['LapTime_Sec'], mode='lines+markers',
                        name=f'{drv} {comp}', line=dict(color=col, width=2),
                        marker=dict(color=comp_colors.get(comp, 'grey'), size=10, symbol='circle', line=dict(width=0)),
                        showlegend=False
                    ), row=1, col=1)

                    # 2. Draw the Vertical "Pit Window" Line
                    # We check `stint < max_stint` so we don't draw a line at the very end of the race
                    if stint < max_stint:
                        last_lap = stint_subset['LapNumber'].max()
                        fig.add_vline(
                            x=last_lap,
                            line_width=1.5,
                            line_dash="dot",
                            line_color=col,
                            opacity=0.6,
                            row='all',
                            col='all'
                        )
        else:
            fig.add_trace(go.Scatter(
                x=lap_data['LapNumber'], y=lap_data['LapTime_Sec'], mode='markers',
                name=drv, marker=dict(color=col, size=10, symbol='circle', line=dict(width=0)),
                showlegend=False
            ), row=1, col=1)

        # Plot Pit Stops
        if pace_filter == 'all':
            pits = unf[unf['PitOutTime'].notna()]['LapNumber']
            valid_pits = lap_data[lap_data['LapNumber'].isin(pits)]
            fig.add_trace(go.Scatter(
                x=valid_pits['LapNumber'], y=valid_pits['LapTime_Sec'], mode='markers',
                marker=dict(symbol='triangle-up', size=16, color='white', line=dict(color=col, width=2)),
                name=f'{drv} Pit', showlegend=False
            ), row=1, col=1)

    # 5. Overlay SC/VSC/Red Flag lines (If looking at 'all' laps)
    if pace_filter == 'all':
        sc_laps, vsc_laps, red_laps = set(), set(), set()
        for unf in [unf_1, unf_2]:
            sc_laps.update(unf[unf['TrackStatus'].astype(str).str.contains('4', na=False)]['LapNumber'].tolist())
            vsc_laps.update(unf[unf['TrackStatus'].astype(str).str.contains('6', na=False)]['LapNumber'].tolist())
            red_laps.update(unf[unf['TrackStatus'].astype(str).str.contains('5', na=False)]['LapNumber'].tolist())

        lines = [(sc_laps, 'orange', 'SC / YF'), (vsc_laps, 'yellow', 'VSC'), (red_laps, 'red', 'Red Flag')]
        for laps, color, name in lines:
            for lap in laps:
                fig.add_vline(x=lap, line_width=2, line_dash="dash", line_color=color, opacity=0.5, row='all',
                              col='all')
            if laps:
                fig.add_trace(go.Scatter(x=[None], y=[None], mode='lines', line=dict(color=color, dash='dash', width=2),
                                         name=name, legend='legend'), row=1, col=1)

        # General Legend additions
        fig.add_trace(go.Scatter(x=[None], y=[None], mode='markers', name='Pit Stop',
                                 marker=dict(symbol='triangle-up', size=14, color='white',
                                             line=dict(color='black', width=1)), legend='legend'), row=1, col=1)
        for drv, col in [(driver1, c1), (driver2, c2)]:
            fig.add_trace(go.Scatter(x=[None], y=[None], mode='markers', name=drv,
                                     marker=dict(color=col, size=10),
                                     legend='legend'), row=1, col=1)
    else:
        for drv, col in [(driver1, c1), (driver2, c2)]:
            fig.add_trace(
                go.Scatter(x=[None], y=[None], mode='lines', name=drv,
                           line=dict(color=col, width=2),
                           legend='legend'), row=1, col=1)
        for comp in comp_drawn:
            if comp in comp_colors:
                fig.add_trace(go.Scatter(x=[None], y=[None], mode='markers', name=comp,
                                         marker=dict(color=comp_colors[comp], size=10),
                                         legend='legend'), row=1, col=1)

    # 6. Weather & Rain Overlay
    weather_data = session.weather_data
    if not weather_data.empty and not all_laps1.empty:
        track_temps, lap_nums, rain_laps = [], [], set()
        for _, lap in all_laps1.iterrows():
            idx = (weather_data['Time'] - lap['Time']).abs().idxmin()
            track_temps.append(weather_data.loc[idx, 'TrackTemp'])
            lap_nums.append(lap['LapNumber'])
            if weather_data.loc[idx, 'Rainfall']:
                rain_laps.add(lap['LapNumber'])

        fig.add_trace(go.Scatter(
            x=lap_nums, y=track_temps, mode='lines+markers', name='Track Temp (°C)',
            line=dict(color='white', width=2), marker=dict(size=4), showlegend=False
        ), row=2, col=1)

        for lap in rain_laps:
            fig.add_vrect(x0=lap - 0.5, x1=lap + 0.5, fillcolor="blue", opacity=0.2, layer="below", line_width=0,
                          row='all', col='all')

        if rain_laps:
            fig.add_trace(go.Scatter(x=[None], y=[None], mode='markers',
                                     marker=dict(color='blue', opacity=0.5, symbol='square', size=15), name='Rain',
                                     legend='legend'), row=1, col=1)

    fig.update_layout(
        title="Strategy & Weather", template='plotly_dark', hovermode='x unified', margin=dict(l=40, r=40, t=60, b=40),
        legend=dict(title=dict(text="Legend"), yanchor="top", y=1, xanchor="left", x=1.02, bgcolor="rgba(0,0,0,0)")
    )
    fig.update_xaxes(title_text="Lap Number", row=2, col=1)
    fig.update_yaxes(title_text="Pace (s)", row=1, col=1)
    fig.update_yaxes(title_text="Temp (°C)", row=2, col=1)

    return fig


@app.callback([Output('race-dropdown', 'options'), Output('race-dropdown', 'value')], [Input('year-dropdown', 'value')])
def update_races(year):
    if not year: return dash.no_update, dash.no_update
    schedule = fastf1.get_event_schedule(year)
    schedule = schedule[schedule['EventFormat'] != 'testing']
    races = schedule['EventName'].tolist()
    return [{'label': r.replace("Grand Prix", "GP"), 'value': r} for r in races], races[0] if races else None


@app.callback([Output('session-dropdown', 'options'), Output('session-dropdown', 'value')],
              [Input('race-dropdown', 'value')], [State('year-dropdown', 'value')])
def update_sessions(race, year):
    if not race or not year: return dash.no_update, dash.no_update
    event = fastf1.get_event(year, race)
    options = [{'label': event[f'Session{i}'], 'value': event[f'Session{i}']} for i in range(1, 6) if
               pd.notna(event[f'Session{i}']) and event[f'Session{i}']]
    val = options[-1]['value'] if options else None
    for opt in options:
        if opt['label'] == 'Race': val = opt['value']
    return options, val


@app.callback(
    [Output('driver1-dropdown', 'options'), Output('driver1-dropdown', 'value'), Output('driver2-dropdown', 'options'),
     Output('driver2-dropdown', 'value')], [Input('session-dropdown', 'value')],
    [State('race-dropdown', 'value'), State('year-dropdown', 'value')])
def update_drivers(session_name, race, year):
    if not session_name or not race or not year: return dash.no_update, dash.no_update, dash.no_update, dash.no_update
    try:
        session = fastf1.get_session(year, race, session_name)
        session.load(telemetry=False, laps=False, weather=False, messages=False)
        valid_drivers = [d for d in session.results['Abbreviation'].dropna().tolist() if
                         isinstance(d, str) and len(d) == 3]
        options = [{'label': d, 'value': d} for d in sorted(valid_drivers)]
        return options, (valid_drivers[0] if len(valid_drivers) > 0 else None), options, (
            valid_drivers[1] if len(valid_drivers) > 1 else None)
    except:
        return [], None, [], None


@app.callback(
    [Output('speed-graph', 'figure'), Output('2d-dominance-graph', 'figure'), Output('strategy-graph', 'figure'),
     Output('main-title', 'children')],
    [Input('driver1-dropdown', 'value'), Input('driver2-dropdown', 'value'),
     Input('pace-filter', 'value')],
    [State('session-dropdown', 'value'), State('race-dropdown', 'value'), State('year-dropdown', 'value')])
def update_graphs(driver1, driver2, pace_filter, session_type, race, year):
    empty_fig = go.Figure().update_layout(template='plotly_dark')
    if not all([year, race, session_type, driver1, driver2]):
        return empty_fig, empty_fig, empty_fig, "Select parameters to load data..."

    try:
        # 1. Load Session Data
        session = fastf1.get_session(year, race, session_type)
        session.load(telemetry=True, weather=True, messages=False)

        # 2. Extract Laps & Telemetry
        lap1 = session.laps.pick_drivers(driver1).pick_fastest()
        lap2 = session.laps.pick_drivers(driver2).pick_fastest()

        if pd.isna(lap1['LapTime']) or pd.isna(lap2['LapTime']):
            raise ValueError("One or both drivers did not set a valid lap.")

        tel1 = lap1.get_telemetry().add_distance()
        tel2 = lap2.get_telemetry().add_distance()

        # 3. Setup Colors & Sort Drivers (Fastest vs Slowest)
        c1, c2 = _get_driver_colors(driver1, driver2, session)
        fast_data, slow_data = _sort_fastest_driver(driver1, tel1, c1, lap1, driver2, tel2, c2, lap2)

        # 4. Generate Graphs using Helpers
        fig_speed = _build_telemetry_fig(fast_data, slow_data)
        fig_2d_dom = _build_dominance_fig(driver1, driver2, c1, c2, tel1, tel2, fast_data, slow_data)

        if session_type != 'Race':
            fig_strat = go.Figure().update_layout(template='plotly_dark')
            fig_strat.add_annotation(text="Strategy & Weather only available for Race sessions", showarrow=False,
                                     font=dict(size=20), xref="paper", yref="paper", x=0.5, y=0.5)
        else:
            fig_strat = _build_strategy_fig(session, pace_filter, driver1, driver2, c1, c2)

        title_text = f"{year} {race} | {session_type} | {fast_data[0]} vs {slow_data[0]}"
        return fig_speed, fig_2d_dom, fig_strat, title_text

    except Exception as e:
        print(f"Graph Error: {e}")
        err_fig = go.Figure().update_layout(title=f"Error Loading Telemetry Data", template='plotly_dark')
        return err_fig, err_fig, err_fig, "Data Unavailable"

# TODO if feasible have app allow for switching between sessions without changing drivers
#  also  save selected session, drivers and tab when reloading the app and move to ai analytics soon


def _clear_old_cache(max_size_gb=1.0):
    cache_path = "f1_cache"

    if not os.path.exists(cache_path):
        os.makedirs(cache_path)
        fastf1.Cache.enable_cache(cache_path)
        return

    total_size = 0
    for root, _, files in os.walk(cache_path):
        for f in files:
            fp = os.path.join(root, f)
            total_size += os.path.getsize(fp)

    if total_size > max_size_gb * 1024 ** 3:
        print("***Cache limit reached! Clearing cache...")
        shutil.rmtree(cache_path)
        os.makedirs(cache_path)
        fastf1.Cache.enable_cache(cache_path)


if __name__ == '__main__':
    _clear_old_cache()
    app.run(debug=True, port=8050)
