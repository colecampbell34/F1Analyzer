import dash
from dash import dcc, html
import dash_bootstrap_components as dbc
from datetime import datetime
from graphs import GRAPH_CONFIG
from ai_utils import GEMINI_API_KEY

# --- Reusable empty-state placeholder ---
def _empty_state(graph_id, height='68vh'):
    """Returns a graph with a friendly empty-state message instead of a blank chart."""
    return dcc.Graph(
        id=graph_id,
        style={'height': height},
        config=GRAPH_CONFIG,
        figure={
            'data': [],
            'layout': {
                'template': 'plotly_dark',
                'xaxis': {'visible': False},
                'yaxis': {'visible': False},
                'annotations': [{
                    'text': 'Select a session and two drivers, then click "Update Dashboard"<br><br><span style="font-size: 13px; color: #888;"><i>Note: Loading a session for the very first time<br>may take up to a minute to cache the raw telemetry.</i></span>',
                    'showarrow': False,
                    'font': {'size': 16, 'color': '#ccc'},
                    'xref': 'paper', 'yref': 'paper', 'x': 0.5, 'y': 0.5
                }]
            }
        }
    )


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
    dcc.Loading(type='dot', color='#ff0000', children=[
        dcc.Dropdown(id='race-dropdown', persistence=True, persistence_type='session',
                     style={'color': 'black', 'fontSize': '0.9rem'}),
    ]),
    html.Br(),

    dbc.Label("Session", style={"fontSize": "0.9rem"}),
    dcc.Loading(type='dot', color='#ff0000', children=[
        dcc.Dropdown(id='session-dropdown', persistence=True, persistence_type='session',
                     style={'color': 'black', 'fontSize': '0.9rem'}),
    ]),
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
        html.Span("Teammate", className='teammate-label',
                  style={'fontSize': '0.65rem', 'color': '#888', 'marginLeft': '2px',
                         'display': 'none'}),
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
        html.Span("Teammate", className='teammate-label',
                  style={'fontSize': '0.65rem', 'color': '#888', 'marginLeft': '2px',
                         'display': 'none'}),
    ], style={'display': 'flex', 'alignItems': 'center'}),
    html.Br(),
    dbc.Button("Update Dashboard", id='update-dashboard-btn', color='success', size='sm', n_clicks=0,
               style={'fontWeight': 'bold', 'width': '100%', 'marginTop': '5px', 'marginBottom': '10px'}),
    html.Br(),
    html.Hr(),
    html.H4("Session Leaderboard", style={"fontSize": "1.1rem", "marginTop": "0.5rem"}),
    html.Div(id='leaderboard-container', style={'overflowY': 'auto', 'flex': '1', 'minHeight': '0'})

], style={"padding": "1rem", "background-color": "#111111", "height": "100vh", "overflowY": "auto",
          "display": "flex", "flexDirection": "column"})


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

        dcc.Tabs(id='main-tabs', value='tab-telemetry', children=[
            dcc.Tab(label='Telemetry', value='tab-telemetry', children=[
                telemetry_controls,
                dcc.Loading(type='circle', color='#ff0000', children=[
                    _empty_state('speed-graph', '68vh')
                ])
            ], style=tab_style, selected_style=tab_selected_style),

            dcc.Tab(label='Track Map', value='tab-trackmap', children=[
                dcc.Loading(type='circle', color='#ff0000', children=[
                    _empty_state('2d-dominance-graph', '75vh')
                ])
            ], style=tab_style, selected_style=tab_selected_style),

            dcc.Tab(label='Strategy', value='tab-strategy', children=[
                dcc.Loading(type='circle', color='#ff0000', children=[
                    _empty_state('strategy-graph', '40vh'),
                    _empty_state('deg-graph', '35vh')
                ])
            ], style=tab_style, selected_style=tab_selected_style),

            dcc.Tab(label='Race', value='tab-race', children=[
                dcc.Loading(type='circle', color='#ff0000', children=[
                    _empty_state('race-gaps-graph', '42vh'),
                    _empty_state('pit-stops-graph', '33vh')
                ])
            ], style=tab_style, selected_style=tab_selected_style),

            dcc.Tab(label='Grid Pace', value='tab-gridpace', children=[
                dcc.Loading(type='circle', color='#ff0000', children=[
                    _empty_state('grid-pace-graph', '75vh')
                ])
            ], style=tab_style, selected_style=tab_selected_style),

            dcc.Tab(label='AI Analysis', value='tab-ai', children=[
                html.Div([
                    html.Div([
                        dbc.InputGroup([
                            dbc.Input(id='ai-question-input', type='text',
                                      placeholder='Ask about this session... (e.g. "Why was NOR faster in sector 2?")',
                                      n_submit=0,
                                      style={'backgroundColor': '#1a1a1a', 'color': 'white', 'border': '1px solid #444',
                                             'fontSize': '0.95rem'},
                                      disabled=not GEMINI_API_KEY),
                            dbc.Button('Ask AI', id='ai-ask-button', color='danger', n_clicks=0,
                                       style={'fontWeight': 'bold'},
                                       disabled=not GEMINI_API_KEY)
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
    dbc.Row([
        dbc.Col(sidebar, md=2, xs=12),
        dbc.Col(content, md=10, xs=12)
    ]),
    dcc.Store(id='dashboard-params-store', storage_type='session'),
    dcc.ConfirmDialog(id='error-dialog', message='')
], fluid=True, style={"padding": "0px"})
