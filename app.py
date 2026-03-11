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

        # TAB 2: The Merged 3D Dominance Map
        dcc.Tab(label='3D Track Dominance', children=[
            dcc.Loading(type="default", color="#ff0000",
                        children=dcc.Graph(id='3d-dominance-graph', style={'height': '75vh'}))
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


# --- CALLBACKS 1-3 (DYNAMIC DROPDOWNS) ---
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
    [Output('speed-graph', 'figure'), Output('3d-dominance-graph', 'figure'), Output('strategy-graph', 'figure'),
     Output('main-title', 'children')],
    [Input('driver1-dropdown', 'value'), Input('driver2-dropdown', 'value'), Input('metric-dropdown', 'value'),
     Input('pace-filter', 'value')],
    [State('session-dropdown', 'value'), State('race-dropdown', 'value'), State('year-dropdown', 'value')]
    )
def update_graphs(driver1, driver2, metric, pace_filter, session_type, race, year):
    empty_fig = go.Figure().update_layout(template='plotly_dark')
    if not all([year, race, session_type, driver1, driver2, metric]):
        return empty_fig, empty_fig, empty_fig, "Select parameters to load data..."

    try:
        session = fastf1.get_session(year, race, session_type)
        # CRITICAL: We now MUST load Weather = True for Tab 3!
        session.load(telemetry=True, weather=True, messages=False)

        # FASTEST LAPS (For Tab 1 & Tab 2)
        lap1 = session.laps.pick_drivers(driver1).pick_fastest()
        lap2 = session.laps.pick_drivers(driver2).pick_fastest()

        if pd.isna(lap1['LapTime']) or pd.isna(lap2['LapTime']):
            raise ValueError("One or both drivers did not set a valid lap.")

        tel1 = lap1.get_telemetry().add_distance()
        tel2 = lap2.get_telemetry().add_distance()
        t1, t2 = lap1['LapTime'].total_seconds(), lap2['LapTime'].total_seconds()

        # DYNAMIC COLORS
        try:
            c1, c2 = fastf1.plotting.get_driver_color(driver1, session), fastf1.plotting.get_driver_color(driver2,
                                                                                                          session)
        except:
            c1, c2 = '#00ffff', '#ff00ff'
        if not c1.startswith('#'): c1 = f"#{c1}"
        if not c2.startswith('#'): c2 = f"#{c2}"
        if c1.lower() == c2.lower(): c2 = '#ffffff' if c1.lower() != '#ffffff' else '#ffff00'

        # SORTING FASTEST DRIVER
        if t1 <= t2:
            fast_driver, fast_tel, fast_c, fast_t = driver1, tel1, c1, t1
            slow_driver, slow_tel, slow_c, slow_t = driver2, tel2, c2, t2
        else:
            fast_driver, fast_tel, fast_c, fast_t = driver2, tel2, c2, t2
            slow_driver, slow_tel, slow_c, slow_t = driver1, tel1, c1, t1

        # TODO maybe change this and the domination map so users can pick any single lap
        #  might be too complex
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
        fig_speed.update_layout(title=f'{metric} Trace (Fastest lap)', xaxis_title='Distance along track (meters)',
                                yaxis_title=y_labels.get(metric, metric), template='plotly_dark', hovermode='x unified',
                                margin=dict(l=40, r=40, t=40, b=40),
                                legend=dict(yanchor="top", y=0.99, xanchor="right", x=0.99))

        # ==========================================
        # GRAPH 2: COMBINED 3D DOMINANCE MAP
        # ==========================================
        num_minisectors = 15
        sector_length = max(tel1['Distance'].max(), tel2['Distance'].max()) / num_minisectors
        tel1['MiniSector'] = (tel1['Distance'] // sector_length).astype(int)
        tel2['MiniSector'] = (tel2['Distance'] // sector_length).astype(int)

        v1_avg = tel1.groupby('MiniSector')['Speed'].mean()
        v2_avg = tel2.groupby('MiniSector')['Speed'].mean()
        winner_list = [driver1 if v1_avg.get(i, 0) > v2_avg.get(i, 0) else driver2 for i in range(num_minisectors + 1)]

        # Calculate Aspect Ratio to preserve track shape but boost Elevation (Z)
        x_range = fast_tel['X'].max() - fast_tel['X'].min()
        y_range = fast_tel['Y'].max() - fast_tel['Y'].min()
        max_range = max(x_range, y_range)

        fig_3d_dom = go.Figure()

        # Add Dummy Legend Items
        fig_3d_dom.add_trace(go.Scatter3d(x=[None], y=[None], z=[None], mode='lines', line=dict(color=fast_c, width=6),
                                          name=f'{fast_driver} Faster ({fast_t:.3f}s)'))
        fig_3d_dom.add_trace(go.Scatter3d(x=[None], y=[None], z=[None], mode='lines', line=dict(color=slow_c, width=6),
                                          name=f'{slow_driver} Faster ({slow_t:.3f}s)'))

        # Draw the 3D Mini-Sectors
        for ms in range(num_minisectors):
            # We map the physical path of the overall fastest driver, but color it by the sector winner
            sector_data = fast_tel[fast_tel['MiniSector'] == ms]
            if sector_data.empty: continue

            next_sector = fast_tel[fast_tel['MiniSector'] == ms + 1]
            if not next_sector.empty: sector_data = pd.concat([sector_data, next_sector.iloc[[0]]])

            winner = winner_list[ms]
            color = c1 if winner == driver1 else c2

            fig_3d_dom.add_trace(go.Scatter3d(
                x=sector_data['X'], y=sector_data['Y'], z=sector_data['Z'],
                mode='lines', line=dict(color=color, width=8),
                showlegend=False, hoverinfo='skip'
            ))

        fig_3d_dom.update_layout(
            title="3D Track Elevation & Dominance Map", template='plotly_dark',
            scene=dict(
                xaxis=dict(visible=False), yaxis=dict(visible=False), zaxis=dict(visible=False),
                aspectmode='manual', aspectratio=dict(x=x_range / max_range, y=y_range / max_range, z=0.15)
            ), margin=dict(l=0, r=0, t=40, b=0), legend=dict(yanchor="top", y=0.99, xanchor="left", x=0.01)
        )

        # ==========================================
        # GRAPH 3: RACE PACE, PITS & WEATHER STRATEGY
        # ==========================================

        # TODO analyze graphs to see if they are representing the data well and what we can improve
        
        if session_type != 'Race':
            fig_strat = go.Figure().update_layout(template='plotly_dark')
            fig_strat.add_annotation(text="Strategy & Weather only available for Race sessions",
                                     showarrow=False, font=dict(size=20), xref="paper", yref="paper", x=0.5, y=0.5)
            title_text = f"{year} {race} | {session_type} | {fast_driver} vs {slow_driver}"
            return fig_speed, fig_3d_dom, fig_strat, title_text

        # 1. Fetch unfiltered laps to preserve pit stop data
        unfiltered_1 = session.laps.pick_drivers(driver1).reset_index(drop=True)
        unfiltered_2 = session.laps.pick_drivers(driver2).reset_index(drop=True)

        weather_data = session.weather_data

        # Racing laps or all laps
        if pace_filter == 'racing':
            all_laps1 = unfiltered_1.pick_wo_box().pick_track_status('1').loc[unfiltered_1['LapNumber'] > 1].reset_index(drop=True)
            all_laps2 = unfiltered_2.pick_wo_box().pick_track_status('1').loc[unfiltered_2['LapNumber'] > 1].reset_index(drop=True)
        else:
            all_laps1 = unfiltered_1
            all_laps2 = unfiltered_2

        all_laps1['LapTime_Sec'] = all_laps1['LapTime'].dt.total_seconds()
        all_laps2['LapTime_Sec'] = all_laps2['LapTime'].dt.total_seconds()

        fig_strat = make_subplots(specs=[[{"secondary_y": True}]])
        comp_colors = {'SOFT': '#ff3333', 'MEDIUM': '#ffff00', 'HARD': '#ffffff', 'INTERMEDIATE': '#00ff00',
                       'WET': '#0099ff'}

        # Track which compounds are drawn for the general legend
        comp_drawn = set()

        # Plot pace line, tyre compounds, pit stops
        for lap_data, drv, col, unfiltered in [(all_laps1, driver1, c1, unfiltered_1), (all_laps2, driver2, c2, unfiltered_2)]:

            # Plot Pace Line
            fig_strat.add_trace(go.Scatter(
                x=lap_data['LapNumber'], y=lap_data['LapTime_Sec'],
                mode='lines', name=f'{drv} Pace', line=dict(color=col),
                legend='legend'
            ), secondary_y=False)

            # Plot Tyre Compounds
            if 'Compound' in lap_data.columns:
                comp_drawn.update(lap_data['Compound'].dropna().unique())
                for compound in lap_data['Compound'].dropna().unique():
                    comp_subset = lap_data[lap_data['Compound'] == compound]
                    fig_strat.add_trace(go.Scatter(
                        x=comp_subset['LapNumber'], y=comp_subset['LapTime_Sec'],
                        mode='markers', name=f'{drv} {compound}',
                        marker=dict(color=comp_colors.get(compound, 'grey'), size=8),
                        showlegend=False
                    ), secondary_y=False)

            if pace_filter == 'all':
                # Plot Pit Stops
                pits = unfiltered[unfiltered['PitOutTime'].notna()]['LapNumber']
                valid_pits = lap_data[lap_data['LapNumber'].isin(pits)]
                fig_strat.add_trace(go.Scatter(
                    x=valid_pits['LapNumber'], y=valid_pits['LapTime_Sec'],
                    mode='markers',
                    marker=dict(symbol='triangle-up', size=14, color='white', line=dict(color='black', width=1)),
                    name=f'{drv} Pit', showlegend=False
                ), secondary_y=False)

        # Plot general track statuses and general legend entries
        if pace_filter == 'all':
            sc_laps = set()
            vsc_laps = set()
            red_laps = set()
            
            for unfiltered in [unfiltered_1, unfiltered_2]:
                sc_laps.update(unfiltered[unfiltered['TrackStatus'].astype(str).str.contains('4', na=False)]['LapNumber'].tolist())
                vsc_laps.update(unfiltered[unfiltered['TrackStatus'].astype(str).str.contains('6', na=False)]['LapNumber'].tolist())
                red_laps.update(unfiltered[unfiltered['TrackStatus'].astype(str).str.contains('5', na=False)]['LapNumber'].tolist())

            for lap in sc_laps:
                fig_strat.add_vline(x=lap, line_width=2, line_dash="dash", line_color="orange", opacity=0.5)
            for lap in vsc_laps:
                fig_strat.add_vline(x=lap, line_width=2, line_dash="dash", line_color="yellow", opacity=0.5)
            for lap in red_laps:
                fig_strat.add_vline(x=lap, line_width=2, line_dash="dash", line_color="red", opacity=0.5)

            if sc_laps:
                fig_strat.add_trace(go.Scatter(
                    x=[None], y=[None], mode='lines', line=dict(color='orange', dash='dash', width=2),
                    name='SC / YF', legend='legend2'
                ))
            if vsc_laps:
                fig_strat.add_trace(go.Scatter(
                    x=[None], y=[None], mode='lines', line=dict(color='yellow', dash='dash', width=2),
                    name='VSC', legend='legend2'
                ))
            if red_laps:
                fig_strat.add_trace(go.Scatter(
                    x=[None], y=[None], mode='lines', line=dict(color='red', dash='dash', width=2),
                    name='Red Flag', legend='legend2'
                ))
            
            fig_strat.add_trace(go.Scatter(
                x=[None], y=[None], mode='markers', name='Pit Stop',
                marker=dict(symbol='triangle-up', size=14, color='white', line=dict(color='black', width=1)),
                legend='legend2'
            ))

        for comp in comp_drawn:
            if comp in comp_colors:
                fig_strat.add_trace(go.Scatter(
                    x=[None], y=[None], mode='markers', name=comp,
                    marker=dict(color=comp_colors[comp], size=8),
                    legend='legend2'
                ))

        # Track Temperature Overlay & Precipitation
        if not weather_data.empty and not all_laps1.empty:
            track_temps = []
            lap_nums = []
            rain_laps = set()
            for _, lap in all_laps1.iterrows():
                # Find the weather reading closest to the time this lap was completed
                idx = (weather_data['Time'] - lap['Time']).abs().idxmin()
                track_temps.append(weather_data.loc[idx, 'TrackTemp'])
                lap_nums.append(lap['LapNumber'])
                
                # Check for rainfall during this lap
                if weather_data.loc[idx, 'Rainfall']:
                    rain_laps.add(lap['LapNumber'])

            # Plot the weather line on the Secondary Y-Axis
            fig_strat.add_trace(go.Scatter(
                x=lap_nums, y=track_temps, mode='lines', name='Track Temp (°C)',
                line=dict(color='white', dash='dot', width=2), opacity=0.4,
                legend='legend'
            ), secondary_y=True)

            # --- PRECIPITATION OVERLAY ---
            for lap in rain_laps:
                fig_strat.add_vline(x=lap, line_width=4, line_dash="dot", line_color="#00ffff", opacity=0.25)

            if rain_laps:
                fig_strat.add_trace(go.Scatter(
                    x=[None], y=[None], mode='lines', line=dict(color='#00ffff', dash='dot', width=4),
                    name='Rain', legend='legend2'
                ))

        fig_strat.update_layout(
            title="Race Pace, Tyres & Strategy",
            template='plotly_dark', hovermode='x unified', margin=dict(l=40, r=240, t=60, b=40),
            legend=dict(
                title=dict(text="Pace"),
                yanchor="top", y=0.99, xanchor="left", x=1.02,
                bgcolor="rgba(0,0,0,0)"
            ),
            legend2=dict(
                title=dict(text="Tyres & Status"),
                yanchor="top", y=0.75, xanchor="left", x=1.02,
                bgcolor="rgba(0,0,0,0)"
            )
        )
        fig_strat.update_xaxes(title_text="Lap Number")
        fig_strat.update_yaxes(title_text="Lap Time (Seconds)", secondary_y=False)
        fig_strat.update_yaxes(title_text="Track Temp (°C)", secondary_y=True, showgrid=False)

        title_text = f"{year} {race} | {session_type} | {fast_driver} vs {slow_driver}"
        return fig_speed, fig_3d_dom, fig_strat, title_text

    except Exception as e:
        print(f"Graph Error: {e}")
        err_fig = go.Figure().update_layout(title=f"Error Loading Telemetry Data", template='plotly_dark')
        return err_fig, err_fig, err_fig, "Data Unavailable"


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

    if total_size > max_size_gb * 1024**3:
        print("***Cache limit reached! Clearing cache...")
        shutil.rmtree(cache_path)
        os.makedirs(cache_path)
        fastf1.Cache.enable_cache(cache_path)


if __name__ == '__main__':
    _clear_old_cache()
    app.run(debug=True)