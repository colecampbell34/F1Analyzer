import dash
from dash import dcc, html
import dash_bootstrap_components as dbc

# --- 2. THE CONTROL PANEL (SIDEBAR) ---
sidebar = html.Div([
    html.H2("F1 AI Data", className="display-6", style={"fontSize": "1.5rem"}),
    html.Hr(),

    dbc.Label("Year", style={"fontSize": "0.9rem"}),
    dcc.Dropdown(id='year-dropdown', options=[{'label': str(y), 'value': y} for y in range(2018, 2027)], value=2026,
                 persistence=True, persistence_type='session', style={'color': 'black', 'fontSize': '0.9rem'}),
    html.Br(),

    dbc.Label("Grand Prix", style={"fontSize": "0.9rem"}),
    dcc.Dropdown(id='race-dropdown', persistence=True, persistence_type='session', style={'color': 'black', 'fontSize': '0.9rem'}),
    html.Br(),

    dbc.Label("Session", style={"fontSize": "0.9rem"}),
    dcc.Dropdown(id='session-dropdown', persistence=True, persistence_type='session', style={'color': 'black', 'fontSize': '0.9rem'}),
    html.Br(),

    dbc.Label("Driver 1", style={"fontSize": "0.9rem"}),
    dcc.Dropdown(id='driver1-dropdown', persistence=True, persistence_type='session', style={'color': 'black', 'fontSize': '0.9rem'}),
    html.Br(),

    dbc.Label("Driver 2", style={"fontSize": "0.9rem"}),
    dcc.Dropdown(id='driver2-dropdown', persistence=True, persistence_type='session', style={'color': 'black', 'fontSize': '0.9rem'}),
    html.Br(),
    html.Hr(),
    html.H4("Session Leaderboard", style={"fontSize": "1.2rem", "marginTop": "1rem"}),
    html.Div(id='leaderboard-container', style={'overflowY': 'auto', 'maxHeight': '30vh'})

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
                dcc.Store(id='session-context-store', data=''),
                dcc.Store(id='ai-response-store', storage_type='session', data={})
            ], style={'padding': '1.5rem', 'height': '75vh', 'overflowY': 'auto'})
        ], style={'backgroundColor': '#222', 'color': 'white'},
                selected_style={'backgroundColor': '#ff0000', 'color': 'white'})
    ])
], style={"padding": "1rem"})


app_layout = dbc.Container([
    dcc.Loading(
        id="fullscreen-loader",
        type="default",
        color="#ff0000",
        fullscreen=True,
        overlay_style={"visibility": "visible", "opacity": 1, "backgroundColor": "#000000"},
        children=[
            dbc.Row([dbc.Col(sidebar, width=2), dbc.Col(content, width=10)])
        ]
    )
], fluid=True, style={"padding": "0px"})
