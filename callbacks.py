import dash
from dash import dcc, html
import dash_bootstrap_components as dbc
from dash.dependencies import Input, Output, State
import plotly.graph_objects as go
import pandas as pd
import fastf1
from google import genai

from data import _load_session_cached, _load_drivers_fast, get_driver_info, get_teammate
from graphs import (
    _get_driver_colors, _sort_fastest_driver, _build_telemetry_fig, _build_dominance_fig,
    _build_strategy_fig, _build_deg_fig, _build_qualifying_fig, _build_race_gaps_fig,
    _build_grid_pace_fig, _build_pit_stops_fig
)
from ai_utils import _gather_session_context, GEMINI_API_KEY


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
        schedule = fastf1.get_event_schedule(year)
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
            session = _load_session_cached(year, race, session_name)
            teammate = get_teammate(driver1, session)
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
            session = _load_session_cached(year, race, session_name)
            teammate = get_teammate(driver2, session)
            return teammate if teammate else dash.no_update
        except Exception:
            return dash.no_update

    # =============================================
    # 5. LEADERBOARD (with gaps to leader)
    # =============================================
    @app.callback(
        Output('leaderboard-container', 'children'),
        [Input('update-dashboard-btn', 'n_clicks')],
        [State('session-dropdown', 'value'), State('race-dropdown', 'value'), State('year-dropdown', 'value')]
    )
    def update_leaderboard(n_clicks, session_name, race, year):
        if not session_name or not race or not year:
            return dash.no_update

        try:
            session = _load_session_cached(year, race, session_name)
            leaderboard_children = []

            is_practice = any(p in session_name for p in ['Practice', 'FP'])

            if is_practice and getattr(session, 'laps', None) is not None and not session.laps.empty:
                # --- PRACTICE ---
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
                # --- RACE / QUALI / SPRINT ---
                if getattr(session, 'results', None) is not None and not session.results.empty:
                    results_df = session.results.copy()
                    results_df['Position_Num'] = pd.to_numeric(results_df['Position'], errors='coerce')
                    results_df = results_df.sort_values(by='Position_Num')

                    leader_time = None
                    is_race = session_name in ['Race', 'Sprint']

                    for row_idx, (_, row) in enumerate(results_df.iterrows()):
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

                        # Get the relevant time
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

        except Exception as e:
            print(f"Leaderboard Error: {e}")
            return html.Div("Error loading leaderboard", style={'color': 'red'})

    # =============================================
    # 6. MAIN GRAPH UPDATE (all driver-dependent graphs)
    # =============================================
    @app.callback(
        [Output('speed-graph', 'figure'), Output('2d-dominance-graph', 'figure'),
         Output('strategy-graph', 'figure'), Output('deg-graph', 'figure'),
         Output('race-gaps-graph', 'figure'), Output('pit-stops-graph', 'figure'),
         Output('session-context-store', 'data'), Output('main-title', 'children'),
         Output('error-dialog', 'displayed'), Output('error-dialog', 'message')],
        [Input('update-dashboard-btn', 'n_clicks'), Input('update-laps-btn', 'n_clicks')],
        [State('driver1-dropdown', 'value'), State('driver2-dropdown', 'value'),
         State('d1-lap-mode', 'value'), State('d2-lap-mode', 'value'),
         State('d1-lap-number', 'value'), State('d2-lap-number', 'value'),
         State('session-dropdown', 'value'), State('race-dropdown', 'value'), State('year-dropdown', 'value')]
    )
    def update_graphs(n_clicks_dashboard, n_clicks_update_laps, driver1, driver2, d1_mode, d2_mode, d1_lap_num, d2_lap_num,
                      session_type, race, year):
        empty_fig = go.Figure().update_layout(template='plotly_dark')
        no_update_set = (empty_fig,) * 6 + ('', "Select parameters to load data...", False, "")
        if not all([year, race, session_type, driver1, driver2]):
            return no_update_set

        try:
            session = _load_session_cached(year, race, session_type)

            # Determine which laps to use for telemetry
            def get_lap(driver, mode, lap_num):
                drv_laps = session.laps.pick_drivers(driver)
                if mode == 'specific' and lap_num is not None:
                    specific = drv_laps[drv_laps['LapNumber'] == int(lap_num)]
                    if not specific.empty:
                        return specific.iloc[0]
                return drv_laps.pick_fastest()

            lap1 = get_lap(driver1, d1_mode, d1_lap_num)
            lap2 = get_lap(driver2, d2_mode, d2_lap_num)

            if getattr(lap1, "empty", True) or pd.isna(lap1.get("LapTime")) if lap1 is not None else True:
                raise ValueError(f"{driver1} did not set a valid lap.")
            if getattr(lap2, "empty", True) or pd.isna(lap2.get("LapTime")) if lap2 is not None else True:
                raise ValueError(f"{driver2} did not set a valid lap.")

            tel1 = lap1.get_telemetry().add_distance()
            tel2 = lap2.get_telemetry().add_distance()

            if not tel1.empty:
                tel1['Distance'] -= tel1['Distance'].min()
            if not tel2.empty:
                tel2['Distance'] -= tel2['Distance'].min()

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

            c1, c2 = _get_driver_colors(driver1, driver2, session)
            fast_data, slow_data = _sort_fastest_driver(
                driver1, tel1, c1, lap1, driver2, tel2, c2, lap2, lbl1, lbl2)

            # Build Telemetry
            fig_speed = _build_telemetry_fig(fast_data, slow_data)

            # Build Track Dominance
            # Use copies to avoid modifying telemetry data in-place
            fig_2d_dom = _build_dominance_fig(
                driver1, driver2, c1, c2, tel1.copy(), tel2.copy(), fast_data, slow_data)

            # Build Strategy / Qualifying / Deg
            is_quali = any(q in session_type for q in ['Qualifying', 'Shootout'])

            if is_quali:
                fig_strat = _build_qualifying_fig(session, driver1, driver2, lbl1, lbl2, c1, c2)
                fig_deg = go.Figure().update_layout(template='plotly_dark')
                fig_deg.add_annotation(text="Tyre degradation not applicable for qualifying sessions",
                                       showarrow=False, font=dict(size=16, color='#888'),
                                       xref="paper", yref="paper", x=0.5, y=0.5)
            elif any(p in session_type for p in ['Practice', 'FP']):
                fig_strat = go.Figure().update_layout(template='plotly_dark')
                fig_strat.add_annotation(
                    text="Strategy view available for Race & Sprint sessions.\n"
                         "For practice, check the Grid Overview tab for pace comparisons.",
                    showarrow=False, font=dict(size=16, color='#888'),
                    xref="paper", yref="paper", x=0.5, y=0.5)
                fig_deg = go.Figure().update_layout(template='plotly_dark')
                fig_deg.add_annotation(text="Tyre degradation not applicable for practice sessions",
                                       showarrow=False, font=dict(size=16, color='#888'),
                                       xref="paper", yref="paper", x=0.5, y=0.5)
            else:
                fig_strat = _build_strategy_fig(session, driver1, driver2, lbl1, lbl2, c1, c2)
                fig_deg = _build_deg_fig(session, driver1, driver2, lbl1, lbl2, c1, c2)

            # Build Race Analysis
            is_race = session_type in ['Race', 'Sprint']
            if is_race:
                fig_gaps = _build_race_gaps_fig(session, driver1, driver2, lbl1, lbl2, c1, c2)
                fig_pits = _build_pit_stops_fig(session, driver1, driver2, lbl1, lbl2, c1, c2)
            else:
                fig_gaps = go.Figure().update_layout(template='plotly_dark')
                fig_gaps.add_annotation(text="Race gap analysis available for Race & Sprint sessions only",
                                        showarrow=False, font=dict(size=16, color='#888'),
                                        xref="paper", yref="paper", x=0.5, y=0.5)
                fig_pits = go.Figure().update_layout(template='plotly_dark')
                fig_pits.add_annotation(text="Pit stop data available for Race & Sprint sessions only",
                                        showarrow=False, font=dict(size=16, color='#888'),
                                        xref="paper", yref="paper", x=0.5, y=0.5)

            # Build AI context
            context = _gather_session_context(session, session_type, driver1, driver2)
            context_header = f"{year} {race} | {session_type} | {driver1} vs {driver2}"
            full_context = f"{context_header}\n\n{context}"

            title_text = f"{year} {race} | {session_type} | {fast_data[0]} vs {slow_data[0]}"
            return (fig_speed, fig_2d_dom, fig_strat, fig_deg, fig_gaps, fig_pits,
                    full_context, title_text, False, "")

        except Exception as e:
            print(f"Graph Error: {e}")
            err_fig = go.Figure().update_layout(title="Error Loading Telemetry Data", template='plotly_dark')
            return (err_fig,) * 6 + ('', "Data Unavailable", True, f"Error: {e}")

    # =============================================
    # 7. GRID PACE (independent of driver selection)
    # =============================================
    @app.callback(
        Output('grid-pace-graph', 'figure'),
        [Input('update-dashboard-btn', 'n_clicks')],
        [State('session-dropdown', 'value'), State('race-dropdown', 'value'), State('year-dropdown', 'value')]
    )
    def update_grid_pace(n_clicks, session_name, race, year):
        if not session_name or not race or not year:
            return go.Figure().update_layout(template='plotly_dark')
        try:
            session = _load_session_cached(year, race, session_name)
            return _build_grid_pace_fig(session, session_name)
        except Exception as e:
            print(f"Grid Pace Error: {e}")
            fig = go.Figure().update_layout(template='plotly_dark')
            fig.add_annotation(text=f"Error loading grid pace: {e}", showarrow=False,
                               font=dict(size=16, color='#ff4444'), xref="paper", yref="paper", x=0.5, y=0.5)
            return fig

    # =============================================
    # 8. NOTES TOGGLE
    # =============================================
    @app.callback(
        Output('notes-collapse', 'is_open'),
        Input('toggle-notes-btn', 'n_clicks'),
        State('notes-collapse', 'is_open'),
        prevent_initial_call=True
    )
    def toggle_notes(n_clicks, is_open):
        return not is_open

    # =============================================
    # 9. AI ANALYSIS (with conversation history + Enter-to-submit)
    # =============================================
    @app.callback(
        [Output('ai-response-output', 'children'), Output('ai-history-store', 'data')],
        [Input('ai-ask-button', 'n_clicks'), Input('ai-question-input', 'n_submit')],
        [State('ai-question-input', 'value'), State('session-context-store', 'data'),
         State('ai-history-store', 'data')],
        prevent_initial_call=False
    )
    def ask_ai(n_clicks, n_submit, question, session_context, history):
        """Sends the user's question + session context to Gemini with conversation history."""
        if history is None:
            history = []

        # On initial load: show existing history or default message
        if not dash.ctx.triggered_id:
            if history:
                return _render_history(history), dash.no_update
            return html.P("Type a question and click 'Ask AI' or press Enter to get started.",
                          style={'color': '#888'}), dash.no_update

        total_clicks = (n_clicks or 0) + (n_submit or 0)
        if total_clicks == 0 or not question or not question.strip():
            return dash.no_update, dash.no_update

        if not GEMINI_API_KEY:
            error_html = html.Div([
                html.P("⚠️ Gemini API key not configured.", style={'color': '#ff4444', 'fontWeight': 'bold'}),
                html.P("Set the GEMINI_API_KEY environment variable:", style={'color': '#aaa'}),
                html.Code("export GEMINI_API_KEY='your-api-key-here'",
                          style={'color': '#00ff88', 'backgroundColor': '#111', 'padding': '0.5rem',
                                 'display': 'block', 'borderRadius': '4px', 'marginTop': '0.5rem'})
            ])
            return error_html, dash.no_update

        if not session_context:
            return html.P("⚠️ No session data loaded. Select a session and drivers first.",
                          style={'color': '#ff4444'}), dash.no_update

        try:
            client = genai.Client(api_key=GEMINI_API_KEY)

            # Build conversation context from history
            history_text = ""
            if history:
                history_text = "\n\n=== PREVIOUS Q&A ===\n"
                for h in history[-3:]:  # last 3 exchanges for context
                    history_text += f"Q: {h['question']}\nA: {h['answer'][:500]}...\n\n"

            prompt = (
                "You are an expert Formula 1 data analyst. You have access to the following telemetry "
                "and race data for a specific F1 session. Answer the user's question with detailed, "
                "data-driven analysis. Reference specific numbers from the data. Be thorough and conclusive.\n\n"
                "=== SESSION DATA ===\n"
                f"{session_context}\n"
                f"{history_text}\n"
                "=== USER QUESTION ===\n"
                f"{question}"
            )

            models_to_try = ['gemini-flash-latest', 'gemini-2.5-flash', 'gemini-3.1-flash-lite',
                             'gemini-2.5-flash-lite']
            last_error = None

            for model_name in models_to_try:
                try:
                    response = client.models.generate_content(model=model_name, contents=prompt)
                    answer = response.text

                    new_history = history + [{'question': question, 'answer': answer}]

                    return _render_history(new_history), new_history
                except Exception as e:
                    last_error = e
                    if '429' not in str(e):
                        break

            error_str = str(last_error)
            if '429' in error_str:
                return html.Div([
                    html.P("⏳ Rate limit reached on Gemini free tier.",
                           style={'color': '#ffaa00', 'fontWeight': 'bold'}),
                    html.P("Please wait about 60 seconds and try again.", style={'color': '#aaa'}),
                ]), dash.no_update
            else:
                return html.Div([
                    html.P(f"❌ AI Error: {error_str}", style={'color': '#ff4444'}),
                    html.P("Please check your API key and try again.", style={'color': '#888'})
                ]), dash.no_update

        except Exception as e:
            return html.Div([
                html.P(f"❌ AI Error: {str(e)}", style={'color': '#ff4444'}),
                html.P("Please check your API key and try again.", style={'color': '#888'})
            ]), dash.no_update


def _render_history(history):
    """Renders the full AI conversation history as a scrollable list."""
    children = []
    for i, h in enumerate(history):
        children.append(html.Div([
            html.Div([
                html.Strong("Q: ", style={'color': '#ff4444'}),
                html.Span(h['question'], style={'color': '#ddd'})
            ], style={'marginBottom': '0.5rem'}),
            html.Div([
                dcc.Markdown(h['answer'], style={'color': '#e0e0e0', 'lineHeight': '1.7'})
            ]),
        ], style={'marginBottom': '1.5rem', 'paddingBottom': '1rem',
                  'borderBottom': '1px solid #333' if i < len(history) - 1 else 'none'}))
    return html.Div(children)
