import os
from datetime import datetime, timezone
from urllib.parse import parse_qs
import flask
from dash import html
import dash_bootstrap_components as dbc
from ux_helpers import get_glossary_definition

def _friendly_error(e):
    """Translate cryptic FastF1/network errors to user-friendly messages."""
    msg = str(e)
    lower_msg = msg.lower()
    if 'data has not been loaded' in lower_msg or 'session does not exist' in lower_msg:
        return "This session is not live in FastF1 yet. If the weekend has not started or the data feed is still syncing, try again shortly."
    if '404' in msg:
        return "This session's data is not available yet. It may not have started, or FastF1 has not published it yet."
    if '503' in msg or '502' in msg or 'Connection' in lower_msg:
        return "The F1 data server is temporarily unavailable. Please try again in a few minutes."
    if 'timeout' in lower_msg:
        return "The data request timed out. This can happen on the first load — please try again."
    if 'no lap data' in lower_msg or 'no laps' in lower_msg:
        return "Lap data is not available for this session yet. The event may still be in progress or not published."
    if 'did not set a valid lap' in msg:
        return msg
    if 'telemetry data is not available' in lower_msg or 'telemetry' in lower_msg:
        return "Telemetry data is not available or is incomplete for this session from the F1 live timing feed."
    if 'date' in lower_msg or 'columns' in lower_msg:
        return "Telemetry data is incomplete or has missing timestamps for this session."
    return f"Something went wrong loading the data: {msg}"

def _tab_label(tab_value):
    labels = {
        'tab-telemetry': 'Telemetry',
        'tab-trackmap': 'Track Map',
        'tab-strategy': 'Strategy',
        'tab-race': 'Race',
        'tab-gridpace': 'Grid Pace',
        'tab-ai': 'AI Analysis'
    }
    return labels.get(tab_value, 'Unknown')

def _feedback_admin_authorized(url_search):
    token = os.getenv('FEEDBACK_ADMIN_TOKEN')
    if not token:
        return False

    # Preferred auth channel: request header or cookie (not URL).
    supplied_header = flask.request.headers.get('X-Feedback-Admin-Token', '')
    if supplied_header == token:
        return True

    supplied_cookie = flask.request.cookies.get('feedback_admin_token', '')
    if supplied_cookie == token:
        return True

    # Backward-compatibility fallback for existing workflows.
    query_params = parse_qs((url_search or '').lstrip('?'))
    supplied = (query_params.get('feedback_admin') or [''])[0]
    return supplied == token

def _format_feedback_time(timestamp):
    if not timestamp:
        return 'Unknown time'
    try:
        dt = datetime.fromisoformat(str(timestamp).replace('Z', '+00:00'))
        return dt.strftime('%Y-%m-%d %H:%M UTC')
    except ValueError:
        return str(timestamp)

def _feedback_context_text(entry):
    session = entry.get('session') or {}
    parts = [
        session.get('year'),
        session.get('race'),
        session.get('session_type')
    ]
    session_text = ' | '.join(str(part) for part in parts if part)
    drivers = ' vs '.join(str(part) for part in [session.get('driver1'), session.get('driver2')] if part)

    if session_text and drivers:
        return f"{session_text} | {drivers}"
    if session_text:
        return session_text
    return 'No session attached'

def _build_feedback_card(entry):
    category = entry.get('category', 'general')
    badge_colors = {
        'bug': 'danger',
        'feature': 'info',
        'data': 'warning',
        'general': 'secondary'
    }

    meta_bits = [
        f"Tab: {_tab_label(entry.get('active_tab'))}",
        f"Context attached: {'Yes' if entry.get('context_loaded') else 'No'}",
        f"Reporter: {entry.get('ip_hash', 'anonymous')}"
    ]
    if entry.get('contact'):
        meta_bits.append(f"Contact: {entry['contact']}")

    return dbc.Card(
        dbc.CardBody([
            html.Div([
                html.Div([
                    dbc.Badge(category.title(), color=badge_colors.get(category, 'secondary'),
                              className='me-2'),
                    dbc.Badge(f"{entry.get('rating', 0)}/5", color='light', text_color='dark')
                ], style={'display': 'flex', 'gap': '0.4rem'}),
                html.Small(_format_feedback_time(entry.get('submitted_at')), style={'color': '#999'})
            ], style={'display': 'flex', 'justifyContent': 'space-between', 'gap': '1rem', 'marginBottom': '0.75rem'}),
            html.P(entry.get('message', ''), style={'whiteSpace': 'pre-wrap', 'marginBottom': '0.75rem'}),
            html.Div(_feedback_context_text(entry), style={'fontSize': '0.85rem', 'color': '#bbb', 'marginBottom': '0.35rem'}),
            html.Div(' • '.join(meta_bits), style={'fontSize': '0.8rem', 'color': '#8f8f8f'})
        ]),
        className='mb-3'
    )

def _build_feedback_review_panel(entries):
    total = len(entries)
    bug_count = sum(1 for entry in entries if entry.get('category') == 'bug')
    feature_count = sum(1 for entry in entries if entry.get('category') == 'feature')
    recent_count = sum(
        1
        for entry in entries
        if str(entry.get('submitted_at', ''))[:10] == datetime.now(timezone.utc).strftime('%Y-%m-%d')
    )

    summary_cards = dbc.Row([
        dbc.Col(dbc.Card(dbc.CardBody([html.Div("Total", style={'color': '#999'}), html.H4(str(total))])), md=3, xs=6),
        dbc.Col(dbc.Card(dbc.CardBody([html.Div("Bugs", style={'color': '#999'}), html.H4(str(bug_count))])), md=3, xs=6),
        dbc.Col(dbc.Card(dbc.CardBody([html.Div("Features", style={'color': '#999'}), html.H4(str(feature_count))])), md=3, xs=6),
        dbc.Col(dbc.Card(dbc.CardBody([html.Div("Today", style={'color': '#999'}), html.H4(str(recent_count))])), md=3, xs=6)
    ], className='g-2 mb-3')

    if not entries:
        feedback_body = dbc.Alert("No feedback submitted yet.", color='dark')
    else:
        feedback_body = html.Div([_build_feedback_card(entry) for entry in entries[:25]])

    return html.Div([
        html.H5("Feedback Inbox", style={'marginTop': '0.5rem'}),
        html.P(
            "Newest submissions are shown here. Add "
            "?feedback_admin=YOUR_TOKEN to the app URL to unlock this panel.",
            style={'color': '#888', 'fontSize': '0.85rem'}
        ),
        summary_cards,
        feedback_body
    ])


def _format_bytes(num_bytes):
    try:
        value = float(num_bytes or 0)
    except (TypeError, ValueError):
        value = 0.0
    for unit in ('B', 'KB', 'MB', 'GB'):
        if value < 1024 or unit == 'GB':
            return f"{value:.1f} {unit}" if unit != 'B' else f"{int(value)} B"
        value /= 1024


def _build_perf_review_panel(snapshot, jobs, cache_stats):
    """Build an admin-only lightweight performance panel."""
    slow = snapshot.get('recent_slow_callbacks') or []
    callbacks = snapshot.get('callbacks_by_name') or []
    jobs = jobs or []
    cache_stats = cache_stats or {}

    top_callbacks = callbacks[:6]
    callback_rows = [
        html.Div([
            html.Strong(row.get('name', 'callback'), style={'color': '#eee'}),
            html.Span(
                f" count {row.get('count', 0)} | avg {row.get('avg_ms', 0)}ms | max {row.get('max_ms', 0)}ms",
                style={'color': '#aaa', 'float': 'right'}
            )
        ], style={'padding': '0.25rem 0', 'borderBottom': '1px solid #333', 'fontSize': '0.82rem'})
        for row in top_callbacks
    ] or [html.Div("No callback timings recorded yet.", style={'color': '#888', 'fontSize': '0.85rem'})]

    job_rows = [
        html.Div([
            html.Strong(f"{job.get('profile', 'profile')} ", style={'color': '#eee'}),
            html.Span(f"{job.get('year')} {job.get('race')} {job.get('session')}", style={'color': '#bbb'}),
            dbc.Badge(job.get('status', 'idle'), color={
                'ready': 'success',
                'loading': 'info',
                'queued': 'secondary',
                'error': 'danger',
                'idle': 'dark'
            }.get(job.get('status'), 'secondary'), className='ms-2')
        ], style={'padding': '0.25rem 0', 'borderBottom': '1px solid #333', 'fontSize': '0.82rem'})
        for job in jobs[:8]
    ] or [html.Div("No preload jobs tracked yet.", style={'color': '#888', 'fontSize': '0.85rem'})]

    cache_info = cache_stats.get('session_cache') or {}
    selected_lap_cache = cache_stats.get('selected_lap_cache') or {}
    cache_text = (
        f"FastF1 cache {_format_bytes(cache_stats.get('cache_size_bytes'))} | "
        f"session hits {cache_info.get('hits', 0)} misses {cache_info.get('misses', 0)} | "
        f"telemetry prep hits {selected_lap_cache.get('hits', 0)} misses {selected_lap_cache.get('misses', 0)}"
    )

    return html.Div([
        html.H5("Performance", style={'marginTop': '1rem'}),
        dbc.Row([
            dbc.Col(dbc.Card(dbc.CardBody([
                html.Div("Callbacks", style={'color': '#999'}),
                html.H4(str(snapshot.get('callback_count', 0)))
            ])), md=3, xs=6),
            dbc.Col(dbc.Card(dbc.CardBody([
                html.Div("Slow Recent", style={'color': '#999'}),
                html.H4(str(len(slow)))
            ])), md=3, xs=6),
            dbc.Col(dbc.Card(dbc.CardBody([
                html.Div("Preload Jobs", style={'color': '#999'}),
                html.H4(str(len(jobs)))
            ])), md=3, xs=6),
            dbc.Col(dbc.Card(dbc.CardBody([
                html.Div("Cache", style={'color': '#999'}),
                html.H4(_format_bytes(cache_stats.get('cache_size_bytes')))
            ])), md=3, xs=6),
        ], className='g-2 mb-3'),
        html.Div(cache_text, style={'color': '#aaa', 'fontSize': '0.85rem', 'marginBottom': '0.75rem'}),
        dbc.Row([
            dbc.Col([
                html.H6("Callback Timing"),
                html.Div(callback_rows)
            ], md=6, xs=12),
            dbc.Col([
                html.H6("Preload Status"),
                html.Div(job_rows)
            ], md=6, xs=12),
        ], className='g-3')
    ])


def _glossary_tooltip_text(term):
    return get_glossary_definition(term)

def _build_leaderboard_children(session, session_name, year=None, race=None):
    import pandas as pd
    from data import get_best_lap, is_practice, resolve_team_color

    _is_practice = is_practice(session_name)
    _is_shootout = 'Shootout' in session_name
    
    parts = []
    if year: parts.append(str(year))
    if race:
        # Shorten 'Grand Prix' to 'GP' and add to title.
        race_clean = str(race).replace('Grand Prix', 'GP')
        parts.append(race_clean)
    if session_name: parts.append(str(session_name))
    subtitle = " ".join(parts) if parts else ""
    
    leaderboard_children = [
        html.Div(subtitle, style={
            'fontSize': '0.72rem',
            'color': '#888',
            'marginBottom': '0.4rem',
            'marginTop': '-0.2rem',
            'fontStyle': 'italic',
            'textAlign': 'center',
            'borderBottom': '1px solid #444',
            'paddingBottom': '0.3rem',
            'whiteSpace': 'nowrap',
            'overflow': 'hidden',
            'textOverflow': 'ellipsis'
        })
    ] if subtitle else []

    if (_is_practice or _is_shootout) and getattr(session, 'laps', None) is not None and not session.laps.empty:
        drivers_data = []
        all_drivers = (session.results['Abbreviation'].dropna().unique()
                       if getattr(session, 'results', None) is not None and not session.results.empty
                       else session.laps['Driver'].unique())

        for drv in all_drivers:
            if not isinstance(drv, str) or len(drv) != 3:
                continue
            fastest_lap = get_best_lap(session, drv)
            lap_time = fastest_lap['LapTime'] if fastest_lap is not None and pd.notna(
                fastest_lap['LapTime']) else pd.NaT

            team_name = ''
            raw_color = None
            if getattr(session, 'results', None) is not None and not session.results.empty:
                res_row = session.results[session.results['Abbreviation'] == drv]
                if not res_row.empty:
                    team_name = res_row.iloc[0].get('TeamName', '')
                    raw_color = res_row.iloc[0].get('TeamColor', None)
            color = resolve_team_color(
                team_name,
                session=session,
                raw_color=raw_color,
                fallback_identifier=drv,
            )

            drivers_data.append({'Abbreviation': drv, 'LapTime': lap_time, 'TeamColor': color})

        valid_times = sorted([d for d in drivers_data if pd.notna(d['LapTime'])],
                             key=lambda x: x['LapTime'])
        no_times = [d for d in drivers_data if pd.isna(d['LapTime'])]
        sorted_drivers = valid_times + no_times

        leader_time = sorted_drivers[0]['LapTime'] if sorted_drivers and pd.notna(
            sorted_drivers[0]['LapTime']) else None

        for idx, r in enumerate(sorted_drivers):
            pos_str = f"P{idx + 1}" if pd.notna(r['LapTime']) else "N/A"

            if pd.notna(r['LapTime']):
                if idx == 0 or leader_time is None:
                    delta = r['LapTime']
                    mins = int(delta.total_seconds() // 60)
                    secs = delta.total_seconds() % 60
                    time_str = f"{mins}:{secs:06.3f}"
                else:
                    gap = (r['LapTime'] - leader_time).total_seconds()
                    time_str = f"+{gap:.3f}s"
            else:
                time_str = "NO TIME"

            row_div = html.Div([
                html.Span(f"{pos_str} ",
                          style={'width': '30px', 'display': 'inline-block', 'color': '#888'}),
                html.Strong(f"{r['Abbreviation']}",
                            style={'color': r['TeamColor'], 'width': '50px', 'display': 'inline-block'}),
                html.Span(f"{time_str}", style={'color': '#ccc', 'float': 'right'})
            ], style={'padding': '0.2rem 0', 'borderBottom': '1px solid #333', 'fontSize': '0.85rem'})

            leaderboard_children.append(row_div)
    else:
        if getattr(session, 'results', None) is not None and not session.results.empty:
            results_df = session.results.copy()
            results_df['Position_Num'] = pd.to_numeric(results_df['Position'], errors='coerce')
            results_df = results_df.sort_values(by='Position_Num')

            leader_time = None
            is_race = session_name in ['Race', 'Sprint']

            for _, row in results_df.iterrows():
                abbr = row.get('Abbreviation', '')
                if not isinstance(abbr, str) or len(abbr) != 3:
                    continue

                pos = row.get('Position', '?')
                pos_str = f"P{int(pos)}" if pd.notna(pos) else "N/A"

                color = resolve_team_color(
                    row.get('TeamName', ''),
                    session=session,
                    raw_color=row.get('TeamColor', None),
                    fallback_identifier=abbr,
                )

                raw_time = None
                for col in ['Time', 'Q3', 'Q2', 'Q1', 'SQ3', 'SQ2', 'SQ1']:
                    if col in row and pd.notna(row[col]):
                        raw_time = row[col]
                        break

                if raw_time is not None:
                    if leader_time is None:
                        leader_time = raw_time
                        mins = int(raw_time.total_seconds() // 60)
                        secs = raw_time.total_seconds() % 60
                        time_str = f"{mins}:{secs:06.3f}"
                    else:
                        if is_race:
                            gap = raw_time.total_seconds()
                            time_str = f"+{gap:.3f}s"
                        else:
                            gap = (raw_time - leader_time).total_seconds()
                            time_str = f"+{gap:.3f}s"
                else:
                    status = row.get('Status', '')
                    time_str = status if isinstance(status, str) else ""

                row_div = html.Div([
                    html.Span(f"{pos_str} ",
                              style={'width': '30px', 'display': 'inline-block', 'color': '#888'}),
                    html.Strong(f"{abbr}",
                                style={'color': color, 'width': '50px', 'display': 'inline-block'}),
                    html.Span(f"{time_str}", style={'color': '#ccc', 'float': 'right'})
                ], style={'padding': '0.2rem 0', 'borderBottom': '1px solid #333', 'fontSize': '0.85rem'})

                leaderboard_children.append(row_div)

    return leaderboard_children


def _downsample(df, max_points=2000):
    """Downsample a DataFrame to max_points rows via even spacing. Visually identical at chart resolution."""
    if len(df) <= max_points:
        return df
    step = max(1, len(df) // max_points)
    return df.iloc[::step].reset_index(drop=True)


def _hex_to_rgba(hex_val, opacity):
    h = hex_val.lstrip('#')
    rgb = tuple(int(h[i:i+2], 16) for i in (0, 2, 4))
    return f'rgba({rgb[0]}, {rgb[1]}, {rgb[2]}, {opacity})'


BASE_LAYOUT = dict(
    template='plotly_dark',
    margin=dict(l=40, r=40, t=60, b=40),
    hovermode='x unified',
    font=dict(family='Inter, Segoe UI, Arial, sans-serif', color='#e8edf2'),
    paper_bgcolor='#0b0f14',
    plot_bgcolor='#0f141a',
    hoverlabel=dict(bgcolor='#111820', bordercolor='#44515f', font=dict(color='#f5f7fa')),
    legend=dict(bgcolor='rgba(10, 15, 20, 0.72)', bordercolor='rgba(255,255,255,0.08)', borderwidth=1)
)

def _apply_base_layout(fig, **kwargs):
    """Applies the base F1 analyzer layout, allowing kwargs to override specifics."""
    fig.update_layout(**BASE_LAYOUT)
    fig.update_layout(**kwargs)
    fig.update_xaxes(gridcolor='rgba(255,255,255,0.08)', zerolinecolor='rgba(255,255,255,0.18)')
    fig.update_yaxes(gridcolor='rgba(255,255,255,0.08)', zerolinecolor='rgba(255,255,255,0.18)')
    return fig
