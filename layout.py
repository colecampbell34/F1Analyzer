import dash
from dash import dcc, html
import dash_bootstrap_components as dbc

# --- AFFILIATE LINKS CONFIG ---
# Replace these URLs with your actual affiliate links (e.g., Amazon Associates, F1 Store, etc.)
# To sign up: https://affiliate-program.amazon.com/ or https://f1store.formula1.com/affiliate
AFFILIATE_LINKS = [
    {
        'icon': '🏎️',
        'label': 'Official F1 Store',
        'sub': 'Team gear & merch',
        'url': 'https://f1store.formula1.com/',
    },
    {
        'icon': '🎮',
        'label': 'F1 25 Video Game',
        'sub': 'Available on all platforms',
        'url': 'https://www.amazon.com/dp/B0DT14NXP6?tag=YOUR_AMAZON_TAG',
    },
    {
        'icon': '📚',
        'label': 'F1 Books & Docs',
        'sub': 'Biographies & history',
        'url': 'https://www.amazon.com/s?k=formula+1+books&tag=YOUR_AMAZON_TAG',
    },
]

BANNER_LINKS = [
    {'text': '🏁 Official F1 Store', 'url': 'https://f1store.formula1.com/'},
    {'text': '🎮 F1 25 Game', 'url': 'https://www.amazon.com/dp/B0DT14NXP6?tag=YOUR_AMAZON_TAG'},
]


def _build_affiliate_sidebar():
    """Builds the affiliate links section for the sidebar."""
    links = []
    for item in AFFILIATE_LINKS:
        links.append(
            html.A([
                html.Span(item['icon'], className='link-icon'),
                html.Span([
                    html.Span(item['label'], className='link-label'),
                    html.Span(item['sub'], className='link-sub'),
                ], className='link-text')
            ], href=item['url'], target='_blank', rel='noopener noreferrer sponsored',
               className='affiliate-link')
        )

    return html.Div([
        html.H5("F1 Gear"),
        *links
    ], className='affiliate-section')


def _build_affiliate_banner():
    """Builds the slim top banner with affiliate links."""
    parts = []
    for i, link in enumerate(BANNER_LINKS):
        if i > 0:
            parts.append(html.Span('|', className='banner-sep'))
        parts.append(html.A(link['text'], href=link['url'], target='_blank', rel='noopener noreferrer sponsored'))

    return html.Div(parts, className='affiliate-banner')


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
    html.Div(id='leaderboard-container', style={'overflowY': 'auto', 'maxHeight': '30vh'}),

    # Affiliate links below leaderboard
    _build_affiliate_sidebar()

], style={"padding": "1rem", "background-color": "#111111", "height": "100vh", "overflowY": "auto"})

# --- 3. THE MAIN VIEWING AREA ---
content = html.Div([
    html.H3("Session Telemetry Analysis", className="text-center mt-2", id='main-title'),
    html.Hr(),

    # Affiliate banner between header and tabs
    _build_affiliate_banner(),

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
    ),
    dcc.ConfirmDialog(id='error-dialog', message='')
], fluid=True, style={"padding": "0px"})
