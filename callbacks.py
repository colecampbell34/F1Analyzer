import dash
from dash import dcc, html
import dash_bootstrap_components as dbc
from dash.dependencies import Input, Output, State
from dash.exceptions import PreventUpdate
import flask
import random
from datetime import datetime
from urllib.parse import parse_qs

from data import (
    _load_drivers_fast, get_teammate_from_info, get_event_schedule_cached,
    load_session_summary, load_session_with_preload, preload_session,
    get_best_lap, get_shared_data, is_qualifying, is_race, is_practice
)
from feedback import store_feedback_entry, load_feedback_entries
from graphs import (
    _sort_fastest_driver, _build_telemetry_fig, _build_dominance_fig,
    _build_strategy_fig, _build_deg_fig, _build_race_gaps_fig,
    _build_grid_pace_fig, _build_pit_stops_fig,
    _error_figure, _not_applicable_figure
)
from ai_utils import (
    _gather_session_context, GEMINI_API_KEY, GEMINI_MODELS,
    get_cached_response, store_cached_response, build_ai_prompt
)
from ui_utils import (
    _friendly_error, _feedback_admin_authorized,
    _build_feedback_review_panel, _build_leaderboard_children
)


# Max number of AI Q&A exchanges stored in browser sessionStorage
MAX_AI_HISTORY = 20


def _trim_history(history):
    """Enforce max history length by dropping oldest entries."""
    if len(history) > MAX_AI_HISTORY:
        return history[-MAX_AI_HISTORY:]
    return history


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
        import fastf1
        import pandas as pd
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
        [Input('update-leaderboard-btn', 'n_clicks')],
        [State('session-dropdown', 'value'), State('race-dropdown', 'value'), State('year-dropdown', 'value')]
    )
    def update_leaderboard(n_clicks, session_name, race, year):
        if not n_clicks:
            return html.Div("Click 'Update Leaderboard' to load.", style={'color': '#888', 'fontSize': '0.9rem'})
        if not session_name or not race or not year:
            return html.Div("Select a session to load the leaderboard.", style={'color': '#888', 'fontSize': '0.9rem'})

        try:
            include_laps = is_practice(session_name) or is_qualifying(session_name)
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
            import pandas as pd
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
            import pandas as pd
            session, d1, d2, lbl1, lbl2, c1, c2 = get_shared_data(params)

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
            return _error_figure(_friendly_error(e))

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
            session, d1, d2, lbl1, lbl2, c1, c2 = get_shared_data(params)
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
            return _error_figure(_friendly_error(e))

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
            session, d1, d2, lbl1, lbl2, c1, c2 = get_shared_data(params)
            session_type = params['session_type']

            if is_qualifying(session_type):
                fig_strat = _not_applicable_figure("Strategy timeline is not applicable for Qualifying sessions")
                fig_deg = _not_applicable_figure("Tyre degradation is not applicable for Qualifying sessions")
            elif is_practice(session_type):
                fig_strat = _not_applicable_figure(
                    "Strategy view available for Race & Sprint sessions.\n"
                    "For practice, check the Grid Pace tab for pace comparisons.")
                fig_deg = _not_applicable_figure("Tyre degradation not applicable for practice sessions")
            else:
                fig_strat = _build_strategy_fig(session, d1, d2, lbl1, lbl2, c1, c2)
                fig_deg = _build_deg_fig(session, d1, d2, lbl1, lbl2, c1, c2)

            return fig_strat, fig_deg
        except Exception as e:
            print(f"Strategy Error: {e}")
            err = _error_figure(_friendly_error(e))
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
            session, d1, d2, lbl1, lbl2, c1, c2 = get_shared_data(params)
            session_type = params['session_type']

            if is_race(session_type):
                fig_gaps = _build_race_gaps_fig(session, d1, d2, lbl1, lbl2, c1, c2)
                fig_pits = _build_pit_stops_fig(session, d1, d2, lbl1, lbl2, c1, c2)
            else:
                fig_gaps = _not_applicable_figure("Race gap analysis available for Race & Sprint sessions only")
                fig_pits = _not_applicable_figure("Pit stop data available for Race & Sprint sessions only")
            return fig_gaps, fig_pits
        except Exception as e:
            print(f"Race Analysis Error: {e}")
            err = _error_figure(_friendly_error(e))
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
            return _error_figure(_friendly_error(e))


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

        import pandas as pd
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
    #     with paginated history (prev/next arrows)
    # =============================================
    @app.callback(
        [Output('ai-response-output', 'children'), Output('ai-history-store', 'data'),
         Output('ai-question-input', 'value'), Output('ai-history-index-store', 'data')],
        [Input('ai-ask-button', 'n_clicks'), Input('ai-question-input', 'n_submit'),
         Input('ai-prev-btn', 'n_clicks'), Input('ai-next-btn', 'n_clicks')],
        [State('ai-question-input', 'value'), State('session-context-store', 'data'),
         State('ai-history-store', 'data'), State('ai-history-index-store', 'data')],
        prevent_initial_call=False
    )
    def ask_ai(n_clicks, n_submit, n_prev, n_next, question, session_context, history, current_index):
        """Sends the user's question + session context to Gemini with full protection."""
        if history is None:
            history = []
        history = _trim_history(history)
        if current_index is None:
            current_index = max(0, len(history) - 1)

        trigger = dash.ctx.triggered_id

        # --- Navigation: prev/next arrows ---
        if trigger == 'ai-prev-btn':
            new_index = max(0, current_index - 1)
            return _render_history_page(history, new_index), dash.no_update, dash.no_update, new_index
        if trigger == 'ai-next-btn':
            new_index = min(len(history) - 1, current_index + 1) if history else 0
            return _render_history_page(history, new_index), dash.no_update, dash.no_update, new_index

        # On initial load: show existing history or default message
        if not trigger:
            if history:
                idx = len(history) - 1
                return _render_history_page(history, idx), dash.no_update, dash.no_update, idx
            if not GEMINI_API_KEY:
                return html.P("🔒 AI Analysis is not available at this time.",
                              style={'color': '#888'}), dash.no_update, dash.no_update, 0
            return html.P("Type a question and click 'Ask AI' or press Enter to get started.",
                          style={'color': '#888'}), dash.no_update, dash.no_update, 0

        total_clicks = (n_clicks or 0) + (n_submit or 0)
        if total_clicks == 0 or not question or not question.strip():
            return dash.no_update, dash.no_update, dash.no_update, dash.no_update

        # --- Guard: API key ---
        if not GEMINI_API_KEY:
            return html.P("🔒 AI Analysis is not available at this time.",
                          style={'color': '#888'}), dash.no_update, dash.no_update, current_index

        # --- Guard: Session context ---
        if not session_context:
            err = "⚠️ No session data loaded. Select a session and drivers, then click Update Dashboard."
            new_history = history + [{'question': question, 'answer': err}]
            new_idx = len(new_history) - 1
            return _render_history_page(new_history, new_idx), history, '', new_idx

        # --- Guard: Input validation ---
        question = question.strip()
        if len(question) < 10:
            err = "⚠️ Please ask a more specific question (at least 10 characters)."
            new_history = history + [{'question': question, 'answer': err}]
            new_idx = len(new_history) - 1
            return _render_history_page(new_history, new_idx), history, '', new_idx
        if len(question) > 300:
            err = "⚠️ Question is too long. Please keep it under 300 characters."
            new_history = history + [{'question': question, 'answer': err}]
            new_idx = len(new_history) - 1
            return _render_history_page(new_history, new_idx), history, '', new_idx

        # --- Check response cache ---
        cached = get_cached_response(session_context, question)
        if cached:
            new_history = history + [{'question': question, 'answer': cached}]
            new_idx = len(new_history) - 1
            return _render_history_page(new_history, new_idx), new_history, '', new_idx

        # --- Call Gemini Models sequentially with random start ---
        shuffled_models = GEMINI_MODELS.copy()
        random.shuffle(shuffled_models)
        
        last_error = ""
        for model_name in shuffled_models:
            try:
                from google import genai
                client = genai.Client(api_key=GEMINI_API_KEY)
                prompt = build_ai_prompt(session_context, question, history)
                
                response = client.models.generate_content(model=model_name, contents=prompt)
                answer = response.text
                
                # Append model attribution
                attribution = f"\n\n---\n*Response generated by {model_name}*"
                full_answer = answer + attribution

                # Cache the response for future identical questions
                store_cached_response(session_context, question, full_answer)

                new_history = history + [{'question': question, 'answer': full_answer}]
                new_idx = len(new_history) - 1
                return _render_history_page(new_history, new_idx), new_history, '', new_idx

            except Exception as e:
                last_error = str(e)
                # Fail gracefully and try the next model
                continue
        
        # If all models failed
        err = f"❌ **AI Analysis encountered an error after trying multiple models.**\n\n```text\n{last_error}\n```\nPlease try again in a moment."
        new_history = history + [{'question': question, 'answer': err}]
        new_idx = len(new_history) - 1
        return _render_history_page(new_history, new_idx), new_history, '', new_idx


def _render_history_page(history, index):
    """Renders a single AI Q&A exchange with prev/next navigation."""
    if not history:
        return []

    index = max(0, min(index, len(history) - 1))
    h = history[index]
    total = len(history)

    # Navigation bar
    nav_bar = html.Div([
        dbc.Button("◀", id='ai-prev-btn', color='secondary', size='sm', n_clicks=0,
                   disabled=(index == 0),
                   style={'padding': '2px 10px', 'fontSize': '0.85rem'}),
        html.Span(f" {index + 1} / {total} ",
                  style={'color': '#999', 'fontSize': '0.85rem', 'margin': '0 0.5rem'}),
        dbc.Button("▶", id='ai-next-btn', color='secondary', size='sm', n_clicks=0,
                   disabled=(index >= total - 1),
                   style={'padding': '2px 10px', 'fontSize': '0.85rem'}),
    ], style={'display': 'flex', 'alignItems': 'center', 'justifyContent': 'center', 'marginBottom': '1rem'})

    content = html.Div([
        html.Div([
            html.Strong("Q: ", style={'color': '#ff4444'}),
            html.Span(h['question'], style={'color': '#ddd'})
        ], style={'marginBottom': '0.5rem'}),
        html.Div([
            dcc.Markdown(h['answer'], style={'color': '#e0e0e0', 'lineHeight': '1.7'})
        ]),
    ], style={'marginBottom': '1rem', 'paddingBottom': '1rem'})

    return html.Div([nav_bar, content])
