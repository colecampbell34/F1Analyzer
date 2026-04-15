import os
from datetime import datetime
from urllib.parse import parse_qs
import pandas as pd
import fastf1
import fastf1.plotting
from dash import html
import dash_bootstrap_components as dbc
from data import get_best_lap, is_practice

def _friendly_error(e):
    """Translate cryptic FastF1/network errors to user-friendly messages."""
    msg = str(e)
    if '404' in msg:
        return "This session's data is not yet available. It may not have taken place yet, or the data hasn't been published."
    if '503' in msg or '502' in msg or 'Connection' in msg.lower():
        return "The F1 data server is temporarily unavailable. Please try again in a few minutes."
    if 'Timeout' in msg or 'timeout' in msg:
        return "The data request timed out. This can happen on the first load — please try again."
    if 'No lap data' in msg or 'no laps' in msg.lower():
        return "No lap data is available for this session yet."
    if 'did not set a valid lap' in msg:
        return msg  # Already user-friendly
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
        if str(entry.get('submitted_at', ''))[:10] == datetime.utcnow().strftime('%Y-%m-%d')
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

def _build_leaderboard_children(session, session_name):
    leaderboard_children = []

    _is_practice = is_practice(session_name)

    if _is_practice and getattr(session, 'laps', None) is not None and not session.laps.empty:
        drivers_data = []
        all_drivers = (session.results['Abbreviation'].dropna().unique()
                       if getattr(session, 'results', None) is not None and not session.results.empty
                       else session.laps['Driver'].unique())

        for drv in all_drivers:
            if not isinstance(drv, str) or len(drv) != 3:
                continue
            drv_laps = session.laps.pick_drivers(drv)
            fastest_lap = get_best_lap(session, drv)
            lap_time = fastest_lap['LapTime'] if fastest_lap is not None and pd.notna(
                fastest_lap['LapTime']) else pd.NaT

            color = "ffffff"
            if getattr(session, 'results', None) is not None and not session.results.empty:
                res_row = session.results[session.results['Abbreviation'] == drv]
                if not res_row.empty:
                    color = res_row.iloc[0].get('TeamColor', '')
                    if pd.isna(color) or not color:
                        try:
                            color = fastf1.plotting.get_team_color(
                                res_row.iloc[0].get('TeamName', ''), session=session)
                        except Exception:
                            pass
            if not str(color).startswith('#'):
                color = f"#{color}"

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

                color = row.get('TeamColor', '')
                if pd.isna(color) or not color:
                    try:
                        color = fastf1.plotting.get_team_color(row.get('TeamName', ''), session=session)
                    except Exception:
                        color = "ffffff"
                if not str(color).startswith('#'):
                    color = f"#{color}"

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
