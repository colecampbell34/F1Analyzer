import dash
from dash import dcc, html
import dash_bootstrap_components as dbc
from dash.dependencies import Input, Output
import plotly.graph_objects as go
import fastf1
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
], style={"padding": "2rem", "background-color": "#111111", "height": "100vh"})

# --- 3. THE MAIN VIEWING AREA (NOW WITH TABS!) ---
content = html.Div([
    html.H3("Qualifying Telemetry Analysis", className="text-center mt-3"),
    html.Hr(),

    dcc.Tabs([
        # Tab 1: The Speed Traces
        dcc.Tab(label='Speed Traces', children=[
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


# --- 4. THE CALLBACK (Generates BOTH graphs now) ---
@app.callback([Output('speed-graph', 'figure'), Output('dominance-graph', 'figure')],
              [Input('year-dropdown', 'value'), Input('race-dropdown', 'value'),
               Input('driver1-dropdown', 'value'), Input('driver2-dropdown', 'value')]
              )
def update_graphs(year, race, driver1, driver2):
    if not year or not race or not driver1 or not driver2:
        return go.Figure(), go.Figure()

    try:
        session = fastf1.get_session(year, race, 'Q')
        session.load(telemetry=True, weather=False, messages=False)

        # Updated to pick_drivers()
        lap1 = session.laps.pick_drivers(driver1).pick_fastest()
        lap2 = session.laps.pick_drivers(driver2).pick_fastest()

        tel1 = lap1.get_telemetry().add_distance()
        tel2 = lap2.get_telemetry().add_distance()

        # ==========================================
        # GRAPH 1: SPEED TRACE
        # ==========================================
        fig_speed = go.Figure()
        fig_speed.add_trace(go.Scatter(x=tel1['Distance'], y=tel1['Speed'], mode='lines', name=f'{driver1}',
                                       line=dict(color='#00ffff')))
        fig_speed.add_trace(go.Scatter(x=tel2['Distance'], y=tel2['Speed'], mode='lines', name=f'{driver2}',
                                       line=dict(color='#ff00ff')))
        fig_speed.update_layout(title=f'Speed Trace', template='plotly_dark', hovermode='x unified',
                                margin=dict(l=40, r=40, t=40, b=40))

        # ==========================================
        # GRAPH 2: TRACK DOMINANCE MAP
        # ==========================================
        # 1. Divide the track into 25 mini-sectors
        num_minisectors = 10
        total_distance = max(tel1['Distance'].max(), tel2['Distance'].max())
        sector_length = total_distance / num_minisectors

        # 2. Assign a sector number to each telemetry row
        tel1['MiniSector'] = (tel1['Distance'] // sector_length).astype(int)
        tel2['MiniSector'] = (tel2['Distance'] // sector_length).astype(int)

        # 3. Calculate average speed per sector for both drivers
        v1_avg = tel1.groupby('MiniSector')['Speed'].mean()
        v2_avg = tel2.groupby('MiniSector')['Speed'].mean()

        # 4. Determine the winner of each sector
        winner_list = []
        for i in range(num_minisectors + 1):
            speed1 = v1_avg.get(i, 0)
            speed2 = v2_avg.get(i, 0)
            winner_list.append(driver1 if speed1 > speed2 else driver2)

        # 5. Map the winner back to Driver 1's X/Y coordinates
        tel1['Winner'] = tel1['MiniSector'].apply(lambda x: winner_list[x] if x < len(winner_list) else driver1)

        # 6. Plot the Track Map using Markers
        fig_map = go.Figure()

        d1_data = tel1[tel1['Winner'] == driver1]
        fig_map.add_trace(go.Scatter(x=d1_data['X'], y=d1_data['Y'], mode='markers', name=f'{driver1} Faster',
                                     marker=dict(color='#00ffff', size=8)))

        d2_data = tel1[tel1['Winner'] == driver2]
        fig_map.add_trace(go.Scatter(x=d2_data['X'], y=d2_data['Y'], mode='markers', name=f'{driver2} Faster',
                                     marker=dict(color='#ff00ff', size=8)))

        fig_map.update_layout(
            title="Track Dominance (Mini-Sectors)",
            template='plotly_dark',
            # THIS IS CRITICAL: scaleanchor ensures the track doesn't look stretched or squished
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
    app.run(debug=False)