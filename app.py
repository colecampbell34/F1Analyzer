import dash
from dash import dcc, html
import dash_bootstrap_components as dbc
from dash.dependencies import Input, Output
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

driver_options = [{'label': d, 'value': d} for d in ['VER', 'NOR', 'LEC', 'SAI', 'HAM', 'RUS', 'PIA', 'ALO', 'PER']]

# --- 2. THE CONTROL PANEL (SIDEBAR) ---
sidebar = html.Div([
    html.H2("F1 AI Data", className="display-6"),
    html.Hr(),

    dbc.Label("Year"),
    dcc.Dropdown(id='year-dropdown', options=[{'label': str(y), 'value': y} for y in range(2023, 2027)], value=2024,
                 style={'color': 'black'}),
    html.Br(),

    dbc.Label("Grand Prix"),
    dcc.Dropdown(
        id='race-dropdown',
        options=[{'label': 'Bahrain', 'value': 'Bahrain'}, {'label': 'Saudi Arabia', 'value': 'Saudi Arabia'},
                 {'label': 'Australia', 'value': 'Australia'}, {'label': 'Japan', 'value': 'Japan'}],
        value='Australia', style={'color': 'black'}
    ),
    html.Br(),

    dbc.Label("Driver 1"),
    dcc.Dropdown(id='driver1-dropdown', options=driver_options, value='VER', style={'color': 'black'}),
    html.Br(),

    dbc.Label("Driver 2"),
    dcc.Dropdown(id='driver2-dropdown', options=driver_options, value='NOR', style={'color': 'black'}),
    html.Br(),
    html.Hr(),

    # NEW: Telemetry Metric Selector
    dbc.Label("Telemetry Metric"),
    dcc.Dropdown(
        id='metric-dropdown',
        options=[
            {'label': 'Speed (km/h)', 'value': 'Speed'},
            {'label': 'Throttle (%)', 'value': 'Throttle'},
            {'label': 'Brake (%)', 'value': 'Brake'},
            {'label': 'Gear', 'value': 'nGear'},
            {'label': 'Engine RPM', 'value': 'RPM'}
        ],
        value='Speed',  # Default value
        style={'color': 'black'}
    ),

], style={"padding": "2rem", "background-color": "#111111", "height": "100vh"})

# --- 3. THE MAIN VIEWING AREA ---
content = html.Div([
    html.H3("Qualifying Telemetry Analysis", className="text-center mt-3"),
    html.Hr(),

    dcc.Tabs([
        # Tab 1: The Telemetry Traces
        dcc.Tab(label='Telemetry Traces', children=[
            dcc.Loading(type="default", color="#ff0000", children=dcc.Graph(id='speed-graph'))
        ], style={'backgroundColor': '#222', 'color': 'white'},
                selected_style={'backgroundColor': '#ff0000', 'color': 'white'}),

        # Tab 2: The Dominance Map
        dcc.Tab(label='Track Dominance Map', children=[
            dcc.Loading(type="default", color="#ff0000",
                        children=dcc.Graph(id='dominance-graph', style={'height': '70vh'}))
        ], style={'backgroundColor': '#222', 'color': 'white'},
                selected_style={'backgroundColor': '#ff0000', 'color': 'white'})
    ])
], style={"padding": "2rem"})

app.layout = dbc.Container([
    dbc.Row([dbc.Col(sidebar, width=3), dbc.Col(content, width=9)])
], fluid=True, style={"padding": "0px"})


# --- 4. THE CALLBACK ---
@app.callback([Output('speed-graph', 'figure'), Output('dominance-graph', 'figure')],
              [Input('year-dropdown', 'value'), Input('race-dropdown', 'value'),
               Input('driver1-dropdown', 'value'), Input('driver2-dropdown', 'value'),
               Input('metric-dropdown', 'value')]  # NEW INPUT ADDED HERE
              )
def update_graphs(year, race, driver1, driver2, metric):
    if not year or not race or not driver1 or not driver2 or not metric:
        return go.Figure(), go.Figure()

    try:
        session = fastf1.get_session(year, race, 'Q')
        session.load(telemetry=True, weather=False, messages=False)

        lap1 = session.laps.pick_drivers(driver1).pick_fastest()
        lap2 = session.laps.pick_drivers(driver2).pick_fastest()

        tel1 = lap1.get_telemetry().add_distance()
        tel2 = lap2.get_telemetry().add_distance()

        # --- SMART COLOR ASSIGNMENT ---
        try:
            c1 = fastf1.plotting.get_driver_color(driver1, session)
            c2 = fastf1.plotting.get_driver_color(driver2, session)
        except:
            c1, c2 = '#00ffff', '#ff00ff'  # Fallback if driver color isn't found

        # Ensure hex starts with #
        if not c1.startswith('#'): c1 = f"#{c1}"
        if not c2.startswith('#'): c2 = f"#{c2}"

        # If teammates (same color), give driver 2 a high-visibility fallback color
        if c1.lower() == c2.lower():
            c2 = '#ffffff' if c1.lower() != '#ffffff' else '#ffff00'

        # ==========================================
        # GRAPH 1: DYNAMIC TELEMETRY TRACE
        # ==========================================
        fig_speed = go.Figure()
        fig_speed.add_trace(
            go.Scatter(x=tel1['Distance'], y=tel1[metric], mode='lines', name=f'{driver1}', line=dict(color=c1)))
        fig_speed.add_trace(
            go.Scatter(x=tel2['Distance'], y=tel2[metric], mode='lines', name=f'{driver2}', line=dict(color=c2)))

        # Dynamic Y-Axis Labels
        y_labels = {'Speed': 'Speed (km/h)', 'Throttle': 'Throttle (%)', 'Brake': 'Brake Pressure (%)', 'nGear': 'Gear',
                    'RPM': 'Engine RPM'}

        fig_speed.update_layout(
            title=f'{metric} Trace',
            xaxis_title='Distance along track (meters)',
            yaxis_title=y_labels.get(metric, metric),
            template='plotly_dark',
            hovermode='x unified',
            margin=dict(l=40, r=40, t=40, b=40)
        )

        # ==========================================
        # GRAPH 2: TRACK DOMINANCE MAP (CONTINUOUS LINES)
        # ==========================================
        num_minisectors = 15
        total_distance = max(tel1['Distance'].max(), tel2['Distance'].max())
        sector_length = total_distance / num_minisectors

        tel1['MiniSector'] = (tel1['Distance'] // sector_length).astype(int)
        tel2['MiniSector'] = (tel2['Distance'] // sector_length).astype(int)

        v1_avg = tel1.groupby('MiniSector')['Speed'].mean()
        v2_avg = tel2.groupby('MiniSector')['Speed'].mean()

        winner_list = []
        for i in range(num_minisectors + 1):
            winner_list.append(driver1 if v1_avg.get(i, 0) > v2_avg.get(i, 0) else driver2)

        fig_map = go.Figure()

        # Flags to ensure drivers only appear in the legend once
        legend_added_d1 = False
        legend_added_d2 = False

        # 2. Draw each sector as a solid, continuous line
        for ms in range(num_minisectors):
            sector_data = tel1[tel1['MiniSector'] == ms]
            if sector_data.empty: continue

            # CRITICAL: Append the first point of the NEXT sector to close the gap!
            next_sector_data = tel1[tel1['MiniSector'] == ms + 1]
            if not next_sector_data.empty:
                sector_data = pd.concat([sector_data, next_sector_data.iloc[[0]]])

            winner = winner_list[ms]
            color = c1 if winner == driver1 else c2

            show_legend = False
            if winner == driver1 and not legend_added_d1:
                show_legend, legend_added_d1 = True, True
            elif winner == driver2 and not legend_added_d2:
                show_legend, legend_added_d2 = True, True

            fig_map.add_trace(go.Scatter(
                x=sector_data['X'], y=sector_data['Y'],
                mode='lines',
                line=dict(color=color, width=10),  # Thick continuous line
                name=f'{winner} Faster',
                showlegend=show_legend,
                hoverinfo='skip'
            ))

        fig_map.update_layout(
            title="Track Dominance (15 Mini-Sectors)",
            template='plotly_dark',
            yaxis=dict(scaleanchor="x", scaleratio=1, visible=False),
            xaxis=dict(visible=False),
            margin=dict(l=0, r=0, t=40, b=0)
        )

        return fig_speed, fig_map

    except Exception as e:
        print(f"Error: {e}")
        empty_fig = go.Figure().update_layout(title="Error loading data.", template='plotly_dark')
        return empty_fig, empty_fig


if __name__ == '__main__':
    app.run(debug=True)