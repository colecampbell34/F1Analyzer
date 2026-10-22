from dash import dcc, html
import dash_bootstrap_components as dbc
from graph_config import GRAPH_CONFIG
from ai_config import AI_ENABLED
from session_data import get_supported_years
from callbacks_shared import ANALYSIS_VIEW_OPTIONS


# Tab graph heights by view.
TAB_HEIGHTS = {
    'single':       'calc(100dvh - 235px)',
    'telemetry':    'calc(100dvh - 315px)',
    'strategy_top': 'calc((100dvh - 215px) / 2)',
    'strategy_bot': 'calc((100dvh - 215px) / 2)',
    'race_top':     'calc((100dvh - 215px) / 2)',
    'race_bot':     'calc((100dvh - 215px) / 2)',
    'sidecar':      'calc((100dvh - 480px) / 2)',
}

# Displayed once above the active view instead of repeating inside every panel.
DATA_AVAILABILITY_NOTE = html.Span(
    "Historical sessions from 2023 onward are available after the source marks them complete. OpenF1 samples telemetry at about 3.7 Hz; individual laps or optional result, weather, and position data can be incomplete.",
    className='data-availability-note',
)

# Shared tab styles.
TAB_STYLE          = {'backgroundColor': '#222', 'color': 'white'}
TAB_SELECTED_STYLE = {'backgroundColor': '#ff0000', 'color': 'white'}

def _shortcut_buttons(prefix=''):
    id_prefix = f"{prefix}-" if prefix else ""
    return html.Div([
        dbc.Button("Top 2", id=f'{id_prefix}shortcut-top-two', color='secondary', outline=True, size='sm',
                   n_clicks=0, title='Compare the top two classified drivers'),
        dbc.Button("Closest", id=f'{id_prefix}shortcut-closest', color='secondary', outline=True, size='sm',
                   n_clicks=0, title='Compare the closest classified pair when timing data is available'),
    ], className='comparison-shortcuts', role='group', **{'aria-label': 'Comparison shortcuts'})


def _label_with_tip(label, tip, *_unused, **style):
    """A readable label whose native hover preserves contextual help without visual clutter."""
    return html.Span(label, className='label-with-tip', title=tip, style=style or None)


def _tab_label(label, tip, *_unused):
    return html.Span(label, className='tab-label-with-tip', title=tip)


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
                'paper_bgcolor': '#111111',
                'plot_bgcolor': '#111111',
                'font': {'color': '#cccccc'},
                'xaxis': {'visible': False},
                'yaxis': {'visible': False},
                'annotations': [{
                    'text': 'Choose a completed 2023+ session and two drivers,<br>then click "Load analysis"<br><br><span style="font-size: 13px; color: #888;"><i>Selected-lap telemetry is loaded on demand.</i></span>',
                    'showarrow': False,
                    'font': {'size': 15, 'color': '#ccc'},
                    'xref': 'paper', 'yref': 'paper', 'x': 0.5, 'y': 0.5
                }]
            }
        }
    )


def _sidecar_empty_state(graph_id, height):
    """Dark placeholder for small secondary charts before telemetry loads."""
    return dcc.Graph(
        id=graph_id,
        style={'height': height},
        config={'displayModeBar': False},
        figure={
            'data': [],
            'layout': {
                'template': 'plotly_dark',
                'paper_bgcolor': 'rgba(0,0,0,0)',
                'plot_bgcolor': 'rgba(0,0,0,0)',
                'xaxis': {'visible': False},
                'yaxis': {'visible': False},
                'margin': {'l': 0, 'r': 0, 't': 0, 'b': 0},
            }
        }
    )


# Reusable driver selector with teammate shortcut.
def _driver_selector(label, dropdown_id, btn_id):
    return html.Div([
        dbc.Label(
            _label_with_tip(
                label,
                "Pick one driver in the session. The charts compare this driver's lap, pace, and strategy against the other selected driver."
            ),
            style={"fontSize": "0.9rem"}
        ),
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
    ], className='sidebar-driver-selector', style={'marginBottom': '0.75rem'})


def _control_field(label, child, extra_class=''):
    return html.Div([
        dbc.Label(label, className='sidebar-control-label', style={"fontSize": "0.9rem"}),
        child
    ], className=f"sidebar-control-field {extra_class}".strip())


YEAR_LABEL = _label_with_tip("Year", "Choose a season with completed sessions in the 2023+ OpenF1 historical archive.")
RACE_LABEL = _label_with_tip("Grand Prix", "Choose the race weekend. Each weekend contains practice, qualifying, sprint, or race sessions depending on the format.")
SESSION_LABEL = _label_with_tip("Session", "Choose which part of the weekend to analyze. Race and Sprint unlock strategy and gap views.")


# Sidebar control panel.  The IDs in this layout are a stable public contract
# for the callback modules, so visual changes should add classes/structure
# without casually renaming controls.
sidebar = html.Div([
    html.Div([
        html.Div([
            html.Div("F1", className='product-mark', **{'aria-hidden': 'true'}),
            html.Div([
                html.H2("Analyzer", className="product-name"),
                html.P("Telemetry · Pace · Strategy", className='product-subtitle'),
            ]),
        ], className='product-lockup'),
        html.Div(className='section-heading'),
        html.Hr(className='rail-divider'),
    ], className='sidebar-header', style={'flex': '0 0 auto'}),

    # Scrollable controls are organized around the normal session-to-analysis flow.
    html.Div([
        html.Div([
            html.Div([
                html.Span("01", className='workflow-step'),
                html.Span("Choose a session", className='workflow-title'),
            ], className='workflow-heading'),
            _control_field(YEAR_LABEL, dcc.Dropdown(
                id='year-dropdown',
                options=[{'label': str(y), 'value': y} for y in get_supported_years()],
                value=max(get_supported_years()),
                persistence=True, persistence_type='session',
                searchable=True,
                style={'color': 'black', 'fontSize': '0.9rem'}
            ), 'year-field'),
            _control_field(RACE_LABEL, dcc.Loading(type='dot', color='#ff0000', children=[
                dcc.Dropdown(id='race-dropdown', persistence=True, persistence_type='session',
                             searchable=True, style={'color': 'black', 'fontSize': '0.9rem'}),
            ]), 'race-field'),
            _control_field(SESSION_LABEL, dcc.Loading(type='dot', color='#ff0000', children=[
                dcc.Dropdown(id='session-dropdown', persistence=True, persistence_type='session',
                             searchable=True, style={'color': 'black', 'fontSize': '0.9rem'}),
            ]), 'session-field'),
            dbc.Button([html.I(className="fas fa-history me-2"), "Use latest race"],
                       id='latest-race-btn', color='secondary', outline=True, size='sm', n_clicks=0,
                       title='Choose the most recent completed race and its top two classified drivers',
                       className='sidebar-latest-btn'),
        ], className='workflow-section workflow-session'),

        html.Div([
            html.Div([
                html.Span("02", className='workflow-step'),
                html.Span("Choose drivers", className='workflow-title'),
            ], className='workflow-heading'),
            _driver_selector("Driver 1", 'driver1-dropdown', 'teammate1-btn'),
            _driver_selector("Driver 2", 'driver2-dropdown', 'teammate2-btn'),
            html.Div([
                html.Div(
                    _label_with_tip(
                        "Quick picks",
                        "Top 2 uses classification order. Closest uses the tightest classified timing gap when timing data is available."
                    ),
                    className='sidebar-control-label',
                ),
                _shortcut_buttons()
            ], className='shortcut-wrap'),
        ], className='workflow-section workflow-drivers'),

        html.Div([
            html.Div("03", className='workflow-step'),
            html.Div([
                html.Strong("Load your analysis"),
            ], className='workflow-submit-copy'),
            dbc.Button("Load analysis", id='update-dashboard-btn', color='danger', n_clicks=0,
                       className='sidebar-update-btn',
                       title='Load the selected session and driver comparison'),
        ], className='workflow-submit'),

        html.Details([
            html.Summary("Session leaderboard",
                         title='View session order or best-lap ranking before choosing drivers.'),
            html.Div([
                html.Div("Check the classified order or best-lap ranking before loading a comparison.",
                         className='sidebar-leaderboard-hint'),
                dbc.Button([html.I(className="fas fa-list-ol me-2"), "Load session leaderboard"],
                           id='update-leaderboard-btn', color='secondary', outline=True,
                           size='sm', n_clicks=0, className='sidebar-leaderboard-btn',
                           title='Refresh the session order without changing the main comparison'),
                dcc.Loading(type='dot', color='#ff0000', children=[
                    html.Div(id='leaderboard-container')
                ])
            ], className='sidebar-leaderboard')
        ], className='sidebar-optional-section', open=True)
    ], className='sidebar-controls', style={'flex': '1 1 auto', 'overflowY': 'auto', 'paddingRight': '5px', 'marginBottom': '1rem'}),

    html.Button(
        "‹",
        id='sidebar-collapse-btn',
        className='sidebar-collapse-btn',
        n_clicks=0,
        title='Collapse or expand the selection panel',
        **{'aria-label': 'Collapse or expand the selection panel'},
    ),
], className='sidebar-panel', style={"padding": "1rem", "backgroundColor": "#111111", "height": "100vh",
          "display": "flex", "flexDirection": "column", "overflow": "hidden"})



# Main viewing area.
# Telemetry lap-selection row.
telemetry_controls = html.Div([
    dbc.Row([
        dbc.Col([
            dbc.Label(
                _label_with_tip(
                    "Driver 1 Lap",
                    "Fastest uses that driver's best lap. Numbered laps compare exact race laps, which is useful for strategy or traffic context.",
                    'intermediate'
                ),
                style={"fontSize": "0.8rem", "color": "#aaa", "marginBottom": "0.25rem"}
            ),
            dcc.Dropdown(
                id='d1-lap-dropdown',
                options=[{'label': 'Fastest', 'value': 'fastest'}],
                value='fastest',
                clearable=False,
                searchable=False,
                style={'color': 'black', 'fontSize': '0.85rem'}
            ),
        ], md=6, xs=12, style={'marginBottom': '0.5rem'}),
        dbc.Col([
            dbc.Label(
                _label_with_tip(
                    "Driver 2 Lap",
                    "Use the same lap number as Driver 1 for race-to-race context, or fastest for pure one-lap pace.",
                    'intermediate'
                ),
                style={"fontSize": "0.8rem", "color": "#aaa", "marginBottom": "0.25rem"}
            ),
            dcc.Dropdown(
                id='d2-lap-dropdown',
                options=[{'label': 'Fastest', 'value': 'fastest'}],
                value='fastest',
                clearable=False,
                searchable=False,
                style={'color': 'black', 'fontSize': '0.85rem'}
            ),
        ], md=6, xs=12, style={'marginBottom': '0.5rem'})
    ]),
    dbc.Row([
        dbc.Col([
            dbc.Button("Play Lap", id='play-lap-btn', color='secondary', size='sm', n_clicks=0,
                       title='Play the selected two-driver lap replay',
                       style={'fontWeight': 'bold', 'width': '100%'})
        ], md=2, xs=6, style={'display': 'flex', 'alignItems': 'center', 'marginTop': '0.35rem'}),
        dbc.Col([
            dbc.Button("Pause", id='pause-resume-lap-btn', color='secondary', outline=True, size='sm', n_clicks=0,
                       title='Pause or resume replay',
                       style={'fontWeight': 'bold', 'width': '100%'})
        ], md=2, xs=6, style={'display': 'flex', 'alignItems': 'center', 'marginTop': '0.35rem'}),
        dbc.Col([
            dbc.Button("Replay Focus", id='replay-focus-btn', color='danger', outline=True, size='sm', n_clicks=0,
                       title='Expand the lap replay workspace',
                       style={'fontWeight': 'bold', 'width': '100%'})
        ], md=2, xs=12, style={'display': 'flex', 'alignItems': 'center', 'marginTop': '0.35rem'}),
        dbc.Col([
            dbc.Checklist(
                id='mini-map-follow-toggle',
                options=[{'label': ' Follow cars', 'value': 'follow'}],
                value=['follow'],
                inline=True,
                switch=True,
                style={'color': '#aaa', 'fontSize': '0.78rem', 'whiteSpace': 'nowrap'},
            )
        ], md=2, xs=6, style={'display': 'flex', 'alignItems': 'center', 'marginTop': '0.35rem'}),
        dbc.Col([
            html.Div("Lap Time: 0.00s / 0.00s", id='lap-playback-time-label',
                     style={'color': '#aaa', 'fontSize': '0.82rem', 'width': '100%'})
        ], md=2, xs=6, style={'display': 'flex', 'alignItems': 'center', 'marginTop': '0.35rem'})
    ])
], className='telemetry-controls-panel',
   style={'padding': '0.5rem 1rem', 'backgroundColor': '#1a1a1a', 'borderRadius': '6px',
          'marginBottom': '0.5rem', 'border': '1px solid #333'})


mobile_companion = html.Div([
    html.Div([
        html.Div("F1 Analyzer", className='mobile-brand'),
        html.Div(id='mobile-session-summary', className='mobile-session-summary',
                 children='Choose a session and comparison')
    ], className='mobile-companion-title'),
    _shortcut_buttons('mobile'),
    html.Div([
        dbc.Button("Feedback", id='mobile-open-feedback-modal-btn', color='danger', size='sm', n_clicks=0,
                   title='Send feedback'),
        dbc.Button("Edit", id='mobile-edit-selection-btn', color='secondary', size='sm', n_clicks=0,
                   title='Show or hide session controls'),
        dbc.Button("Load", id='mobile-update-dashboard-btn', color='danger', size='sm', n_clicks=0,
                   title='Load the selected comparison')
    ], className='mobile-action-buttons')
], className='mobile-companion')


content = html.Main([
    html.Header([
        html.Div([
            html.H1("Build a comparison", id='main-title'),
        ]),
        html.Div([
            html.Div(className='workspace-provenance'),
            html.Div([
                html.Label("Analysis view", className='view-selector-label', htmlFor='main-tabs'),
                dcc.Dropdown(
                    id='main-tabs',
                    options=list(ANALYSIS_VIEW_OPTIONS),
                    value='tab-trackmap',
                    clearable=False,
                    searchable=False,
                    className='analysis-view-selector',
                ),
            ], className='analysis-view-selector-wrap', title='Choose the dashboard view to display'),
        ], className='workspace-actions'),
    ], className='workspace-header'),
    # Status updates still drive preload behavior, but are no longer surfaced
    # as a prominent strip above every chart.
    html.Div(
        id='loading-status-banner',
        className='loading-status-banner sr-only',
        children=html.Span('Choose a session and click Load analysis.'),
        role='status',
        **{'aria-live': 'polite'},
    ),
    html.Div([
        html.Div(DATA_AVAILABILITY_NOTE, className='dashboard-data-note'),
        dbc.Button([html.I(className='fas fa-download me-1'), "Download Chart"],
                   id='download-active-chart-btn', color='secondary', outline=True, size='sm',
                   n_clicks=0, title='Download the active Plotly chart as a PNG'),
    ], className='dashboard-info-row'),
    html.Div(id='export-status', className='export-status', role='status', **{'aria-live': 'polite'}),
    html.Div(id='graph-summary', className='sr-only', role='status', **{'aria-live': 'polite'}),
    html.Div(id='plot-resize-sentinel', style={'display': 'none'}),

    dcc.Tabs(id='analysis-view-panels', value='tab-trackmap', parent_className='analysis-view-panels', children=[

        dcc.Tab(id='tab-telemetry-control', label=_tab_label(
            'Telemetry',
            "Telemetry compares two selected laps using speed, gap, throttle/brake, gear, track position, and G-force. Use Replay Focus to watch the lap evolve.",
            'beginner'
        ), value='tab-telemetry', children=[
            telemetry_controls,
            dbc.Row([
                dbc.Col([
                    dcc.Loading(type='dot', color='#ff0000', children=[
                        _empty_state('speed-graph', TAB_HEIGHTS['telemetry'])
                    ])
                ], lg=9, md=8, xs=12),
                dbc.Col([
                    html.Div(
                        _label_with_tip(
                            "Track Position",
                            "The dots show both selected cars at the hovered or replayed point on the lap.",
                            'beginner'
                        ),
                        className='telemetry-sidecar-label',
                        style={'textAlign': 'center', 'color': '#888', 'fontSize': '0.7rem', 'marginBottom': '3px'}
                    ),
                    # Live Telemetry Dashboard
                    html.Div(id='live-telemetry-dashboard', className='live-dashboard-container', style={'display': 'none'}, children=[
                        html.Div(className='live-driver-row d1-row', children=[
                            html.Div(id='live-d1-name', className='live-driver-name', children='D1'),
                            html.Div(className='live-stats', children=[
                                html.Div([html.Span(id='live-d1-speed', className='stat-val', children='--'), html.Small(" KM/H")], className='stat-item'),
                                html.Div([html.Span(id='live-d1-gear', className='stat-val', children='--'), html.Small(" G")], className='stat-item'),
                            ])
                        ]),
                        html.Div(id='live-delta-row', className='live-delta-row', children=[
                            html.Span("GAP", className='delta-label'),
                            html.Span(id='live-delta-value', className='delta-value', children='--')
                        ]),
                        html.Div(className='live-driver-row d2-row', children=[
                            html.Div(id='live-d2-name', className='live-driver-name', children='D2'),
                            html.Div(className='live-stats', children=[
                                html.Div([html.Span(id='live-d2-speed', className='stat-val', children='--'), html.Small(" KM/H")], className='stat-item'),
                                html.Div([html.Span(id='live-d2-gear', className='stat-val', children='--'), html.Small(" G")], className='stat-item'),
                            ])
                        ]),
                    ]),
                    _sidecar_empty_state('mini-track-map', TAB_HEIGHTS['sidecar']),
                    html.Hr(style={'margin': '6px 0'}),
                    html.Div(_label_with_tip(
                        "G-Force Traces",
                        "Shows lateral and longitudinal forces. Wide sideways traces mean cornering load; downward traces mean braking.",
                        'intermediate'
                    ), className='telemetry-sidecar-label', style={
                        'textAlign': 'center',
                        'color': '#888',
                        'fontSize': '0.7rem',
                        'marginBottom': '3px'
                    }),
                    _sidecar_empty_state('gg-diagram', TAB_HEIGHTS['sidecar'])
                ], lg=3, md=4, xs=12, className='telemetry-sidecar',
                   style={'backgroundColor': '#151515', 'borderRadius': '8px', 'padding': '8px', 'marginTop': '6px', 'overflow': 'hidden'})
            ], className='telemetry-visual-grid')
        ], style=TAB_STYLE, selected_style=TAB_SELECTED_STYLE),

        dcc.Tab(id='tab-trackmap-control', label=_tab_label(
            'Track Map',
            "Track Map shows where each driver is stronger around the circuit. Dominance is best for who gained where; braking and speed isolate driving style.",
            'beginner'
        ), value='tab-trackmap', children=[
            html.Div([
                html.Div([
                    dbc.Label(
                        _label_with_tip(
                            "Track Map — Driver 1 Lap",
                            "This selection applies only to Track Map and does not change the Telemetry lap.",
                            'intermediate'
                        ),
                        style={"fontSize": "0.76rem", "color": "#aaa", "marginBottom": "0.2rem"}
                    ),
                    dcc.Dropdown(
                        id='trackmap-d1-lap-dropdown',
                        options=[{'label': 'Fastest', 'value': 'fastest'}],
                        value='fastest', clearable=False, searchable=False,
                        style={'color': 'black', 'fontSize': '0.82rem', 'minWidth': '150px'}
                    ),
                ], style={'minWidth': '150px'}),
                html.Div([
                    dbc.Label(
                        _label_with_tip(
                            "Track Map — Driver 2 Lap",
                            "This selection applies only to Track Map and does not change the Telemetry lap.",
                            'intermediate'
                        ),
                        style={"fontSize": "0.76rem", "color": "#aaa", "marginBottom": "0.2rem"}
                    ),
                    dcc.Dropdown(
                        id='trackmap-d2-lap-dropdown',
                        options=[{'label': 'Fastest', 'value': 'fastest'}],
                        value='fastest', clearable=False, searchable=False,
                        style={'color': 'black', 'fontSize': '0.82rem', 'minWidth': '150px'}
                    ),
                ], style={'minWidth': '150px'}),
                dbc.Label(
                    _label_with_tip(
                        "Overlay Mode:",
                        "Dominance shows where one driver is faster. Braking highlights braking zones. Speed colours track sections by velocity.",
                        'intermediate'
                    ),
                    style={"fontSize": "0.8rem", "color": "#aaa", "marginRight": "10px"}
                ),
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
                html.Div(
                    id='trackmap-lap-summary',
                    style={
                        'marginLeft': 'auto',
                        'color': '#aaa',
                        'fontSize': '0.78rem',
                        'textAlign': 'right'
                    }
                ),
            ], className='trackmap-controls-panel',
               style={'padding': '5px 15px', 'backgroundColor': '#1a1a1a', 'borderRadius': '6px', 'marginBottom': '0.5rem', 'display': 'flex', 'alignItems': 'center', 'gap': '0.5rem', 'flexWrap': 'wrap'}),
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

        dcc.Tab(id='tab-strategy-control', label=_tab_label(
            'Strategy',
            "Strategy focuses on tyre stints and degradation. It works best for Race and Sprint sessions where pit stops and tyre ageing matter.",
            'intermediate'
        ), value='tab-strategy', children=[
            html.Div(id='strategy-stint-overview', className='strategy-stint-overview'),
            dcc.Loading(type='dot', color='#ff0000', children=[
                _empty_state('strategy-graph', TAB_HEIGHTS['strategy_top'])
            ]),
            dcc.Loading(type='dot', color='#ff0000', children=[
                _empty_state('deg-graph', TAB_HEIGHTS['strategy_bot'])
            ])
        ], style=TAB_STYLE, selected_style=TAB_SELECTED_STYLE),

        dcc.Tab(id='tab-racepace-control', label=_tab_label(
            'Race & Pace',
            "Race & Pace combines the selected drivers' race gap and position with field-wide representative pace. Pit decisions are summarized as context rather than a standalone stop-time chart.",
            'intermediate'
        ), value='tab-racepace', children=[
            html.Div([
                html.Div(id='race-session-summary', className='race-session-summary'),
                html.Div(id='race-strategy-impact', className='race-strategy-impact'),
            ], className='racepace-summary-row'),
            dcc.Loading(type='dot', color='#ff0000', children=[
                _empty_state('race-gaps-graph', TAB_HEIGHTS['race_top'])
            ]),
            dcc.Loading(type='dot', color='#ff0000', children=[
                _empty_state('grid-pace-graph', TAB_HEIGHTS['race_bot'])
            ])
        ], style=TAB_STYLE, selected_style=TAB_SELECTED_STYLE),

        dcc.Tab(id='tab-ai-control', label=_tab_label(
            'AI Analysis',
            "AI Analysis answers questions from the loaded session context. Update the dashboard after changing sessions or drivers before asking.",
            'beginner'
        ), value='tab-ai', children=[
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
                    html.Div([
                        html.Span(
                            "AI can make mistakes. Check important info.",
                            title="AI answers use the currently loaded session context. If you change drivers or sessions, load the analysis first."
                        )
                    ],
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
                    html.Div(id='feedback-review-panel'),
                    html.Div([
                        dbc.Button("Refresh Performance", id='refresh-perf-review-btn', color='secondary',
                                   outline=True, size='sm', n_clicks=0)
                    ], id='perf-review-controls', style={'display': 'none', 'marginBottom': '1rem'}),
                    html.Div(id='perf-review-panel')
                ]),
                dcc.Store(id='session-context-store', data=''),
                dcc.Store(id='ai-history-store', storage_type='session', data=[]),
                dcc.Store(id='ai-history-index-store', storage_type='session', data=0)
            ], style={'padding': '1.5rem', 'height': TAB_HEIGHTS['single'], 'overflowY': 'auto'})
        ], style=TAB_STYLE, selected_style=TAB_SELECTED_STYLE)
    ]),
    html.Div([
        html.Div('Preparing analysis', id='view-loading-title', className='view-loading-title'),
        html.Div('Loading the data this view needs…', id='view-loading-detail', className='view-loading-detail'),
        html.Div([html.Span(), html.Span(), html.Span()], className='view-loading-skeleton', **{'aria-hidden': 'true'}),
    ], id='view-loading-overlay', className='view-loading-overlay', role='status', **{'aria-live': 'polite'}),
], className='analysis-workspace')


app_layout = dbc.Container([
    dcc.Location(id='url', refresh=False),
    mobile_companion,
    dbc.Row([
        dbc.Col(sidebar, xs=12, className='sidebar-col'),
        dbc.Col(content, xs=12, className='content-col')
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
                    dbc.Label("Dashboard rating", style={'fontSize': '0.85rem'}),
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
        id="teammate-toast",
        header="Teammate Shortcut",
        is_open=False,
        dismissable=True,
        icon="warning",
        duration=3500,
        style={"position": "fixed", "top": 72, "right": 10, "width": 280, "zIndex": 9999},
    ),

    dbc.Modal([
        dbc.ModalHeader(dbc.ModalTitle("Best on a Larger Screen")),
        dbc.ModalBody([
            html.P(
                "F1 Analyzer works on phones, but the telemetry charts, track maps, and replay controls are built for detailed comparison.",
                style={'marginBottom': '0.75rem'}
            ),
            html.P(
                "For the best experience, use a laptop, desktop, or larger tablet.",
                style={'color': '#b8c3cc', 'marginBottom': 0}
            )
        ]),
        dbc.ModalFooter(
            dbc.Button("Continue on Phone", id='phone-disclaimer-dismiss-btn',
                       color='danger', n_clicks=0)
        )
    ], id='phone-disclaimer-modal', is_open=False, centered=True,
       className='phone-disclaimer-modal'),

    dcc.Store(id='dashboard-params-store', storage_type='session'),
    dcc.Store(id='phone-disclaimer-store', storage_type='local', data={}),
    dcc.Store(id='replay-focus-store', storage_type='memory', data=False),
    dcc.Store(id='latest-race-store', storage_type='memory'),
    dcc.Store(id='gg-data-store', storage_type='memory'),
    dcc.Store(id='mini-map-store', storage_type='memory'),
    dcc.Store(id='lap-playback-store', storage_type='memory'),
    dcc.Store(id='telemetry-figure-cache-key-store', storage_type='memory'),
    dcc.Store(id='mini-map-cache-key-store', storage_type='memory'),
    dcc.Store(id='gg-cache-key-store', storage_type='memory'),
    dcc.Store(id='trackmap-cache-key-store', storage_type='memory'),
    dcc.Store(id='strategy-cache-key-store', storage_type='memory'),
    dcc.Store(id='race-cache-key-store', storage_type='memory'),
    dcc.Store(id='preload-status-store', storage_type='memory'),
    dcc.Store(id='active-tab-preload-store', storage_type='memory'),
    dcc.Store(id='mobile-setup-open-store', storage_type='memory', data=False),
    dcc.Store(id='sidebar-collapsed-store', storage_type='local', data=False),
    dcc.Interval(id='lap-playback-interval', interval=20, n_intervals=0, disabled=True),
    dcc.Interval(id='preload-status-interval', interval=1500, n_intervals=0, disabled=True),
    dcc.Store(id='feedback-refresh-store'),
    dcc.Download(id='feedback-download'),
    dcc.ConfirmDialog(id='error-dialog', message='')
], id='app-root', fluid=True, className='app-root',
   style={"padding": "0px", "height": "100vh", "overflow": "hidden"})
