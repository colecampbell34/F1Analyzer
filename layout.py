from dash import dcc, html
import dash_bootstrap_components as dbc
from datetime import datetime
from graph_shared import GRAPH_CONFIG
from ai_utils import AI_ENABLED


# Tab graph heights by view.
TAB_HEIGHTS = {
    'single':       '75vh',
    'telemetry':    '68vh',
    'strategy_top': '40vh',
    'strategy_bot': '35vh',
    'race_top':     '42vh',
    'race_bot':     '33vh',
}

# Shared disclaimer.
DISCLAIMER = html.Div([
    html.Span("Note: F1 data can occasionally be missing or incomplete for specific stints/laps due to session recording issues.",
              style={'fontSize': '0.75rem', 'color': '#888', 'fontStyle': 'italic'})
], style={'textAlign': 'center', 'marginBottom': '0.5rem'})

# Shared tab styles.
TAB_STYLE          = {'backgroundColor': '#222', 'color': 'white'}
TAB_SELECTED_STYLE = {'backgroundColor': '#ff0000', 'color': 'white'}


# Reusable empty-state graph placeholder.
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


# Reusable driver selector with teammate shortcut.
def _driver_selector(label, dropdown_id, btn_id):
    return html.Div([
        dbc.Label(label, style={"fontSize": "0.9rem"}),
        html.Div([
            html.Div(
                dcc.Dropdown(id=dropdown_id, persistence=True, persistence_type='session',
                             searchable=True,
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


# Sidebar control panel.
sidebar = html.Div([
    # Fixed Header
    html.Div([
        html.H2("F1 Analyzer", className="display-6", style={"fontSize": "1.4rem", "fontWeight": "bold"}),
        html.P("Session Analysis Dashboard", style={"fontSize": "0.75rem", "color": "#888", "marginBottom": "0.5rem"}),
        html.Hr(style={'margin': '0.5rem 0'}),
    ], style={'flex': '0 0 auto'}),

    # Scrollable Content (Controls + Leaderboard)
    html.Div([
        dbc.Label("Year", style={"fontSize": "0.9rem"}),
        dcc.Dropdown(id='year-dropdown',
                     options=[{'label': str(y), 'value': y} for y in range(2018, datetime.now().year + 1)],
                     value=datetime.now().year,
                     persistence=True, persistence_type='session',
                     searchable=True,
                     style={'color': 'black', 'fontSize': '0.9rem', 'marginBottom': '0.75rem'}),

        dbc.Label("Grand Prix", style={"fontSize": "0.9rem"}),
        dcc.Loading(type='dot', color='#ff0000', children=[
            dcc.Dropdown(id='race-dropdown', persistence=True, persistence_type='session',
                         searchable=True,
                         style={'color': 'black', 'fontSize': '0.9rem', 'marginBottom': '0.75rem'}),
        ]),

        dbc.Label("Session", style={"fontSize": "0.9rem"}),
        dcc.Loading(type='dot', color='#ff0000', children=[
            dcc.Dropdown(id='session-dropdown', persistence=True, persistence_type='session',
                         searchable=True,
                         style={'color': 'black', 'fontSize': '0.9rem', 'marginBottom': '0.75rem'}),
        ]),
        dbc.Button([html.I(className="fas fa-history me-2"), "Latest Race"],
                   id='latest-race-btn', color='danger', size='sm', n_clicks=0,
                   title='Select the most recent completed race and default to the top two drivers',
                   style={'width': '100%', 'fontWeight': 'bold', 'marginBottom': '0.75rem'}),

        # Driver selectors.
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
        ], style={'minHeight': '0'})
    ], style={'flex': '1 1 auto', 'overflowY': 'auto', 'paddingRight': '5px', 'marginBottom': '1rem'}),

    # Fixed Footer
    html.Div([
        html.Hr(style={'margin': '0.5rem 0'}),
        dbc.Button([html.I(className="fas fa-share-alt me-2"), "Share Comparison"],
                   id='share-btn', color='info', size='sm', n_clicks=0,
                   style={'width': '100%', 'fontWeight': 'bold', 'marginBottom': '10px'}),
        html.Div([
            html.A(html.I(className="fab fa-github fa-lg"), href="https://github.com/colecampbell34/F1Analyzer", target="_blank", style={'color': '#888', 'marginRight': '15px'}),
            html.A(html.I(className="fab fa-twitter fa-lg"), href="https://twitter.com/intent/tweet?text=Check%20out%20this%20F1%20Analysis!&url=https://f-1-analyzer--colecampbell34.replit.app", target="_blank", style={'color': '#888', 'marginRight': '15px'}),
            html.A(html.I(className="fab fa-reddit fa-lg"), href="https://reddit.com/submit?url=https://f-1-analyzer--colecampbell34.replit.app&title=Advanced%20F1%20Telemetry%20Dashboard", target="_blank", style={'color': '#888'}),
        ], style={'textAlign': 'center', 'paddingBottom': '5px'})
    ], style={'flex': '0 0 auto'})

], style={"padding": "1rem", "backgroundColor": "#111111", "height": "100vh",
          "display": "flex", "flexDirection": "column", "overflow": "hidden"})



# Main viewing area.
# Telemetry lap-selection row.
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
    ]),
    dbc.Row([
        dbc.Col([
            dbc.Button("Play Lap", id='play-lap-btn', color='secondary', size='sm', n_clicks=0,
                       style={'fontWeight': 'bold', 'width': '100%'})
        ], md=2, xs=12, style={'display': 'flex', 'alignItems': 'center', 'marginTop': '0.35rem'}),
        dbc.Col([
            dbc.Button("Pause", id='pause-resume-lap-btn', color='secondary', outline=True, size='sm', n_clicks=0,
                       style={'fontWeight': 'bold', 'width': '100%'})
        ], md=2, xs=12, style={'display': 'flex', 'alignItems': 'center', 'marginTop': '0.35rem'}),
        dbc.Col([
            html.Div("Lap Time: 0.00s / 0.00s", id='lap-playback-time-label',
                     style={'color': '#aaa', 'fontSize': '0.82rem', 'width': '100%'})
        ], md=4, xs=12, style={'display': 'flex', 'alignItems': 'center', 'marginTop': '0.35rem'})
    ])
], style={'padding': '0.5rem 1rem', 'backgroundColor': '#1a1a1a', 'borderRadius': '6px',
          'marginBottom': '0.5rem', 'border': '1px solid #333'})


content = html.Div([
    html.H3("Session Telemetry Analysis", className="text-center mt-2", id='main-title'),
    html.Hr(),

    dcc.Tabs(id='main-tabs', value='tab-telemetry', children=[
        dcc.Tab(id='tab-telemetry-control', label='Telemetry', value='tab-telemetry', children=[
            DISCLAIMER,
            telemetry_controls,
            dbc.Row([
                dbc.Col([
                    dcc.Loading(type='dot', color='#ff0000', children=[
                        _empty_state('speed-graph', TAB_HEIGHTS['telemetry'])
                    ])
                ], lg=9, md=8, xs=12),
                dbc.Col([
                    html.Div("Track Position", style={'textAlign': 'center', 'color': '#888', 'fontSize': '0.7rem', 'marginBottom': '3px'}),
                    # Live Telemetry Dashboard
                    html.Div(id='live-telemetry-dashboard', className='live-dashboard-container', style={'display': 'none'}, children=[
                        html.Div(className='live-driver-row d1-row', children=[
                            html.Div(id='live-d1-name', className='live-driver-name'),
                            html.Div(className='live-stats', children=[
                                html.Div([html.Span(id='live-d1-speed', className='stat-val'), html.Small(" KM/H")], className='stat-item'),
                                html.Div([html.Span(id='live-d1-gear', className='stat-val'), html.Small(" G")], className='stat-item'),
                                html.Div([html.Span(id='live-d1-rpm', className='stat-val'), html.Small(" RPM")], className='stat-item'),
                            ])
                        ]),
                        html.Div(id='live-delta-row', className='live-delta-row', children=[
                            html.Span("GAP", className='delta-label'),
                            html.Span(id='live-delta-value', className='delta-value')
                        ]),
                        html.Div(className='live-driver-row d2-row', children=[
                            html.Div(id='live-d2-name', className='live-driver-name'),
                            html.Div(className='live-stats', children=[
                                html.Div([html.Span(id='live-d2-speed', className='stat-val'), html.Small(" KM/H")], className='stat-item'),
                                html.Div([html.Span(id='live-d2-gear', className='stat-val'), html.Small(" G")], className='stat-item'),
                                html.Div([html.Span(id='live-d2-rpm', className='stat-val'), html.Small(" RPM")], className='stat-item'),
                            ])
                        ]),
                    ]),
                    dcc.Graph(id='mini-track-map', style={'height': '200px'}, config={'displayModeBar': False}),
                    html.Hr(style={'margin': '6px 0'}),
                    html.Div("G-Force Traces", style={
                        'textAlign': 'center',
                        'color': '#888',
                        'fontSize': '0.7rem',
                        'marginBottom': '3px'
                    }),
                    dcc.Graph(id='gg-diagram', style={'height': '250px'}, config={'displayModeBar': False})
                ], lg=3, md=4, xs=12, className='telemetry-sidecar',
                   style={'backgroundColor': '#151515', 'borderRadius': '8px', 'padding': '8px', 'marginTop': '6px', 'overflow': 'hidden'})
            ])
        ], style=TAB_STYLE, selected_style=TAB_SELECTED_STYLE),

        dcc.Tab(id='tab-trackmap-control', label='Track Map', value='tab-trackmap', children=[
            DISCLAIMER,
            html.Div([
                dbc.Label("Overlay Mode:", style={"fontSize": "0.8rem", "color": "#aaa", "marginRight": "10px"}),
                dbc.RadioItems(
                    id='trackmap-mode',
                    options=[
                        {'label': 'Dominance', 'value': 'dominance'},
                        {'label': 'Braking', 'value': 'braking'},
                        {'label': 'Speed', 'value': 'speed'}
                    ],
                    value='dominance',
                    inline=True,
                    style={"fontSize": "0.8rem"},
                    inputStyle={"marginRight": "4px"},
                    labelStyle={"marginRight": "15px", "color": "#ccc"}
                ),
            ], style={'padding': '5px 15px', 'backgroundColor': '#1a1a1a', 'borderRadius': '6px', 'marginBottom': '0.5rem', 'display': 'flex', 'alignItems': 'center'}),
            dbc.Row([
                dbc.Col([
                    dcc.Loading(type='dot', color='#ff0000', children=[
                        _empty_state('2d-dominance-graph', TAB_HEIGHTS['single'])
                    ])
                ], lg=9, md=8, xs=12),
                dbc.Col([
                    html.Div(id='driver-dna-container', style={'flex': '1 1 auto', 'minHeight': 0})
                ], lg=3, md=4, xs=12, style={
                    'height': TAB_HEIGHTS['single'],
                    'display': 'flex',
                    'flexDirection': 'column',
                    'gap': '0.75rem'
                })
            ])
        ], style=TAB_STYLE, selected_style=TAB_SELECTED_STYLE),

        dcc.Tab(id='tab-strategy-control', label='Strategy', value='tab-strategy', children=[
            DISCLAIMER,
            dcc.Loading(type='dot', color='#ff0000', children=[
                _empty_state('strategy-graph', TAB_HEIGHTS['strategy_top'])
            ]),
            dcc.Loading(type='dot', color='#ff0000', children=[
                _empty_state('deg-graph', TAB_HEIGHTS['strategy_bot'])
            ])
        ], style=TAB_STYLE, selected_style=TAB_SELECTED_STYLE),

        dcc.Tab(id='tab-race-control', label='Race', value='tab-race', children=[
            DISCLAIMER,
            dcc.Loading(type='dot', color='#ff0000', children=[
                _empty_state('race-gaps-graph', TAB_HEIGHTS['race_top'])
            ]),
            dcc.Loading(type='dot', color='#ff0000', children=[
                _empty_state('pit-stops-graph', TAB_HEIGHTS['race_bot'])
            ])
        ], style=TAB_STYLE, selected_style=TAB_SELECTED_STYLE),

        dcc.Tab(id='tab-gridpace-control', label='Grid Pace', value='tab-gridpace', children=[
            DISCLAIMER,
            dcc.Loading(type='dot', color='#ff0000', children=[
                _empty_state('grid-pace-graph', TAB_HEIGHTS['single'])
            ])
        ], style=TAB_STYLE, selected_style=TAB_SELECTED_STYLE),

        dcc.Tab(id='tab-ai-control', label='AI Analysis', value='tab-ai', children=[
            html.Div([
                html.Div([
                    dbc.InputGroup([
                        dbc.Input(id='ai-question-input', type='text',
                                  placeholder='Ask about this session... (e.g. "What was the optimal strategy in this race?")',
                                  n_submit=0,
                                  style={'backgroundColor': '#1a1a1a', 'color': 'white', 'border': '1px solid #444',
                                         'fontSize': '0.95rem'},
                                  disabled=not AI_ENABLED),
                        dbc.Button('Ask AI', id='ai-ask-button', color='danger', n_clicks=0,
                                   style={'fontWeight': 'bold'},
                                   disabled=not AI_ENABLED)
                    ], style={'marginBottom': '0.5rem'}),
                    html.Div("AI can make mistakes. Check important info.",
                             style={'fontSize': '0.75rem', 'color': '#888', 'textAlign': 'center', 'marginBottom': '0.75rem'}),
                ], style={'padding': '0.5rem 0'}),
                dcc.Loading(
                    type='default', color='#ff0000',
                    children=html.Div([
                        html.Div([
                            html.Strong("Q: ", style={'color': '#ff4444'}),
                            html.Span(id='ai-question-display', style={'color': '#ddd'})
                        ], id='ai-question-container', style={'marginBottom': '0.5rem', 'display': 'none'}),
                        html.Div(id='ai-loading-dummy', style={'display': 'none'}),
                        dcc.Markdown(id='ai-answer-display', style={'color': '#e0e0e0', 'lineHeight': '1.7'})
                    ], id='ai-response-output',
                       style={'padding': '1rem', 'minHeight': '200px',
                              'backgroundColor': '#1a1a1a', 'borderRadius': '8px',
                              'border': '1px solid #333', 'whiteSpace': 'pre-wrap',
                              'lineHeight': '1.6', 'fontSize': '0.95rem',
                              'maxHeight': '70vh', 'overflowY': 'auto'})
                ),
                html.Div([
                    dbc.Button("◀", id='ai-prev-btn', color='secondary', size='sm', n_clicks=0,
                               disabled=True, style={'padding': '2px 10px', 'fontSize': '0.85rem'}),
                    html.Span('', id='ai-history-position',
                              style={'color': '#999', 'fontSize': '0.85rem', 'margin': '0 0.5rem'}),
                    dbc.Button("▶", id='ai-next-btn', color='secondary', size='sm', n_clicks=0,
                               disabled=True, style={'padding': '2px 10px', 'fontSize': '0.85rem'}),
                ], id='ai-history-nav',
                   style={'display': 'none', 'alignItems': 'center', 'justifyContent': 'center',
                          'marginTop': '0.75rem'}),
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
                dcc.Store(id='ai-history-index-store', storage_type='session', data=0)
            ], style={'padding': '1.5rem', 'height': TAB_HEIGHTS['single'], 'overflowY': 'auto'})
        ], style=TAB_STYLE, selected_style=TAB_SELECTED_STYLE)
    ])
], style={"padding": "1rem"})


app_layout = dbc.Container([
    dcc.Location(id='url', refresh=False),
    dbc.Row([
        # Sidebar column.
        dbc.Col(sidebar, md=2, xs=12, 
                style={'height': '100vh', 'overflowY': 'auto', 'borderRight': '1px solid #333'},
                className='sidebar-col'),
        # Main content column.
        dbc.Col(content, md=10, xs=12, 
                style={'height': '100vh', 'overflowY': 'auto'},
                className='content-col')
    ], className='g-0'),
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

    dbc.Toast(
        "Link copied to clipboard!",
        id="share-toast",
        header="Shared",
        is_open=False,
        dismissable=True,
        icon="success",
        duration=3000,
        style={"position": "fixed", "top": 10, "right": 10, "width": 250, "zIndex": 9999},
    ),

    dcc.Store(id='dashboard-params-store', storage_type='session'),
    dcc.Store(id='latest-race-store', storage_type='memory'),
    dcc.Store(id='gg-data-store', storage_type='memory'),
    dcc.Store(id='mini-map-store', storage_type='memory'),
    dcc.Store(id='lap-playback-store', storage_type='memory'),
    dcc.Interval(id='lap-playback-interval', interval=20, n_intervals=0, disabled=True),
    dcc.Store(id='feedback-refresh-store'),
    dcc.Download(id='feedback-download'),
    dcc.ConfirmDialog(id='error-dialog', message='')
], fluid=True, style={"padding": "0px", "height": "100vh", "overflow": "hidden"})
