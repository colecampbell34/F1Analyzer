from dash import dcc, html
import dash_bootstrap_components as dbc
from datetime import datetime
from graphs import GRAPH_CONFIG
from ai_utils import AI_ENABLED


# --- Tab graph height constants ---
TAB_HEIGHTS = {
    'single':       '75vh',
    'telemetry':    '68vh',
    'strategy_top': '40vh',
    'strategy_bot': '35vh',
    'race_top':     '42vh',
    'race_bot':     '33vh',
}

# --- Tab / style constants ---
TAB_STYLE          = {'backgroundColor': '#222', 'color': 'white'}
TAB_SELECTED_STYLE = {'backgroundColor': '#ff0000', 'color': 'white'}


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


# --- Reusable driver selector (dropdown + teammate button) ---
def _driver_selector(label, dropdown_id, btn_id):
    return html.Div([
        dbc.Label(label, style={"fontSize": "0.9rem"}),
        html.Div([
            html.Div(
                dcc.Dropdown(id=dropdown_id, persistence=True, persistence_type='session',
                             style={'color': 'black', 'fontSize': '0.9rem'}),
                style={'flex': '1'}
            ),
            dbc.Button("⇄", id=btn_id, color='secondary', size='sm', n_clicks=0,
                       title='Select Teammate',
                       style={'marginLeft': '4px', 'padding': '4px 8px', 'fontSize': '0.8rem'}),
            html.Span("Teammate", className='teammate-label',
                      style={'fontSize': '0.65rem', 'color': '#888', 'marginLeft': '2px',
                             'display': 'none'}),
        ], style={'display': 'flex', 'alignItems': 'center'}),
    ], style={'marginBottom': '0.75rem'})


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
                 style={'color': 'black', 'fontSize': '0.9rem', 'marginBottom': '0.75rem'}),

    dbc.Label("Grand Prix", style={"fontSize": "0.9rem"}),
    dcc.Loading(type='dot', color='#ff0000', children=[
        dcc.Dropdown(id='race-dropdown', persistence=True, persistence_type='session',
                     style={'color': 'black', 'fontSize': '0.9rem', 'marginBottom': '0.75rem'}),
    ]),

    dbc.Label("Session", style={"fontSize": "0.9rem"}),
    dcc.Loading(type='dot', color='#ff0000', children=[
        dcc.Dropdown(id='session-dropdown', persistence=True, persistence_type='session',
                     style={'color': 'black', 'fontSize': '0.9rem', 'marginBottom': '0.75rem'}),
    ]),

    # Driver selectors
    _driver_selector("Driver 1", 'driver1-dropdown', 'teammate1-btn'),
    _driver_selector("Driver 2", 'driver2-dropdown', 'teammate2-btn'),

    dbc.Button("Update Dashboard", id='update-dashboard-btn', color='success', size='sm', n_clicks=0,
               style={'fontWeight': 'bold', 'width': '100%', 'marginTop': '5px', 'marginBottom': '10px'}),
    html.Hr(),
    html.H4("Session Leaderboard", style={"fontSize": "1.1rem", "marginTop": "0.5rem", "marginBottom": "0rem"}),
    dbc.Button("Update Leaderboard", id='update-leaderboard-btn', color='success', size='sm', n_clicks=0,
               style={'fontWeight': 'bold', 'width': '100%', 'marginTop': '5px', 'marginBottom': '10px'}),
    html.Div([
        dcc.Loading(type='dot', color='#ff0000', children=[
            html.Div(id='leaderboard-container')
        ])
    ], style={'overflowY': 'auto', 'overflowX': 'hidden', 'scrollbarGutter': 'stable', 'flex': '1', 'minHeight': '0'})

], style={"padding": "1rem", "backgroundColor": "#111111", "height": "100vh", "overflowY": "hidden",
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


content = html.Div([
    html.H3("Session Telemetry Analysis", className="text-center mt-2", id='main-title'),
    html.Hr(),

    dcc.Tabs(id='main-tabs', value='tab-telemetry', children=[
        dcc.Tab(label='Telemetry', value='tab-telemetry', children=[
            telemetry_controls,
            dcc.Loading(type='circle', color='#ff0000', children=[
                _empty_state('speed-graph', TAB_HEIGHTS['telemetry'])
            ])
        ], style=TAB_STYLE, selected_style=TAB_SELECTED_STYLE),

        dcc.Tab(label='Track Map', value='tab-trackmap', children=[
            dcc.Loading(type='circle', color='#ff0000', children=[
                _empty_state('2d-dominance-graph', TAB_HEIGHTS['single'])
            ])
        ], style=TAB_STYLE, selected_style=TAB_SELECTED_STYLE),

        dcc.Tab(label='Strategy', value='tab-strategy', children=[
            dcc.Loading(type='circle', color='#ff0000', children=[
                _empty_state('strategy-graph', TAB_HEIGHTS['strategy_top'])
            ]),
            dcc.Loading(type='circle', color='#ff0000', children=[
                _empty_state('deg-graph', TAB_HEIGHTS['strategy_bot'])
            ])
        ], style=TAB_STYLE, selected_style=TAB_SELECTED_STYLE),

        dcc.Tab(label='Race', value='tab-race', children=[
            dcc.Loading(type='circle', color='#ff0000', children=[
                _empty_state('race-gaps-graph', TAB_HEIGHTS['race_top'])
            ]),
            dcc.Loading(type='circle', color='#ff0000', children=[
                _empty_state('pit-stops-graph', TAB_HEIGHTS['race_bot'])
            ])
        ], style=TAB_STYLE, selected_style=TAB_SELECTED_STYLE),

        dcc.Tab(label='Grid Pace', value='tab-gridpace', children=[
            dcc.Loading(type='circle', color='#ff0000', children=[
                _empty_state('grid-pace-graph', TAB_HEIGHTS['single'])
            ])
        ], style=TAB_STYLE, selected_style=TAB_SELECTED_STYLE),

        dcc.Tab(label='AI Analysis', value='tab-ai', children=[
            html.Div([
                html.Div([
                    dbc.InputGroup([
                        dbc.Input(id='ai-question-input', type='text',
                                  placeholder='Ask about this session... (e.g. "Why was NOR faster in sector 2?")',
                                  n_submit=0,
                                  style={'backgroundColor': '#1a1a1a', 'color': 'white', 'border': '1px solid #444',
                                         'fontSize': '0.95rem'},
                                  disabled=not AI_ENABLED),
                        dbc.Button('Ask AI', id='ai-ask-button', color='danger', n_clicks=0,
                                   style={'fontWeight': 'bold'},
                                   disabled=not AI_ENABLED)
                    ], style={'marginBottom': '1rem'}),
                ], style={'padding': '0.5rem 0'}),
                dcc.Loading(
                    type='default', color='#ff0000',
                    children=html.Div(id='ai-response-output',
                                      style={'padding': '1rem', 'minHeight': '200px',
                                             'backgroundColor': '#1a1a1a', 'borderRadius': '8px',
                                             'border': '1px solid #333', 'whiteSpace': 'pre-wrap',
                                             'lineHeight': '1.6', 'fontSize': '0.95rem',
                                             'maxHeight': '70vh', 'overflowY': 'auto'})
                ),
                html.Hr(style={'borderColor': '#333'}),
                html.Div([
                    html.Div([
                        dbc.Button("Refresh Inbox", id='refresh-feedback-review-btn', color='secondary',
                                   outline=True, size='sm', n_clicks=0, className='me-2'),
                        dbc.Button("Download CSV", id='download-feedback-btn', color='danger',
                                   size='sm', n_clicks=0)
                    ], id='feedback-review-controls', style={'display': 'none', 'marginBottom': '1rem'}),
                    html.Div(id='feedback-review-panel')
                ]),
                dcc.Store(id='session-context-store', data=''),
                dcc.Store(id='ai-history-store', storage_type='session', data=[]),
                dcc.Store(id='ai-history-index-store', storage_type='session', data=0),
                # Hidden placeholders for nav buttons (rendered dynamically in callbacks)
                html.Div([
                    dbc.Button(id='ai-prev-btn', style={'display': 'none'}, n_clicks=0),
                    dbc.Button(id='ai-next-btn', style={'display': 'none'}, n_clicks=0),
                ], style={'display': 'none'})
            ], style={'padding': '1.5rem', 'height': TAB_HEIGHTS['single'], 'overflowY': 'auto'})
        ], style=TAB_STYLE, selected_style=TAB_SELECTED_STYLE)
    ])
], style={"padding": "1rem"})


app_layout = dbc.Container([
    dcc.Location(id='url', refresh=False),
    dbc.Row([
        dbc.Col(sidebar, md=2, xs=12, style={'height': '100vh', 'overflow': 'hidden'}),
        dbc.Col(content, md=10, xs=12, style={'height': '100vh', 'overflow': 'hidden'})
    ], className='g-0', style={'height': '100vh', 'margin': '0'}),
    dbc.Button("Send Feedback", id='open-feedback-modal-btn', color='danger', n_clicks=0,
               className='feedback-fab'),
    dbc.Modal([
        dbc.ModalHeader(dbc.ModalTitle("Send Feedback")),
        dbc.ModalBody([
            html.P(
                "Tell me what broke, what felt confusing, or what you want added. "
                "The current session and tab are attached automatically.",
                style={'color': '#bbb', 'marginBottom': '1rem'}
            ),
            dbc.Row([
                dbc.Col([
                    dbc.Label("Feedback Type", style={'fontSize': '0.85rem'}),
                    dbc.Select(
                        id='feedback-category',
                        options=[
                            {'label': 'Bug Report', 'value': 'bug'},
                            {'label': 'Feature Request', 'value': 'feature'},
                            {'label': 'Data Issue', 'value': 'data'},
                            {'label': 'General Feedback', 'value': 'general'}
                        ],
                        value='bug',
                        style={'backgroundColor': '#1a1a1a', 'color': 'white', 'border': '1px solid #444'}
                    )
                ], md=7, xs=12),
                dbc.Col([
                    dbc.Label("Experience Rating", style={'fontSize': '0.85rem'}),
                    dbc.Select(
                        id='feedback-rating',
                        options=[
                            {'label': '5 - Excellent', 'value': 5},
                            {'label': '4 - Good', 'value': 4},
                            {'label': '3 - Mixed', 'value': 3},
                            {'label': '2 - Poor', 'value': 2},
                            {'label': '1 - Broken', 'value': 1}
                        ],
                        value=3,
                        style={'backgroundColor': '#1a1a1a', 'color': 'white', 'border': '1px solid #444'}
                    )
                ], md=5, xs=12)
            ], className='g-2'),
            html.Div([
                dbc.Label("What happened?", style={'fontSize': '0.85rem', 'marginTop': '1rem'}),
                dbc.Textarea(
                    id='feedback-message',
                    placeholder='Example: The track map failed to load for 2025 Japan FP2 after I selected VER vs TSU.',
                    style={'backgroundColor': '#1a1a1a', 'color': '#eee', 'border': '1px solid #444',
                           'minHeight': '170px'}
                )
            ]),
            html.Div([
                dbc.Label("Contact (optional)", style={'fontSize': '0.85rem', 'marginTop': '1rem'}),
                dbc.Input(
                    id='feedback-contact',
                    type='text',
                    placeholder='Email if you want follow-up',
                    style={'backgroundColor': '#1a1a1a', 'color': '#eee', 'border': '1px solid #444'}
                )
            ]),
            dbc.Alert(id='feedback-submit-alert', is_open=False, duration=5000, style={'marginTop': '1rem'})
        ]),
        dbc.ModalFooter([
            dbc.Button("Cancel", id='cancel-feedback-btn', color='secondary', outline=True, n_clicks=0),
            dbc.Button("Submit Feedback", id='submit-feedback-btn', color='danger', n_clicks=0)
        ])
    ], id='feedback-modal', is_open=False, size='lg', centered=True),
    dcc.Store(id='dashboard-params-store', storage_type='session'),
    dcc.Store(id='feedback-refresh-store'),
    dcc.Download(id='feedback-download'),
    dcc.ConfirmDialog(id='error-dialog', message='')
], fluid=True, style={"padding": "0px", "height": "100vh", "overflow": "hidden"})
