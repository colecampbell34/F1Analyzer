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
import numpy as np
from functools import lru_cache
from google import genai

# --- GEMINI API SETUP ---
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '')

# --- 1. SETUP F1 CACHE ---
cache_dir = 'f1_cache'
if not os.path.exists(cache_dir):
    os.makedirs(cache_dir)
fastf1.Cache.enable_cache(cache_dir)

app = dash.Dash(__name__, external_stylesheets=[dbc.themes.CYBORG])


# --- SESSION CACHE ---
@lru_cache(maxsize=4)
def _load_session_cached(year, race, session_name, load_telemetry=True):
    """LRU-cached session loader to avoid redundant parsing."""
    session = fastf1.get_session(year, race, session_name)
    session.load(telemetry=load_telemetry, weather=load_telemetry, messages=False)
    return session

# --- 2. THE CONTROL PANEL (SIDEBAR) ---
sidebar = html.Div([
    html.H2("F1 AI Data", className="display-6", style={"fontSize": "1.5rem"}),
    html.Hr(),

    dbc.Label("Year", style={"fontSize": "0.9rem"}),
    dcc.Dropdown(id='year-dropdown', options=[{'label': str(y), 'value': y} for y in range(2018, 2027)], value=2026,
                 persistence=True, persistence_type='session', style={'color': 'black', 'fontSize': '0.9rem'}),
    html.Br(),

    dbc.Label("Grand Prix", style={"fontSize": "0.9rem"}),
    dcc.Dropdown(id='race-dropdown', persistence=True, style={'color': 'black', 'fontSize': '0.9rem'}),
    html.Br(),

    dbc.Label("Session", style={"fontSize": "0.9rem"}),
    dcc.Dropdown(id='session-dropdown', persistence=True, style={'color': 'black', 'fontSize': '0.9rem'}),
    html.Br(),

    dbc.Label("Driver 1", style={"fontSize": "0.9rem"}),
    dcc.Dropdown(id='driver1-dropdown', persistence=True, style={'color': 'black', 'fontSize': '0.9rem'}),
    html.Br(),

    dbc.Label("Driver 2", style={"fontSize": "0.9rem"}),
    dcc.Dropdown(id='driver2-dropdown', persistence=True, style={'color': 'black', 'fontSize': '0.9rem'}),
    html.Br(),
    dbc.Label("Strategy Chart Filter", style={"fontSize": "0.9rem"}),
    dcc.Dropdown(
        id='pace-filter',
        options=[
            {'label': 'Racing Laps', 'value': 'racing'},
            {'label': 'All Laps', 'value': 'all'}
        ],
        persistence=True,
        value='racing', style={'color': 'black', 'fontSize': '0.9rem'}
    ),

], style={"padding": "1rem", "background-color": "#111111", "height": "100vh", "overflowY": "auto"})

# --- 3. THE MAIN VIEWING AREA ---
content = html.Div([
    html.H3("Session Telemetry Analysis", className="text-center mt-2", id='main-title'),
    html.Hr(),

    dcc.Tabs([
        dcc.Tab(label='Telemetry Traces', children=[
            dcc.Graph(id='speed-graph', style={'height': '75vh'})
        ], style={'backgroundColor': '#222', 'color': 'white'},
                selected_style={'backgroundColor': '#ff0000', 'color': 'white'}),

        dcc.Tab(label='2D Track Dominance', children=[
            dcc.Graph(id='2d-dominance-graph', style={'height': '75vh'})
        ], style={'backgroundColor': '#222', 'color': 'white'},
                selected_style={'backgroundColor': '#ff0000', 'color': 'white'}),

        dcc.Tab(label='Strategy & Weather', children=[
            dcc.Graph(id='strategy-graph', style={'height': '75vh'})
        ], style={'backgroundColor': '#222', 'color': 'white'},
                selected_style={'backgroundColor': '#ff0000', 'color': 'white'}),

        dcc.Tab(label='AI Analysis', children=[
            html.Div([
                html.Div([
                    dbc.InputGroup([
                        dbc.Input(id='ai-question-input', type='text',
                                  placeholder='Ask about this session... (e.g. "Why was NOR faster in sector 2?")',
                                  style={'backgroundColor': '#1a1a1a', 'color': 'white', 'border': '1px solid #444',
                                         'fontSize': '0.95rem'}),
                        dbc.Button('Ask AI', id='ai-ask-button', color='danger', n_clicks=0,
                                   style={'fontWeight': 'bold'})
                    ], style={'marginBottom': '1rem'}),
                ], style={'padding': '1rem 0'}),
                dcc.Loading(
                    type='default', color='#ff0000',
                    children=html.Div(id='ai-response-output',
                                      style={'padding': '1rem', 'minHeight': '200px',
                                             'backgroundColor': '#1a1a1a', 'borderRadius': '8px',
                                             'border': '1px solid #333', 'whiteSpace': 'pre-wrap',
                                             'lineHeight': '1.6', 'fontSize': '0.95rem'})
                ),
                dcc.Store(id='session-context-store', data='')
            ], style={'padding': '1.5rem', 'height': '75vh', 'overflowY': 'auto'})
        ], style={'backgroundColor': '#222', 'color': 'white'},
                selected_style={'backgroundColor': '#ff0000', 'color': 'white'})
    ])
], style={"padding": "1rem"})

app.layout = dbc.Container([
    dcc.Loading(
        id="fullscreen-loader",
        type="default",
        color="#ff0000",
        fullscreen=True,
        overlay_style={"visibility": "visible", "opacity": 0.5, "backgroundColor": "black"},
        children=[
            dbc.Row([dbc.Col(sidebar, width=2), dbc.Col(content, width=10)])
        ]
    )
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
        row_heights=[0.75, 0.25], subplot_titles=("(SC/Pit Laps Removed from Racing Laps)", "Track Temperature (°C)")
    )

    comp_colors = {'SOFT': '#ff3333', 'MEDIUM': '#ffff00', 'HARD': '#ffffff', 'INTERMEDIATE': '#00ff00',
                   'WET': '#0099ff'}
    comp_drawn = set()

    # 4. Plot Pace & Tyres
    for lap_data, drv, col, unf in [(all_laps1, driver1, c1, unf_1), (all_laps2, driver2, c2, unf_2)]:
        if pace_filter == 'racing':
            if 'Compound' in lap_data.columns and 'Stint' in lap_data.columns:
                max_stint = lap_data['Stint'].max()

                for stint in lap_data['Stint'].dropna().unique():
                    stint_subset = lap_data[lap_data['Stint'] == stint].sort_values(by='LapNumber')

                    if stint_subset.empty: continue

                    comp = stint_subset['Compound'].iloc[0]
                    comp_drawn.add(comp)

                    # 1. Draw the Pace Line & Markers for this stint
                    fig.add_trace(go.Scatter(
                        x=stint_subset['LapNumber'],
                        y=stint_subset['LapTime_Sec'],
                        mode='lines+markers',
                        name=f'{drv} {comp}',
                        line=dict(color=col, width=2),
                        marker=dict(
                            color=comp_colors.get(comp, 'grey'),
                            size=10,
                            symbol='circle',
                            line=dict(width=0)
                        ),
                        showlegend=False
                    ), row=1, col=1)

                    # 2. Draw the Vertical "Pit Window" Line
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

        # Plot Pit Stops (Only if showing ALL laps)
        if pace_filter == 'all':
            pits = unf[unf['PitOutTime'].notna()]['LapNumber'] - 1
            valid_pits = lap_data[lap_data['LapNumber'].isin(pits)]
            fig.add_trace(go.Scatter(
                x=valid_pits['LapNumber'], y=valid_pits['LapTime_Sec'], mode='markers',
                marker=dict(symbol='triangle-up', size=16, color='white', line=dict(color=col, width=2)),
                name=f'{drv} Pit', showlegend=False
            ), row=1, col=1)

    # 5. Overlay SC/VSC/Red Flag lines
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

    # General Legend additions based on the filter
    if pace_filter == 'all':
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

    # 6. Weather & Rain Overlay (Now parses unf_1 to prevent gaps in weather data)
    weather_data = session.weather_data
    if not weather_data.empty and not unf_1.empty:
        track_temps, lap_nums, rain_laps = [], [], set()

        # Iterate over unfiltered laps to guarantee a continuous timeline
        for _, lap in unf_1.iterrows():
            idx = (weather_data['Time'] - lap['Time']).abs().idxmin()
            track_temps.append(weather_data.loc[idx, 'TrackTemp'])
            lap_nums.append(lap['LapNumber'])

            if weather_data.loc[idx, 'Rainfall']:
                rain_laps.add(lap['LapNumber'])

        # Plot the Track Temp line on Row 2
        fig.add_trace(go.Scatter(
            x=lap_nums, y=track_temps, mode='lines+markers', name='Track Temp (°C)',
            line=dict(color='white', width=2), marker=dict(size=4), showlegend=False
        ), row=2, col=1)

        # Draw Rain highlighting
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


def _gather_session_context(session, session_type, driver1, driver2):
    """Builds a comprehensive text summary of the session data to feed to the LLM as context."""
    lines = [f"Session Type: {session_type}", f"Drivers being compared: {driver1} vs {driver2}", ""]

    # Fastest lap comparison
    try:
        lap1 = session.laps.pick_drivers(driver1).pick_fastest()
        lap2 = session.laps.pick_drivers(driver2).pick_fastest()
        t1 = lap1['LapTime'].total_seconds()
        t2 = lap2['LapTime'].total_seconds()
        lines.append(f"Fastest Lap: {driver1} = {t1:.3f}s, {driver2} = {t2:.3f}s (Δ {abs(t1-t2):.3f}s)")

        # Sector times
        for s in [1, 2, 3]:
            s1 = lap1.get(f'Sector{s}Time')
            s2 = lap2.get(f'Sector{s}Time')
            if pd.notna(s1) and pd.notna(s2):
                lines.append(f"  Sector {s}: {driver1} = {s1.total_seconds():.3f}s, {driver2} = {s2.total_seconds():.3f}s")
    except Exception:
        lines.append("Fastest lap data: unavailable")

    # Race/Sprint specific data
    if session_type in ['Race', 'Sprint']:
        for drv in [driver1, driver2]:
            try:
                all_laps = session.laps.pick_drivers(drv).reset_index(drop=True)
                total_laps = int(all_laps['LapNumber'].max()) if not all_laps.empty else 0

                rl = all_laps.pick_wo_box().pick_track_status('1').loc[all_laps['LapNumber'] > 1].reset_index(drop=True)
                rl['LapTime_Sec'] = rl['LapTime'].dt.total_seconds()
                rl = rl.dropna(subset=['LapTime_Sec'])

                lines.append(f"\n=== {drv} ===")
                lines.append(f"Total laps completed: {total_laps}")

                if not rl.empty:
                    lines.append(f"Racing laps (excl. pit/SC/lap 1): {len(rl)}")
                    lines.append(f"  Average pace: {rl['LapTime_Sec'].mean():.3f}s")
                    lines.append(f"  Median pace: {rl['LapTime_Sec'].median():.3f}s")
                    lines.append(f"  Best lap: {rl['LapTime_Sec'].min():.3f}s")
                    lines.append(f"  Worst lap: {rl['LapTime_Sec'].max():.3f}s")

                # Pit stops (explicit lap numbers)
                pit_laps = all_laps[all_laps['PitOutTime'].notna()]['LapNumber'].tolist()
                if pit_laps:
                    lines.append(f"  Pit stop(s) on lap(s): {', '.join(str(int(l)) for l in pit_laps)}")
                else:
                    lines.append("  Pit stops: None")

                # Stint & tyre data with lap ranges
                if 'Stint' in all_laps.columns:
                    stints = sorted(all_laps['Stint'].dropna().unique())
                    lines.append(f"  Number of stints: {len(stints)}")
                    for stint in stints:
                        stint_all = all_laps[all_laps['Stint'] == stint].sort_values('LapNumber')
                        if stint_all.empty:
                            continue
                        lap_start = int(stint_all['LapNumber'].min())
                        lap_end = int(stint_all['LapNumber'].max())
                        comp = stint_all['Compound'].iloc[0] if 'Compound' in stint_all.columns else '?'
                        total_stint_laps = len(stint_all)

                        stint_racing = rl[rl['Stint'] == stint].sort_values('LapNumber').reset_index(drop=True)
                        if len(stint_racing) >= 3:
                            stint_racing['StintLap'] = range(1, len(stint_racing) + 1)
                            slope = np.polyfit(stint_racing['StintLap'].values.astype(float),
                                             stint_racing['LapTime_Sec'].values, 1)[0]
                            lines.append(f"    Stint {int(stint)}: {comp} tyres, laps {lap_start}-{lap_end} "
                                       f"({total_stint_laps} laps), deg rate: {slope:+.3f}s/lap")
                        else:
                            lines.append(f"    Stint {int(stint)}: {comp} tyres, laps {lap_start}-{lap_end} "
                                       f"({total_stint_laps} laps)")

                # Position changes
                if 'Position' in all_laps.columns and not all_laps.empty:
                    start_p = all_laps['Position'].iloc[0]
                    end_p = all_laps['Position'].iloc[-1]
                    if pd.notna(start_p) and pd.notna(end_p):
                        lines.append(f"  Grid position: P{int(start_p)} → Finish: P{int(end_p)}")

            except Exception:
                lines.append(f"\n{drv}: lap data unavailable")

        # Track status events (SC, VSC, Red Flag)
        lines.append("\n=== Track Status Events ===")
        sc_laps, vsc_laps, red_laps = set(), set(), set()
        for drv in [driver1, driver2]:
            try:
                unf = session.laps.pick_drivers(drv).reset_index(drop=True)
                sc_laps.update(unf[unf['TrackStatus'].astype(str).str.contains('4', na=False)]['LapNumber'].tolist())
                vsc_laps.update(unf[unf['TrackStatus'].astype(str).str.contains('6', na=False)]['LapNumber'].tolist())
                red_laps.update(unf[unf['TrackStatus'].astype(str).str.contains('5', na=False)]['LapNumber'].tolist())
            except Exception:
                pass

        if sc_laps:
            lines.append(f"Safety Car on lap(s): {', '.join(str(int(l)) for l in sorted(sc_laps))}")
        if vsc_laps:
            lines.append(f"Virtual Safety Car on lap(s): {', '.join(str(int(l)) for l in sorted(vsc_laps))}")
        if red_laps:
            lines.append(f"Red Flag on lap(s): {', '.join(str(int(l)) for l in sorted(red_laps))}")
        if not sc_laps and not vsc_laps and not red_laps:
            lines.append("No Safety Car, VSC, or Red Flag incidents during the session.")

        # Weather
        try:
            weather = session.weather_data
            if not weather.empty:
                lines.append(f"\n=== Weather ===")
                lines.append(f"Track Temp: {weather['TrackTemp'].min():.1f}°C - {weather['TrackTemp'].max():.1f}°C")
                lines.append(f"Air Temp: {weather['AirTemp'].min():.1f}°C - {weather['AirTemp'].max():.1f}°C")
                if weather['Rainfall'].any():
                    lines.append("Rain: Yes (rain detected during session)")
                else:
                    lines.append("Rain: No")
        except Exception:
            pass

    return "\n".join(lines)


@app.callback([Output('race-dropdown', 'options'), Output('race-dropdown', 'value')], [Input('year-dropdown', 'value')],
              [State('race-dropdown', 'value')])
def update_races(year, current_race):
    if not year: return dash.no_update, dash.no_update
    schedule = fastf1.get_event_schedule(year)
    schedule = schedule[schedule['EventFormat'] != 'testing']
    races = schedule['EventName'].tolist()
    options = [{'label': r.replace("Grand Prix", "GP"), 'value': r} for r in races]

    # If the persisted race is still valid for this year, keep it! Otherwise, use the 1st race.
    val = current_race if current_race in races else (races[0] if races else None)
    return options, val


@app.callback([Output('session-dropdown', 'options'), Output('session-dropdown', 'value')],
              [Input('race-dropdown', 'value')], [State('year-dropdown', 'value'), State('session-dropdown', 'value')])
def update_sessions(race, year, current_session):
    if not race or not year: return dash.no_update, dash.no_update
    event = fastf1.get_event(year, race)

    # Generate the available sessions for this specific weekend
    options = [{'label': event[f'Session{i}'], 'value': event[f'Session{i}']} for i in range(1, 6) if
               pd.notna(event[f'Session{i}']) and event[f'Session{i}']]
    valid_sessions = [opt['value'] for opt in options]

    if current_session in valid_sessions:
        val = current_session
    else:
        val = options[-1]['value'] if options else None
        for opt in options:
            if opt['label'] == 'Race': val = opt['value']

    return options, val


@app.callback([Output('driver1-dropdown', 'options'), Output('driver1-dropdown', 'value'),
     Output('driver2-dropdown', 'options'), Output('driver2-dropdown', 'value')],
    [Input('session-dropdown', 'value'), Input('race-dropdown', 'value')],
    [State('year-dropdown', 'value'), State('driver1-dropdown', 'value'), State('driver2-dropdown', 'value')])
def update_drivers(session_name, race, year, current_d1, current_d2):
    if not session_name or not race or not year:
        return dash.no_update, dash.no_update, dash.no_update, dash.no_update

    # Identify which dropdown caused this callback to fire
    triggered_id = dash.ctx.triggered_id

    try:
        session = _load_session_cached(year, race, session_name, load_telemetry=False)
        valid_drivers = [d for d in session.results['Abbreviation'].dropna().tolist() if
                         isinstance(d, str) and len(d) == 3]
        options = [{'label': d, 'value': d} for d in sorted(valid_drivers)]

        # Default choices (1st and 2nd fastest in the session)
        default_d1 = valid_drivers[0] if len(valid_drivers) > 0 else None
        default_d2 = valid_drivers[1] if len(valid_drivers) > 1 else None

        if triggered_id == 'race-dropdown':
            # User switched to a new Grand Prix -> Reset to the session defaults
            return options, default_d1, options, default_d2
        else:
            # User switched Sessions in the same GP -> Keep current driver if they drove in this session
            new_d1 = current_d1 if current_d1 in valid_drivers else default_d1
            new_d2 = current_d2 if current_d2 in valid_drivers else default_d2
            return options, new_d1, options, new_d2

    except:
        return [], None, [], None


@app.callback([Output('speed-graph', 'figure'), Output('2d-dominance-graph', 'figure'), Output('strategy-graph', 'figure'),
     Output('session-context-store', 'data'), Output('main-title', 'children')],
    [Input('driver1-dropdown', 'value'), Input('driver2-dropdown', 'value'),
     Input('pace-filter', 'value')],
    [State('session-dropdown', 'value'), State('race-dropdown', 'value'), State('year-dropdown', 'value')])
def update_graphs(driver1, driver2, pace_filter, session_type, race, year):
    empty_fig = go.Figure().update_layout(template='plotly_dark')
    if not all([year, race, session_type, driver1, driver2]):
        return empty_fig, empty_fig, empty_fig, '', "Select parameters to load data..."

    try:
        # 1. Load Session Data (cached)
        session = _load_session_cached(year, race, session_type, load_telemetry=True)

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

        # Strategy (Race/Sprint only)
        if session_type not in ['Race', 'Sprint']:
            fig_strat = go.Figure().update_layout(template='plotly_dark')
            fig_strat.add_annotation(text="Strategy & Weather only available for Race or Sprint sessions",
                                     showarrow=False, font=dict(size=20), xref="paper", yref="paper", x=0.5, y=0.5)
        else:
            fig_strat = _build_strategy_fig(session, pace_filter, driver1, driver2, c1, c2)

        # Build session context for AI Q&A
        context = _gather_session_context(session, session_type, driver1, driver2)
        context_header = f"{year} {race} | {session_type} | {driver1} vs {driver2}"
        full_context = f"{context_header}\n\n{context}"

        title_text = f"{year} {race} | {session_type} | {fast_data[0]} vs {slow_data[0]}"
        return fig_speed, fig_2d_dom, fig_strat, full_context, title_text

    except Exception as e:
        print(f"Graph Error: {e}")
        err_fig = go.Figure().update_layout(title=f"Error Loading Telemetry Data", template='plotly_dark')
        return err_fig, err_fig, err_fig, '', "Data Unavailable"


@app.callback(
    Output('ai-response-output', 'children'),
    [Input('ai-ask-button', 'n_clicks')],
    [State('ai-question-input', 'value'), State('session-context-store', 'data')],
    prevent_initial_call=True
)
def ask_ai(n_clicks, question, session_context):
    """Sends the user's question + session context to Gemini and returns the response."""
    if not n_clicks or not question or not question.strip():
        return html.P("Type a question and click 'Ask AI' to get started.", style={'color': '#888'})

    if not GEMINI_API_KEY:
        return html.Div([
            html.P("⚠️ Gemini API key not configured.", style={'color': '#ff4444', 'fontWeight': 'bold'}),
            html.P("Set the GEMINI_API_KEY environment variable before running the app:",
                   style={'color': '#aaa'}),
            html.Code("export GEMINI_API_KEY='your-api-key-here'",
                      style={'color': '#00ff88', 'backgroundColor': '#111', 'padding': '0.5rem',
                             'display': 'block', 'borderRadius': '4px', 'marginTop': '0.5rem'})
        ])

    if not session_context:
        return html.P("⚠️ No session data loaded. Select a session and drivers first.", style={'color': '#ff4444'})

    try:
        import time
        client = genai.Client(api_key=GEMINI_API_KEY)
        prompt = (
            "You are an expert Formula 1 data analyst. You have access to the following telemetry "
            "and race data for a specific F1 session. Answer the user's question with detailed, "
            "data-driven analysis. Reference specific numbers from the data. Be thorough and conclusive.\n\n"
            "=== SESSION DATA ===\n"
            f"{session_context}\n\n"
            "=== USER QUESTION ===\n"
            f"{question}"
        )

        # Try primary model, retry once on rate limit, then fallback
        models_to_try = ['gemini-flash-latest', 'gemini-3.1-flash-lite', 'gemini-2.5-flash', 'gemini-2.5-flash-lite']
        last_error = None

        for model_name in models_to_try:
            try:
                response = client.models.generate_content(model=model_name, contents=prompt)
                answer = response.text

                return html.Div([
                    html.Div([
                        html.Strong("Q: ", style={'color': '#ff4444'}),
                        html.Span(question, style={'color': '#ddd'})
                    ], style={'marginBottom': '1rem', 'paddingBottom': '0.75rem', 'borderBottom': '1px solid #333'}),
                    html.Div([
                        dcc.Markdown(answer, style={'color': '#e0e0e0', 'lineHeight': '1.7'})
                    ])
                ])
            except Exception as e:
                last_error = e
                if '429' not in str(e):
                    break  # Non-rate-limit error, don't retry

        # If all retries failed
        error_str = str(last_error)
        if '429' in error_str:
            return html.Div([
                html.P("⏳ Rate limit reached on Gemini free tier.", style={'color': '#ffaa00', 'fontWeight': 'bold'}),
                html.P("The free API has per-minute request limits. Please wait about 60 seconds and try again.",
                       style={'color': '#aaa'}),
                html.P("Tip: Shorter, more focused questions use fewer tokens and are less likely to hit limits.",
                       style={'color': '#666', 'fontStyle': 'italic'})
            ])
        else:
            return html.Div([
                html.P(f"❌ AI Error: {error_str}", style={'color': '#ff4444'}),
                html.P("Please check your API key and try again.", style={'color': '#888'})
            ])

    except Exception as e:
        return html.Div([
            html.P(f"❌ AI Error: {str(e)}", style={'color': '#ff4444'}),
            html.P("Please check your API key and try again.", style={'color': '#888'})
        ])


def _clear_old_cache(max_size_gb=2.0):
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
