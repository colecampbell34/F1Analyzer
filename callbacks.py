import dash
from dash import dcc, html
import dash_bootstrap_components as dbc
from dash.dependencies import Input, Output, State
import plotly.graph_objects as go
import pandas as pd
import fastf1
from google import genai

from data import _load_session_cached
from graphs import _get_driver_colors, _sort_fastest_driver, _build_telemetry_fig, _build_dominance_fig, _build_strategy_fig
from ai_utils import _gather_session_context, GEMINI_API_KEY

def register_callbacks(app):
    @app.callback([Output('race-dropdown', 'options'), Output('race-dropdown', 'value')], [Input('year-dropdown', 'value')],
                  [State('race-dropdown', 'value')])
    def update_races(year, current_race):
        if not year: return dash.no_update, dash.no_update
        schedule = fastf1.get_event_schedule(year)
        schedule = schedule[schedule['EventFormat'] != 'testing']
        races = schedule['EventName'].tolist()
        options = [{'label': r.replace("Grand Prix", "GP"), 'value': r} for r in races]

        # If the persisted race is still valid for this year, keep it! Otherwise, use the 1st race.
        val = current_race if current_race in races else (races[0] if races else None)
        return options, val


    @app.callback([Output('session-dropdown', 'options'), Output('session-dropdown', 'value')],
                  [Input('race-dropdown', 'value')], [State('year-dropdown', 'value'), State('session-dropdown', 'value')])
    def update_sessions(race, year, current_session):
        if not race or not year: return dash.no_update, dash.no_update
        event = fastf1.get_event(year, race)

        # Generate the available sessions for this specific weekend
        options = [{'label': event[f'Session{i}'], 'value': event[f'Session{i}']} for i in range(1, 6) if
                   pd.notna(event[f'Session{i}']) and event[f'Session{i}']]
        valid_sessions = [opt['value'] for opt in options]

        if current_session in valid_sessions:
            val = current_session
        else:
            val = options[-1]['value'] if options else None
            for opt in options:
                if opt['label'] == 'Race': val = opt['value']

        return options, val


    @app.callback([Output('driver1-dropdown', 'options'), Output('driver1-dropdown', 'value'),
         Output('driver2-dropdown', 'options'), Output('driver2-dropdown', 'value')],
        [Input('session-dropdown', 'value'), Input('race-dropdown', 'value')],
        [State('year-dropdown', 'value'), State('driver1-dropdown', 'value'), State('driver2-dropdown', 'value')])
    def update_drivers(session_name, race, year, current_d1, current_d2):
        if not session_name or not race or not year:
            return dash.no_update, dash.no_update, dash.no_update, dash.no_update

        try:
            session = _load_session_cached(year, race, session_name, load_telemetry=False)
            valid_drivers = [d for d in session.results['Abbreviation'].dropna().tolist() if
                             isinstance(d, str) and len(d) == 3]
            options = [{'label': d, 'value': d} for d in sorted(valid_drivers)]

            # Default choices (1st and 2nd fastest in the session)
            default_d1 = valid_drivers[0] if len(valid_drivers) > 0 else None
            default_d2 = valid_drivers[1] if len(valid_drivers) > 1 else None

            # Keep current driver if they drove in this session, otherwise use default
            new_d1 = current_d1 if current_d1 in valid_drivers else default_d1
            new_d2 = current_d2 if current_d2 in valid_drivers else default_d2

            return options, new_d1, options, new_d2
        except Exception as e:
            print(f"Drivers Error: {e}")
            return [], None, [], None

    @app.callback(
        Output('leaderboard-container', 'children'),
        [Input('session-dropdown', 'value'), Input('race-dropdown', 'value')],
        [State('year-dropdown', 'value')]
    )
    def update_leaderboard(session_name, race, year):
        if not session_name or not race or not year:
            return dash.no_update

        try:
            session = _load_session_cached(year, race, session_name, load_telemetry=False)
            leaderboard_children = []
            if getattr(session, 'results', None) is not None and not session.results.empty:
                for _, row in session.results.iterrows():
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

                    time_str = ""
                    for col in ['Time', 'Q3', 'Q2', 'Q1']:
                        if col in row and pd.notna(row[col]):
                            delta = row[col]
                            mins = int(delta.total_seconds() // 60)
                            secs = delta.total_seconds() % 60
                            time_str = f"{mins}:{secs:06.3f}"
                            break
                    
                    if not time_str:
                        status = row.get('Status', '')
                        time_str = status if isinstance(status, str) else ""

                    row_div = html.Div([
                        html.Span(f"{pos_str} ", style={'width': '30px', 'display': 'inline-block', 'color': '#888'}),
                        html.Strong(f"{abbr}", style={'color': color, 'width': '50px', 'display': 'inline-block'}),
                        html.Span(f"{time_str}", style={'color': '#ccc', 'float': 'right'})
                    ], style={'padding': '0.2rem 0', 'borderBottom': '1px solid #333', 'fontSize': '0.85rem'})
                    
                    leaderboard_children.append(row_div)

            return leaderboard_children

        except Exception as e:
            print(f"Leaderboard Error: {e}")
            return html.Div("Error loading leaderboard", style={'color': 'red'})


    @app.callback([Output('speed-graph', 'figure'), Output('2d-dominance-graph', 'figure'), Output('strategy-graph', 'figure'),
         Output('session-context-store', 'data'), Output('main-title', 'children')],
        [Input('driver1-dropdown', 'value'), Input('driver2-dropdown', 'value')],
        [State('session-dropdown', 'value'), State('race-dropdown', 'value'), State('year-dropdown', 'value')])
    def update_graphs(driver1, driver2, session_type, race, year):
        empty_fig = go.Figure().update_layout(template='plotly_dark')
        if not all([year, race, session_type, driver1, driver2]):
            return empty_fig, empty_fig, empty_fig, '', "Select parameters to load data..."

        try:
            # 1. Load Session Data (cached)
            session = _load_session_cached(year, race, session_type, load_telemetry=True)

            # 2. Extract Laps & Telemetry
            lap1 = session.laps.pick_drivers(driver1).pick_fastest()
            lap2 = session.laps.pick_drivers(driver2).pick_fastest()

            if pd.isna(lap1['LapTime']) or pd.isna(lap2['LapTime']):
                raise ValueError("One or both drivers did not set a valid lap.")

            tel1 = lap1.get_telemetry().add_distance()
            tel2 = lap2.get_telemetry().add_distance()
        
            # Zero out distances to perfectly align telemetry (fixes missing start-line gaps)
            if not tel1.empty: tel1['Distance'] -= tel1['Distance'].min()
            if not tel2.empty: tel2['Distance'] -= tel2['Distance'].min()
        
            try:
                p1 = session.results.loc[session.results['Abbreviation'] == driver1, 'Position'].values[0]
                lbl1 = f"{driver1} (P{int(p1)})" if pd.notna(p1) else driver1
            except:
                lbl1 = driver1
            
            try:
                p2 = session.results.loc[session.results['Abbreviation'] == driver2, 'Position'].values[0]
                lbl2 = f"{driver2} (P{int(p2)})" if pd.notna(p2) else driver2
            except:
                lbl2 = driver2

            # 3. Setup Colors & Sort Drivers (Fastest vs Slowest)
            c1, c2 = _get_driver_colors(driver1, driver2, session)
            fast_data, slow_data = _sort_fastest_driver(driver1, tel1, c1, lap1, driver2, tel2, c2, lap2, lbl1, lbl2)

            # 4. Generate Graphs using Helpers
            fig_speed = _build_telemetry_fig(fast_data, slow_data)
            fig_2d_dom = _build_dominance_fig(driver1, driver2, c1, c2, tel1, tel2, fast_data, slow_data)

            # Strategy (Race/Sprint only)
            if session_type not in ['Race', 'Sprint']:
                fig_strat = go.Figure().update_layout(template='plotly_dark')
                fig_strat.add_annotation(text="Strategy & Weather only available for Race or Sprint sessions",
                                         showarrow=False, font=dict(size=20), xref="paper", yref="paper", x=0.5, y=0.5)
            else:
                fig_strat = _build_strategy_fig(session, driver1, driver2, lbl1, lbl2, c1, c2)

            # Build session context for AI Q&A
            context = _gather_session_context(session, session_type, driver1, driver2)
            context_header = f"{year} {race} | {session_type} | {driver1} vs {driver2}"
            full_context = f"{context_header}\n\n{context}"

            title_text = f"{year} {race} | {session_type} | {fast_data[0]} vs {slow_data[0]}"
            return fig_speed, fig_2d_dom, fig_strat, full_context, title_text

        except Exception as e:
            print(f"Graph Error: {e}")
            err_fig = go.Figure().update_layout(title=f"Error Loading Telemetry Data", template='plotly_dark')
            return err_fig, err_fig, err_fig, '', "Data Unavailable"


    @app.callback(
        [Output('ai-response-output', 'children'), Output('ai-response-store', 'data')],
        [Input('ai-ask-button', 'n_clicks')],
        [State('ai-question-input', 'value'), State('session-context-store', 'data'), State('ai-response-store', 'data')],
        prevent_initial_call=False
    )
    def ask_ai(n_clicks, question, session_context, store_data):
        """Sends the user's question + session context to Gemini and returns the response."""
        if not dash.ctx.triggered_id:
            if store_data and store_data.get('answer'):
                return html.Div([
                    html.Div([
                        html.Strong("Q: ", style={'color': '#ff4444'}),
                        html.Span(store_data.get('question', ''), style={'color': '#ddd'})
                    ], style={'marginBottom': '1rem', 'paddingBottom': '0.75rem', 'borderBottom': '1px solid #333'}),
                    html.Div([
                        dcc.Markdown(store_data.get('answer', ''), style={'color': '#e0e0e0', 'lineHeight': '1.7'})
                    ])
                ]), dash.no_update
            return html.P("Type a question and click 'Ask AI' to get started.", style={'color': '#888'}), dash.no_update
        
        if not n_clicks or not question or not question.strip():
            return dash.no_update, dash.no_update

        if not GEMINI_API_KEY:
            error_html = html.Div([
                html.P("⚠️ Gemini API key not configured.", style={'color': '#ff4444', 'fontWeight': 'bold'}),
                html.P("Set the GEMINI_API_KEY environment variable before running the app:",
                       style={'color': '#aaa'}),
                html.Code("export GEMINI_API_KEY='your-api-key-here'",
                          style={'color': '#00ff88', 'backgroundColor': '#111', 'padding': '0.5rem',
                                 'display': 'block', 'borderRadius': '4px', 'marginTop': '0.5rem'})
            ])
            return error_html, dash.no_update

        if not session_context:
            return html.P("⚠️ No session data loaded. Select a session and drivers first.", style={'color': '#ff4444'}), dash.no_update

        try:
            import time
            client = genai.Client(api_key=GEMINI_API_KEY)
            prompt = (
                "You are an expert Formula 1 data analyst. You have access to the following telemetry "
                "and race data for a specific F1 session. Answer the user's question with detailed, "
                "data-driven analysis. Reference specific numbers from the data. Be thorough and conclusive.\n\n"
                "=== SESSION DATA ===\n"
                f"{session_context}\n\n"
                "=== USER QUESTION ===\n"
                f"{question}"
            )

            # Try primary model, retry once on rate limit, then fallback
            models_to_try = ['gemini-flash-latest', 'gemini-2.5-flash', 'gemini-3.1-flash-lite', 'gemini-2.5-flash-lite']
            last_error = None

            for model_name in models_to_try:
                try:
                    response = client.models.generate_content(model=model_name, contents=prompt)
                    answer = response.text

                    return html.Div([
                        html.Div([
                            html.Strong("Q: ", style={'color': '#ff4444'}),
                            html.Span(question, style={'color': '#ddd'})
                        ], style={'marginBottom': '1rem', 'paddingBottom': '0.75rem', 'borderBottom': '1px solid #333'}),
                        html.Div([
                            dcc.Markdown(answer, style={'color': '#e0e0e0', 'lineHeight': '1.7'})
                        ])
                    ]), {'question': question, 'answer': answer}
                except Exception as e:
                    last_error = e
                    if '429' not in str(e):
                        break  # Non-rate-limit error, don't retry

            # If all retries failed
            error_str = str(last_error)
            if '429' in error_str:
                return html.Div([
                    html.P("⏳ Rate limit reached on Gemini free tier.", style={'color': '#ffaa00', 'fontWeight': 'bold'}),
                    html.P("The free API has per-minute request limits. Please wait about 60 seconds and try again.",
                           style={'color': '#aaa'}),
                    html.P("Tip: Shorter, more focused questions use fewer tokens and are less likely to hit limits.",
                           style={'color': '#666', 'fontStyle': 'italic'})
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

