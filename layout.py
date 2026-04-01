import dash
from dash import dcc, html
import dash_bootstrap_components as dbc
from datetime import datetime
from graphs import GRAPH_CONFIG

# --- CONTROL PANEL (SIDEBAR) ---
sidebar = html.Div([
    html.H2("F1 Analyzer", className="display-6", style={"fontSize": "1.4rem", "fontWeight": "bold"}),
    html.P("Session Analysis Dashboard", style={"fontSize": "0.75rem", "color": "#888", "marginBottom": "0.5rem"}),
    html.Hr(),

    dbc.Label("Year", style={"fontSize": "0.9rem"}),
    dcc.Dropdown(id='year-dropdown',
                 options=[{'label': str(y), 'value': y} for y in range(2018, datetime.now().year + 1)],
                 value=datetime.now().year,
                 persistence=True, persistence_type='session',
                 style={'color': 'black', 'fontSize': '0.9rem'}),
    html.Br(),

    dbc.Label("Grand Prix", style={"fontSize": "0.9rem"}),
    dcc.Dropdown(id='race-dropdown', persistence=True, persistence_type='session',
                 style={'color': 'black', 'fontSize': '0.9rem'}),
    html.Br(),

    dbc.Label("Session", style={"fontSize": "0.9rem"}),
    dcc.Dropdown(id='session-dropdown', persistence=True, persistence_type='session',
                 style={'color': 'black', 'fontSize': '0.9rem'}),
    html.Br(),

    # Driver 1 + Teammate Button
    dbc.Label("Driver 1", style={"fontSize": "0.9rem"}),
    html.Div([
        html.Div(dcc.Dropdown(id='driver1-dropdown', persistence=True, persistence_type='session',
                               style={'color': 'black', 'fontSize': '0.9rem'}),
                 style={'flex': '1'}),
        dbc.Button("⇄", id='teammate1-btn', color='secondary', size='sm', n_clicks=0,
                   title='Select Teammate',
                   style={'marginLeft': '4px', 'padding': '4px 8px', 'fontSize': '0.8rem'}),
    ], style={'display': 'flex', 'alignItems': 'center'}),
    html.Br(),

    # Driver 2 + Teammate Button
    dbc.Label("Driver 2", style={"fontSize": "0.9rem"}),
    html.Div([
        html.Div(dcc.Dropdown(id='driver2-dropdown', persistence=True, persistence_type='session',
                               style={'color': 'black', 'fontSize': '0.9rem'}),
                 style={'flex': '1'}),
        dbc.Button("⇄", id='teammate2-btn', color='secondary', size='sm', n_clicks=0,
                   title='Select Teammate',
                   style={'marginLeft': '4px', 'padding': '4px 8px', 'fontSize': '0.8rem'}),
    ], style={'display': 'flex', 'alignItems': 'center'}),
    html.Br(),
    html.Hr(),
    html.H4("Session Leaderboard", style={"fontSize": "1.1rem", "marginTop": "0.5rem"}),
    html.Div(id='leaderboard-container', style={'overflowY': 'auto', 'maxHeight': '30vh'})

], style={"padding": "1rem", "background-color": "#111111", "height": "100vh", "overflowY": "auto"})


# --- MAIN VIEWING AREA ---
# Lap selection row for Telemetry tab
telemetry_controls = html.Div([
    dbc.Row([
        dbc.Col([
            dbc.Label("Driver 1 Lap:", style={"fontSize": "0.8rem", "color": "#aaa", "marginRight": "0.5rem"}),
            dbc.RadioItems(id='d1-lap-mode',
                           options=[{'label': 'Fastest', 'value': 'fastest'},
                                    {'label': 'Lap #', 'value': 'specific'}],
                           value='fastest', inline=True,
                           style={"fontSize": "0.8rem"},
                           inputStyle={"marginRight": "4px"},
                           labelStyle={"marginRight": "12px", "color": "#ccc"}),
            dbc.Input(id='d1-lap-number', type='number', placeholder='Lap #', size='sm',
                      style={'width': '70px', 'display': 'inline-block', 'marginLeft': '6px',
                             'backgroundColor': '#222', 'color': 'white', 'border': '1px solid #444',
                             'fontSize': '0.8rem'}),
        ], md=5, xs=12, style={'display': 'flex', 'alignItems': 'center', 'flexWrap': 'wrap', 'marginBottom': '0.5rem'}),
        dbc.Col([
            dbc.Label("Driver 2 Lap:", style={"fontSize": "0.8rem", "color": "#aaa", "marginRight": "0.5rem"}),
            dbc.RadioItems(id='d2-lap-mode',
                           options=[{'label': 'Fastest', 'value': 'fastest'},
                                    {'label': 'Lap #', 'value': 'specific'}],
                           value='fastest', inline=True,
                           style={"fontSize": "0.8rem"},
                           inputStyle={"marginRight": "4px"},
                           labelStyle={"marginRight": "12px", "color": "#ccc"}),
            dbc.Input(id='d2-lap-number', type='number', placeholder='Lap #', size='sm',
                      style={'width': '70px', 'display': 'inline-block', 'marginLeft': '6px',
                             'backgroundColor': '#222', 'color': 'white', 'border': '1px solid #444',
                             'fontSize': '0.8rem'}),
        ], md=5, xs=12, style={'display': 'flex', 'alignItems': 'center', 'flexWrap': 'wrap', 'marginBottom': '0.5rem'}),
        dbc.Col([
            dbc.Button("Update Laps", id='update-laps-btn', color='danger', size='sm', n_clicks=0,
                       style={'fontWeight': 'bold', 'width': '100%'})
        ], md=2, xs=12, style={'display': 'flex', 'alignItems': 'center', 'marginBottom': '0.5rem'})
    ])
], style={'padding': '0.5rem 1rem', 'backgroundColor': '#1a1a1a', 'borderRadius': '6px',
          'marginBottom': '0.5rem', 'border': '1px solid #333'})


tab_style = {'backgroundColor': '#222', 'color': 'white'}
tab_selected_style = {'backgroundColor': '#ff0000', 'color': 'white'}

content = html.Div([
    html.H3("Session Telemetry Analysis", className="text-center mt-2", id='main-title'),
    html.Hr(),

    dcc.Tabs([
        dcc.Tab(label='Telemetry Traces', children=[
            telemetry_controls,
            dcc.Loading(type='circle', color='#ff0000', children=[
                dcc.Graph(id='speed-graph', style={'height': '68vh'}, config=GRAPH_CONFIG)
            ])
        ], style=tab_style, selected_style=tab_selected_style),

        dcc.Tab(label='Track Dominance', children=[
            dcc.Loading(type='circle', color='#ff0000', children=[
                dcc.Graph(id='2d-dominance-graph', style={'height': '75vh'}, config=GRAPH_CONFIG)
            ])
        ], style=tab_style, selected_style=tab_selected_style),

        dcc.Tab(label='Strategy & Tyres', children=[
            dcc.Loading(type='circle', color='#ff0000', children=[
                dcc.Graph(id='strategy-graph', style={'height': '40vh'}, config=GRAPH_CONFIG),
                dcc.Graph(id='deg-graph', style={'height': '35vh'}, config=GRAPH_CONFIG)
            ])
        ], style=tab_style, selected_style=tab_selected_style),

        dcc.Tab(label='Race Analysis', children=[
            dcc.Loading(type='circle', color='#ff0000', children=[
                dcc.Graph(id='race-gaps-graph', style={'height': '42vh'}, config=GRAPH_CONFIG),
                dcc.Graph(id='pit-stops-graph', style={'height': '33vh'}, config=GRAPH_CONFIG)
            ])
        ], style=tab_style, selected_style=tab_selected_style),

        dcc.Tab(label='Grid Overview', children=[
            dcc.Loading(type='circle', color='#ff0000', children=[
                dcc.Graph(id='grid-pace-graph', style={'height': '75vh'}, config=GRAPH_CONFIG)
            ])
        ], style=tab_style, selected_style=tab_selected_style),

        dcc.Tab(label='AI Analysis', children=[
            html.Div([
                html.Div([
                    dbc.InputGroup([
                        dbc.Input(id='ai-question-input', type='text',
                                  placeholder='Ask about this session... (e.g. "Why was NOR faster in sector 2?")',
                                  n_submit=0,
                                  style={'backgroundColor': '#1a1a1a', 'color': 'white', 'border': '1px solid #444',
                                         'fontSize': '0.95rem'}),
                        dbc.Button('Ask AI', id='ai-ask-button', color='danger', n_clicks=0,
                                   style={'fontWeight': 'bold'})
                    ], style={'marginBottom': '1rem'}),
                ], style={'padding': '0.5rem 0'}),
                dcc.Loading(
                    type='default', color='#ff0000',
                    children=html.Div(id='ai-response-output',
                                      style={'padding': '1rem', 'minHeight': '200px',
                                             'backgroundColor': '#1a1a1a', 'borderRadius': '8px',
                                             'border': '1px solid #333', 'whiteSpace': 'pre-wrap',
                                             'lineHeight': '1.6', 'fontSize': '0.95rem',
                                             'maxHeight': '50vh', 'overflowY': 'auto'})
                ),
                # Session Notes (non-intrusive, collapsible)
                html.Hr(style={'borderColor': '#333'}),
                dbc.Button("📝 Session Notes", id='toggle-notes-btn', color='link', n_clicks=0,
                           style={'color': '#888', 'fontSize': '0.85rem', 'padding': '0', 'textDecoration': 'none'}),
                dbc.Collapse(
                    dbc.Textarea(id='session-notes', placeholder='Personal notes for this session...',
                                 style={'backgroundColor': '#1a1a1a', 'color': '#ccc', 'border': '1px solid #333',
                                        'fontSize': '0.85rem', 'minHeight': '80px', 'marginTop': '0.5rem'},
                                 persistence=True, persistence_type='session'),
                    id='notes-collapse', is_open=False
                ),
                dcc.Store(id='session-context-store', data=''),
                dcc.Store(id='ai-history-store', storage_type='session', data=[])
            ], style={'padding': '1.5rem', 'height': '75vh', 'overflowY': 'auto'})
        ], style=tab_style, selected_style=tab_selected_style)
    ])
], style={"padding": "1rem"})


app_layout = dbc.Container([
    dcc.Loading(
        id="fullscreen-loader",
        type="default",
        color="#ff0000",
        fullscreen=True,
        overlay_style={"visibility": "visible", "opacity": 0.7, "backgroundColor": "#111111"},
        children=[
            dbc.Row([
                dbc.Col(sidebar, md=2, xs=12),
                dbc.Col(content, md=10, xs=12)
            ])
        ]
    ),
    dcc.ConfirmDialog(id='error-dialog', message='')
], fluid=True, style={"padding": "0px"})
