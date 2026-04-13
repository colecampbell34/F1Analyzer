import dash
from dash import dcc, html
import dash_bootstrap_components as dbc
from dash.dependencies import Input, Output, State
from dash.exceptions import PreventUpdate
import plotly.graph_objects as go
import pandas as pd
import fastf1
import flask
import os
from google import genai
from datetime import datetime
from urllib.parse import parse_qs

from data import (
    _load_drivers_fast, get_teammate_from_info, get_event_schedule_cached,
    load_session_summary, load_session_with_preload, preload_session,
    store_feedback_entry, load_feedback_entries, get_best_lap
)
from graphs import (
    _get_driver_colors, _sort_fastest_driver, _build_telemetry_fig, _build_dominance_fig,
    _build_strategy_fig, _build_deg_fig, _build_race_gaps_fig,
    _build_grid_pace_fig, _build_pit_stops_fig
)
from ai_utils import (
    _gather_session_context, GEMINI_API_KEY, GEMINI_MODEL,
    check_rate_limit, check_daily_budget,
    get_cached_response, store_cached_response
)


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

    is_practice = any(p in session_name for p in ['Practice', 'FP'])

    if is_practice and getattr(session, 'laps', None) is not None and not session.laps.empty:
        drivers_data = []
        all_drivers = (session.results['Abbreviation'].dropna().unique()
                       if getattr(session, 'results', None) is not None and not session.results.empty
                       else session.laps['Driver'].unique())

        for drv in all_drivers:
            if not isinstance(drv, str) or len(drv) != 3:
                continue
            drv_laps = session.laps.pick_drivers(drv)
            fastest_lap = drv_laps.pick_fastest() if not drv_laps.empty else None
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
                for col in ['Time', 'Q3', 'Q2', 'Q1']:
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


def register_callbacks(app):
    # =============================================
    # 1. YEAR → RACE DROPDOWN
    # =============================================
    @app.callback(
        [Output('race-dropdown', 'options'), Output('race-dropdown', 'value')],
        [Input('year-dropdown', 'value')],
        [State('race-dropdown', 'value')]
    )
    def update_races(year, current_race):
        if not year:
            return dash.no_update, dash.no_update
        schedule = get_event_schedule_cached(year)
        schedule = schedule[schedule['EventFormat'] != 'testing']
        races = schedule['EventName'].tolist()
        options = [{'label': r.replace("Grand Prix", "GP"), 'value': r} for r in races]
        
        if dash.ctx.triggered_id == 'year-dropdown':
            val = None
        else:
            val = current_race if current_race in races else None
            
        return options, val

    # =============================================
    # 2. RACE → SESSION DROPDOWN
    # =============================================
    @app.callback(
        [Output('session-dropdown', 'options'), Output('session-dropdown', 'value')],
        [Input('race-dropdown', 'value')],
        [State('year-dropdown', 'value'), State('session-dropdown', 'value')]
    )
    def update_sessions(race, year, current_session):
        if not race or not year:
            return dash.no_update, dash.no_update
        event = fastf1.get_event(year, race)
        options = [{'label': event[f'Session{i}'], 'value': event[f'Session{i}']}
                   for i in range(1, 6)
                   if pd.notna(event[f'Session{i}']) and event[f'Session{i}']]
        valid_sessions = [opt['value'] for opt in options]

        if dash.ctx.triggered_id == 'race-dropdown':
            val = None
        else:
            if current_session in valid_sessions:
                val = current_session
            else:
                val = options[-1]['value'] if options else None
                for opt in options:
                    if opt['label'] == 'Race':
                        val = opt['value']
                        break
        return options, val

    # =============================================
    # 3. SESSION → DRIVER DROPDOWNS (with full labels)
    # =============================================
    @app.callback(
        [Output('driver1-dropdown', 'options'), Output('driver1-dropdown', 'value'),
         Output('driver2-dropdown', 'options'), Output('driver2-dropdown', 'value')],
        [Input('session-dropdown', 'value'), Input('race-dropdown', 'value')],
        [State('year-dropdown', 'value'), State('driver1-dropdown', 'value'), State('driver2-dropdown', 'value')]
    )
    def update_drivers(session_name, race, year, current_d1, current_d2):
        if not session_name or not race or not year:
            return dash.no_update, dash.no_update, dash.no_update, dash.no_update

        try:
            driver_info = _load_drivers_fast(year, race, session_name)

            # Build rich labels: "VER - Verstappen (Red Bull)"
            options = []
            valid_abbrs = []
            for d in driver_info:
                label = f"{d['abbr']} - {d['name']} ({d['team']})" if d['team'] else f"{d['abbr']} - {d['name']}"
                options.append({'label': label, 'value': d['abbr']})
                valid_abbrs.append(d['abbr'])

            options.sort(key=lambda x: x['value'])
            valid_abbrs.sort()

            default_d1 = valid_abbrs[0] if len(valid_abbrs) > 0 else None
            default_d2 = valid_abbrs[1] if len(valid_abbrs) > 1 else None

            new_d1 = current_d1 if current_d1 in valid_abbrs else default_d1
            new_d2 = current_d2 if current_d2 in valid_abbrs else default_d2

            return options, new_d1, options, new_d2
        except Exception as e:
            print(f"Drivers Error: {e}")
            return [], None, [], None

    # =============================================
    # 4. TEAMMATE AUTO-SELECT BUTTONS
    # =============================================
    @app.callback(
        Output('driver2-dropdown', 'value', allow_duplicate=True),
        Input('teammate1-btn', 'n_clicks'),
        [State('driver1-dropdown', 'value'), State('session-dropdown', 'value'),
         State('race-dropdown', 'value'), State('year-dropdown', 'value')],
        prevent_initial_call=True
    )
    def teammate_for_d1(n_clicks, driver1, session_name, race, year):
        if not n_clicks or not driver1 or not session_name or not race or not year:
            return dash.no_update
        try:
            driver_info = _load_drivers_fast(year, race, session_name)
            teammate = get_teammate_from_info(driver1, driver_info)
            return teammate if teammate else dash.no_update
        except Exception:
            return dash.no_update

    @app.callback(
        Output('driver1-dropdown', 'value', allow_duplicate=True),
        Input('teammate2-btn', 'n_clicks'),
        [State('driver2-dropdown', 'value'), State('session-dropdown', 'value'),
         State('race-dropdown', 'value'), State('year-dropdown', 'value')],
        prevent_initial_call=True
    )
    def teammate_for_d2(n_clicks, driver2, session_name, race, year):
        if not n_clicks or not driver2 or not session_name or not race or not year:
            return dash.no_update
        try:
            driver_info = _load_drivers_fast(year, race, session_name)
            teammate = get_teammate_from_info(driver2, driver_info)
            return teammate if teammate else dash.no_update
        except Exception:
            return dash.no_update

    # =============================================
    # 5. LEADERBOARD (with gaps to leader)
    # =============================================
    @app.callback(
        Output('leaderboard-container', 'children'),
        [Input('session-dropdown', 'value'), Input('race-dropdown', 'value'), Input('year-dropdown', 'value')]
    )
    def update_leaderboard(session_name, race, year):
        if not session_name or not race or not year:
            return html.Div("Select a session to load the leaderboard.", style={'color': '#888', 'fontSize': '0.9rem'})

        try:
            include_laps = any(p in session_name for p in ['Practice', 'FP'])
            session = load_session_summary(year, race, session_name, include_laps=include_laps)
            return _build_leaderboard_children(session, session_name)

        except Exception as e:
            print(f"Leaderboard Error: {e}")
            return html.Div(_friendly_error(e), style={'color': 'red', 'fontSize': '0.9rem'})

    # =============================================
    # 6. MASTER: Update Dashboard → Store params + Title + Context
    # =============================================
    @app.callback(
        [Output('dashboard-params-store', 'data'), Output('error-dialog', 'displayed'),
         Output('error-dialog', 'message')],
        [Input('update-dashboard-btn', 'n_clicks')],
        [State('driver1-dropdown', 'value'), State('driver2-dropdown', 'value'),
         State('session-dropdown', 'value'), State('race-dropdown', 'value'), State('year-dropdown', 'value')]
    )
    def update_dashboard_params(n_clicks, driver1, driver2, session_type, race, year):
        if not n_clicks:
            return dash.no_update, False, ""
        if not all([year, race, session_type, driver1, driver2]):
            return dash.no_update, True, "Please select Year, Race, Session, and both Drivers before updating."

        preload_session(year, race, session_type)
        params = {'year': year, 'race': race, 'session_type': session_type,
                  'driver1': driver1, 'driver2': driver2}
        return params, False, ""

    @app.callback(
        [Output('main-title', 'children'), Output('session-context-store', 'data')],
        [Input('dashboard-params-store', 'data')]
    )
    def update_dashboard_metadata(params):
        if not params:
            return "Select parameters to load data...", ""
        
        year, race, session_type = params['year'], params['race'], params['session_type']
        driver1, driver2 = params['driver1'], params['driver2']
        
        try:
            session = load_session_with_preload(year, race, session_type)

            # Build labels for the title
            try:
                p1 = session.results.loc[session.results['Abbreviation'] == driver1, 'Position'].values[0]
                lbl1 = f"{driver1} (P{int(p1)})" if pd.notna(p1) else driver1
            except (IndexError, KeyError):
                lbl1 = driver1
            try:
                p2 = session.results.loc[session.results['Abbreviation'] == driver2, 'Position'].values[0]
                lbl2 = f"{driver2} (P{int(p2)})" if pd.notna(p2) else driver2
            except (IndexError, KeyError):
                lbl2 = driver2

            # Build AI context
            context = _gather_session_context(session, session_type, driver1, driver2)
            context_header = f"{year} {race} | {session_type} | {driver1} vs {driver2}"
            full_context = f"{context_header}\n\n{context}"

            title_text = f"{year} {race} | {session_type} | {lbl1} vs {lbl2}"
            return title_text, full_context

        except Exception as e:
            print(f"Metadata Error: {e}")
            return f"{year} {race} | Data Unavailable", ""

    # --- Shared helper for per-tab callbacks ---
    def _get_shared_data(params):
        """Loads session and computes shared labels/colors from stored params."""
        session = load_session_with_preload(params['year'], params['race'], params['session_type'])
        d1, d2 = params['driver1'], params['driver2']

        try:
            p1 = session.results.loc[session.results['Abbreviation'] == d1, 'Position'].values[0]
            lbl1 = f"{d1} (P{int(p1)})" if pd.notna(p1) else d1
        except (IndexError, KeyError):
            lbl1 = d1
        try:
            p2 = session.results.loc[session.results['Abbreviation'] == d2, 'Position'].values[0]
            lbl2 = f"{d2} (P{int(p2)})" if pd.notna(p2) else d2
        except (IndexError, KeyError):
            lbl2 = d2

        c1, c2 = _get_driver_colors(d1, d2, session)
        return session, d1, d2, lbl1, lbl2, c1, c2

    # =============================================
    # 7. TAB: Telemetry (lazy)
    # =============================================
    @app.callback(
        Output('speed-graph', 'figure'),
        [Input('dashboard-params-store', 'data'), Input('main-tabs', 'value'),
         Input('update-laps-btn', 'n_clicks')],
        [State('d1-lap-mode', 'value'), State('d2-lap-mode', 'value'),
         State('d1-lap-number', 'value'), State('d2-lap-number', 'value')]
    )
    def update_telemetry(params, active_tab, n_laps, d1_mode, d2_mode, d1_lap_num, d2_lap_num):
        if not params or active_tab != 'tab-telemetry':
            return dash.no_update
        try:
            session, d1, d2, lbl1, lbl2, c1, c2 = _get_shared_data(params)

            def get_lap(driver, mode, lap_num):
                drv_laps = session.laps.pick_drivers(driver)
                if mode == 'specific' and lap_num is not None:
                    specific = drv_laps[drv_laps['LapNumber'] == int(lap_num)]
                    if not specific.empty:
                        return specific.iloc[0]
                return get_best_lap(session, driver)

            lap1, lap2 = get_lap(d1, d1_mode, d1_lap_num), get_lap(d2, d2_mode, d2_lap_num)

            if getattr(lap1, "empty", True) or pd.isna(lap1.get("LapTime")) if lap1 is not None else True:
                raise ValueError(f"{d1} did not set a valid lap.")
            if getattr(lap2, "empty", True) or pd.isna(lap2.get("LapTime")) if lap2 is not None else True:
                raise ValueError(f"{d2} did not set a valid lap.")

            tel1 = lap1.get_telemetry().add_distance()
            tel2 = lap2.get_telemetry().add_distance()
            if not tel1.empty: tel1['Distance'] -= tel1['Distance'].min()
            if not tel2.empty: tel2['Distance'] -= tel2['Distance'].min()

            fast_data, slow_data = _sort_fastest_driver(d1, tel1, c1, lap1, d2, tel2, c2, lap2, lbl1, lbl2)
            return _build_telemetry_fig(fast_data, slow_data)
        except Exception as e:
            print(f"Telemetry Error: {e}")
            fig = go.Figure().update_layout(template='plotly_dark')
            fig.add_annotation(text=f"Error: {_friendly_error(e)}", showarrow=False,
                               font=dict(size=14, color='#ff4444'), xref="paper", yref="paper", x=0.5, y=0.5)
            return fig

    # =============================================
    # 8. TAB: Track Dominance (lazy)
    # =============================================
    @app.callback(
        Output('2d-dominance-graph', 'figure'),
        [Input('dashboard-params-store', 'data'), Input('main-tabs', 'value')]
    )
    def update_dominance(params, active_tab):
        if not params or active_tab != 'tab-trackmap':
            return dash.no_update
        try:
            session, d1, d2, lbl1, lbl2, c1, c2 = _get_shared_data(params)
            lap1 = get_best_lap(session, d1)
            lap2 = get_best_lap(session, d2)

            tel1 = lap1.get_telemetry().add_distance()
            tel2 = lap2.get_telemetry().add_distance()
            if not tel1.empty: tel1['Distance'] -= tel1['Distance'].min()
            if not tel2.empty: tel2['Distance'] -= tel2['Distance'].min()

            fast_data, slow_data = _sort_fastest_driver(d1, tel1, c1, lap1, d2, tel2, c2, lap2, lbl1, lbl2)
            return _build_dominance_fig(d1, d2, c1, c2, tel1.copy(), tel2.copy(), fast_data, slow_data)
        except Exception as e:
            print(f"Dominance Error: {e}")
            fig = go.Figure().update_layout(template='plotly_dark')
            fig.add_annotation(text=f"Error: {_friendly_error(e)}", showarrow=False,
                               font=dict(size=14, color='#ff4444'), xref="paper", yref="paper", x=0.5, y=0.5)
            return fig

    # =============================================
    # 9. TAB: Strategy & Tyres (lazy)
    # =============================================
    @app.callback(
        [Output('strategy-graph', 'figure'), Output('deg-graph', 'figure')],
        [Input('dashboard-params-store', 'data'), Input('main-tabs', 'value')]
    )
    def update_strategy(params, active_tab):
        if not params or active_tab != 'tab-strategy':
            return dash.no_update, dash.no_update
        try:
            session, d1, d2, lbl1, lbl2, c1, c2 = _get_shared_data(params)
            session_type = params['session_type']

            is_quali = any(q in session_type for q in ['Qualifying', 'Shootout'])
            if is_quali:
                fig_strat = go.Figure().update_layout(template='plotly_dark')
                fig_strat.update_xaxes(visible=False).update_yaxes(visible=False)
                fig_strat.add_annotation(text="Strategy timeline is not applicable for Qualifying sessions",
                                         showarrow=False, font=dict(size=15, color='#888'),
                                         xref="paper", yref="paper", x=0.5, y=0.5)

                fig_deg = go.Figure().update_layout(template='plotly_dark')
                fig_deg.update_xaxes(visible=False).update_yaxes(visible=False)
                fig_deg.add_annotation(text="Tyre degradation is not applicable for Qualifying sessions",
                                       showarrow=False, font=dict(size=15, color='#888'),
                                       xref="paper", yref="paper", x=0.5, y=0.5)
            elif any(p in session_type for p in ['Practice', 'FP']):
                fig_strat = go.Figure().update_layout(template='plotly_dark')
                fig_strat.add_annotation(
                    text="Strategy view available for Race & Sprint sessions.\n"
                         "For practice, check the Grid Pace tab for pace comparisons.",
                    showarrow=False, font=dict(size=16, color='#888'),
                    xref="paper", yref="paper", x=0.5, y=0.5)
                fig_deg = go.Figure().update_layout(template='plotly_dark')
                fig_deg.add_annotation(text="Tyre degradation not applicable for practice sessions",
                                       showarrow=False, font=dict(size=16, color='#888'),
                                       xref="paper", yref="paper", x=0.5, y=0.5)
            else:
                fig_strat = _build_strategy_fig(session, d1, d2, lbl1, lbl2, c1, c2)
                fig_deg = _build_deg_fig(session, d1, d2, lbl1, lbl2, c1, c2)

            return fig_strat, fig_deg
        except Exception as e:
            print(f"Strategy Error: {e}")
            err = go.Figure().update_layout(template='plotly_dark')
            err.add_annotation(text=f"Error: {_friendly_error(e)}", showarrow=False,
                               font=dict(size=14, color='#ff4444'), xref="paper", yref="paper", x=0.5, y=0.5)
            return err, err

    # =============================================
    # 10. TAB: Race Analysis (lazy)
    # =============================================
    @app.callback(
        [Output('race-gaps-graph', 'figure'), Output('pit-stops-graph', 'figure')],
        [Input('dashboard-params-store', 'data'), Input('main-tabs', 'value')]
    )
    def update_race_analysis(params, active_tab):
        if not params or active_tab != 'tab-race':
            return dash.no_update, dash.no_update
        try:
            session, d1, d2, lbl1, lbl2, c1, c2 = _get_shared_data(params)
            session_type = params['session_type']

            if session_type in ['Race', 'Sprint']:
                fig_gaps = _build_race_gaps_fig(session, d1, d2, lbl1, lbl2, c1, c2)
                fig_pits = _build_pit_stops_fig(session, d1, d2, lbl1, lbl2, c1, c2)
            else:
                fig_gaps = go.Figure().update_layout(template='plotly_dark')
                fig_gaps.add_annotation(text="Race gap analysis available for Race & Sprint sessions only",
                                        showarrow=False, font=dict(size=16, color='#888'),
                                        xref="paper", yref="paper", x=0.5, y=0.5)
                fig_pits = go.Figure().update_layout(template='plotly_dark')
                fig_pits.add_annotation(text="Pit stop data available for Race & Sprint sessions only",
                                        showarrow=False, font=dict(size=16, color='#888'),
                                        xref="paper", yref="paper", x=0.5, y=0.5)
            return fig_gaps, fig_pits
        except Exception as e:
            print(f"Race Analysis Error: {e}")
            err = go.Figure().update_layout(template='plotly_dark')
            err.add_annotation(text=f"Error: {_friendly_error(e)}", showarrow=False,
                               font=dict(size=14, color='#ff4444'), xref="paper", yref="paper", x=0.5, y=0.5)
            return err, err

    # =============================================
    # 11. TAB: Grid Pace (lazy, independent of driver selection)
    # =============================================
    @app.callback(
        Output('grid-pace-graph', 'figure'),
        [Input('dashboard-params-store', 'data'), Input('main-tabs', 'value')]
    )
    def update_grid_pace(params, active_tab):
        if not params or active_tab != 'tab-gridpace':
            return dash.no_update
        try:
            session = load_session_with_preload(params['year'], params['race'], params['session_type'])
            return _build_grid_pace_fig(session, params['session_type'])
        except Exception as e:
            print(f"Grid Pace Error: {e}")
            fig = go.Figure().update_layout(template='plotly_dark')
            fig.add_annotation(text=f"Error: {_friendly_error(e)}", showarrow=False,
                               font=dict(size=16, color='#ff4444'), xref="paper", yref="paper", x=0.5, y=0.5)
            return fig


    # =============================================
    # 13. FEEDBACK MODAL / INBOX
    # =============================================
    @app.callback(
        Output('feedback-modal', 'is_open'),
        [Input('open-feedback-modal-btn', 'n_clicks'),
         Input('cancel-feedback-btn', 'n_clicks'),
         Input('feedback-refresh-store', 'data')],
        State('feedback-modal', 'is_open'),
        prevent_initial_call=True
    )
    def toggle_feedback_modal(open_clicks, cancel_clicks, refresh_data, is_open):
        trigger = dash.ctx.triggered_id
        if trigger == 'open-feedback-modal-btn':
            return True
        if trigger in {'cancel-feedback-btn', 'feedback-refresh-store'}:
            return False
        return is_open

    @app.callback(
        [Output('feedback-submit-alert', 'children'),
         Output('feedback-submit-alert', 'color'),
         Output('feedback-submit-alert', 'is_open'),
         Output('feedback-refresh-store', 'data'),
         Output('feedback-message', 'value'),
         Output('feedback-contact', 'value')],
        Input('submit-feedback-btn', 'n_clicks'),
        [State('feedback-category', 'value'),
         State('feedback-rating', 'value'),
         State('feedback-message', 'value'),
         State('feedback-contact', 'value'),
         State('dashboard-params-store', 'data'),
         State('main-tabs', 'value'),
         State('session-context-store', 'data')],
        prevent_initial_call=True
    )
    def submit_feedback(n_clicks, category, rating, message, contact, params, active_tab, session_context):
        if not n_clicks:
            raise PreventUpdate

        message = (message or '').strip()
        if len(message) < 15:
            return (
                "Please include a bit more detail so the issue is actionable.",
                'warning',
                True,
                dash.no_update,
                dash.no_update,
                dash.no_update
            )
        if len(message) > 2500:
            return (
                "Feedback is too long. Keep it under 2500 characters.",
                'warning',
                True,
                dash.no_update,
                dash.no_update,
                dash.no_update
            )

        forwarded_for = flask.request.headers.get('X-Forwarded-For', '')
        raw_ip = forwarded_for.split(',')[0].strip() if forwarded_for else flask.request.remote_addr
        user_agent = flask.request.headers.get('User-Agent')

        entry = store_feedback_entry(
            {
                'category': category,
                'rating': rating,
                'message': message,
                'contact': contact,
                'active_tab': active_tab,
                'session': params or {},
                'context_loaded': bool(session_context)
            },
            raw_ip=raw_ip,
            user_agent=user_agent
        )

        return (
            "Feedback submitted. Thanks.",
            'success',
            True,
            {'entry_id': entry['id'], 'submitted_at': entry['submitted_at']},
            '',
            ''
        )

    @app.callback(
        [Output('feedback-review-panel', 'children'),
         Output('feedback-review-controls', 'style')],
        [Input('url', 'search'),
         Input('feedback-refresh-store', 'data'),
         Input('refresh-feedback-review-btn', 'n_clicks')]
    )
    def update_feedback_review_panel(url_search, refresh_data, refresh_clicks):
        if not _feedback_admin_authorized(url_search):
            return [], {'display': 'none'}
        return _build_feedback_review_panel(load_feedback_entries(limit=100)), {
            'display': 'flex',
            'gap': '0.5rem',
            'marginBottom': '1rem'
        }

    @app.callback(
        Output('feedback-download', 'data'),
        Input('download-feedback-btn', 'n_clicks'),
        State('url', 'search'),
        prevent_initial_call=True
    )
    def download_feedback_csv(n_clicks, url_search):
        if not n_clicks or not _feedback_admin_authorized(url_search):
            raise PreventUpdate

        entries = load_feedback_entries()
        df = pd.json_normalize(entries, sep='_') if entries else pd.DataFrame(columns=[
            'id', 'submitted_at', 'category', 'rating', 'message', 'contact',
            'active_tab', 'context_loaded', 'ip_hash', 'user_agent', 'status',
            'session_year', 'session_race', 'session_session_type', 'session_driver1', 'session_driver2'
        ])
        filename = f"feedback-inbox-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}.csv"
        return dcc.send_data_frame(df.to_csv, filename, index=False)

    # =============================================
    # 14. AI ANALYSIS (rate-limited, cached, budget-tracked)
    # =============================================
    @app.callback(
        [Output('ai-response-output', 'children'), Output('ai-history-store', 'data'),
         Output('ai-question-input', 'value')],
        [Input('ai-ask-button', 'n_clicks'), Input('ai-question-input', 'n_submit')],
        [State('ai-question-input', 'value'), State('session-context-store', 'data'),
         State('ai-history-store', 'data')],
        prevent_initial_call=False
    )
    def ask_ai(n_clicks, n_submit, question, session_context, history):
        """Sends the user's question + session context to Gemini with full protection."""
        if history is None:
            history = []

        # On initial load: show existing history or default message
        if not dash.ctx.triggered_id:
            if history:
                return _render_history(history), dash.no_update, dash.no_update
            if not GEMINI_API_KEY:
                return html.P("🔒 AI Analysis is not available at this time.",
                              style={'color': '#888'}), dash.no_update, dash.no_update
            return html.P("Type a question and click 'Ask AI' or press Enter to get started.",
                          style={'color': '#888'}), dash.no_update, dash.no_update

        total_clicks = (n_clicks or 0) + (n_submit or 0)
        if total_clicks == 0 or not question or not question.strip():
            return dash.no_update, dash.no_update, dash.no_update

        # --- Guard: API key ---
        if not GEMINI_API_KEY:
            return html.P("🔒 AI Analysis is not available at this time.",
                          style={'color': '#888'}), dash.no_update, dash.no_update

        # --- Guard: Session context ---
        if not session_context:
            err = "⚠️ No session data loaded. Select a session and drivers, then click Update Dashboard."
            return _render_history(history + [{'question': question, 'answer': err}]), history, ''

        # --- Guard: Input validation ---
        question = question.strip()
        if len(question) < 10:
            err = "⚠️ Please ask a more specific question (at least 10 characters)."
            return _render_history(history + [{'question': question, 'answer': err}]), history, ''
        if len(question) > 300:
            err = "⚠️ Question is too long. Please keep it under 300 characters."
            return _render_history(history + [{'question': question, 'answer': err}]), history, ''

        # --- Guard: Per-IP rate limit ---
        try:
            ip = flask.request.remote_addr or 'unknown'
        except Exception:
            ip = 'unknown'

        allowed, rate_msg = check_rate_limit(ip)
        if not allowed:
            err = f"⏳ **Slow down!** {rate_msg}"
            return _render_history(history + [{'question': question, 'answer': err}]), history, ''

        # --- Guard: Daily budget ---
        if not check_daily_budget():
            err = "📊 **Daily AI analysis limit reached.** The AI assistant has a daily usage limit to manage costs. Please try again tomorrow (resets at midnight UTC)."
            return _render_history(history + [{'question': question, 'answer': err}]), history, ''

        # --- Check response cache ---
        cached = get_cached_response(session_context, question)
        if cached:
            new_history = history + [{'question': question, 'answer': cached}]
            return _render_history(new_history), new_history, ''

        # --- Call Gemini ---
        try:
            client = genai.Client(api_key=GEMINI_API_KEY)

            # Build conversation context from history
            history_text = ""
            if history:
                history_text = "\n\n=== PREVIOUS Q&A ===\n"
                for h in history[-3:]:  # last 3 exchanges for context
                    history_text += f"Q: {h['question']}\nA: {h['answer'][:500]}...\n\n"

            prompt = (
                "You are an expert Formula 1 data analyst. "
                "Try to sound a little bit smarter than you are but dont make any wild claims. "
                "Use lots of terms related to F1, that a real F1 analyst would use. "
                "The session data below is the AUTHORITATIVE source of truth. "
                "Do not make any claims that are not supported by the data. "
                "IMPORTANT: The driver-team assignments at the top of the session data are definitive — "
                "do NOT override them with your training knowledge. "
                "Teams and driver lineups change every season; always trust the data, not your priors.\n\n"
                "Answer the user's question with detailed, data-driven analysis, without being redundant. "
                "Reference specific numbers from the data. Be thorough and conclusive.\n\n"
                "=== SESSION DATA ===\n"
                f"{session_context}\n"
                f"{history_text}\n"
                "=== USER QUESTION ===\n"
                f"{question}"
            )

            try:
                response = client.models.generate_content(model=GEMINI_MODEL, contents=prompt)
                answer = response.text

                # Cache the response for future identical questions
                store_cached_response(session_context, question, answer)

                new_history = history + [{'question': question, 'answer': answer}]
                return _render_history(new_history), new_history, ''
            except Exception as e:
                error_str = str(e)
                if '429' in error_str:
                    err = "⏳ **AI service is busy right now.** Please wait about 60 seconds and try again."
                else:
                    err = f"❌ **AI Analysis encountered an error.**\n\n```text\n{error_str}\n```\nPlease try again in a moment."
                new_history = history + [{'question': question, 'answer': err}]
                return _render_history(new_history), new_history, ''

        except Exception as e:
            err = f"❌ **AI Analysis encountered an error.**\n\n```text\n{str(e)}\n```"
            new_history = history + [{'question': question, 'answer': err}]
            return _render_history(new_history), new_history, ''


def _render_history(history):
    """Renders only the most recent AI conversation exchange."""
    if not history:
        return []
    
    # Grab only the latest exchange
    h = history[-1]
    
    return html.Div([
        html.Div([
            html.Strong("Q: ", style={'color': '#ff4444'}),
            html.Span(h['question'], style={'color': '#ddd'})
        ], style={'marginBottom': '0.5rem'}),
        html.Div([
            dcc.Markdown(h['answer'], style={'color': '#e0e0e0', 'lineHeight': '1.7'})
        ]),
    ], style={'marginBottom': '1.5rem', 'paddingBottom': '1rem'})
