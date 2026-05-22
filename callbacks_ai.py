"""AI analysis callbacks: session context building, question answering, history navigation."""
import dash
import logging
from dash import ClientsideFunction
from dash.dependencies import Input, Output, State
from dash.exceptions import PreventUpdate
import flask
import random

from ai_config import AI_ENABLED, GEMINI_API_KEY, GEMINI_MODELS
from ai_cache import USER_DAILY_LIMIT
from callbacks_shared import _timed_callback, _trim_history


def _ai_context_header(params):
    """Return the stable header used to identify loaded AI context."""
    if not params:
        return ""
    return (
        f"{params.get('year')} {params.get('race')} | {params.get('session_type')} | "
        f"{params.get('driver1')} vs {params.get('driver2')}"
    )


def _ai_context_matches_params(session_context, params):
    """Return True when the browser-stored context belongs to current dashboard params."""
    header = _ai_context_header(params)
    return bool(header and isinstance(session_context, str) and session_context.startswith(f"{header}\n\n"))


def _build_ai_session_context(params):
    """Build the AI context for the current dashboard params."""
    if not params or not all(params.get(key) for key in ('year', 'race', 'session_type', 'driver1', 'driver2')):
        return ""

    from data import load_session_with_preload
    from ai_utils import _gather_session_context

    year, race, session_type = params['year'], params['race'], params['session_type']
    driver1, driver2 = params['driver1'], params['driver2']
    session = load_session_with_preload(
        year, race, session_type, laps=True, telemetry=True, weather=True, messages=True
    )
    context = _gather_session_context(session, session_type, driver1, driver2)
    return f"{_ai_context_header(params)}\n\n{context}"


def register_ai_callbacks(app):
    """Register AI analysis callbacks."""

    @app.callback(
        [Output('ai-ask-button', 'disabled'),
         Output('ai-question-input', 'placeholder')],
        [Input('session-context-store', 'data'), Input('main-tabs', 'value'),
         Input('dashboard-params-store', 'data')]
    )
    def update_ai_input_state(session_context, active_tab, params):
        if not AI_ENABLED:
            return True, "AI Analysis is not configured."
        if not params:
            return True, "Update the dashboard before asking AI about a session."
        if active_tab == 'tab-ai' and not _ai_context_matches_params(session_context, params):
            return False, "Ask about this session... context will finish loading if needed."
        return False, 'Ask about this session... (e.g. "What was the optimal strategy in this race?")'

    @app.callback(
        Output('session-context-store', 'data', allow_duplicate=True),
        [Input('dashboard-params-store', 'data'), Input('main-tabs', 'value'),
         Input('preload-status-interval', 'n_intervals'), Input('active-tab-preload-store', 'data')],
        [State('session-context-store', 'data')],
        prevent_initial_call=True
    )
    def update_ai_session_context(params, active_tab, _n, _preload_state, current_context):
        if not params or active_tab != 'tab-ai':
            return dash.no_update

        from data import background_preload_enabled, ensure_preload_for_tab
        status = ensure_preload_for_tab(params, active_tab)
        if background_preload_enabled() and status.get('status') != 'ready':
            return dash.no_update

        if _ai_context_matches_params(current_context, params):
            return dash.no_update

        year, race, session_type = params['year'], params['race'], params['session_type']
        with _timed_callback('update_ai_session_context', year=year, race=race, session=session_type):
            try:
                return _build_ai_session_context(params)
            except Exception as e:
                logging.error(f"AI Context Error: {e}")
                return ""

    # AI history navigation (clientside).
    app.clientside_callback(
        ClientsideFunction(namespace='clientside', function_name='updateAIHistoryIndex'),
        Output('ai-history-index-store', 'data', allow_duplicate=True),
        [Input('ai-prev-btn', 'n_clicks'), Input('ai-next-btn', 'n_clicks')],
        [State('ai-history-store', 'data'), State('ai-history-index-store', 'data')],
        prevent_initial_call=True
    )

    app.clientside_callback(
        ClientsideFunction(namespace='clientside', function_name='renderAIState'),
        [Output('ai-question-display', 'children'),
         Output('ai-answer-display', 'children'),
         Output('ai-question-container', 'style'),
         Output('ai-prev-btn', 'disabled'), Output('ai-next-btn', 'disabled'),
         Output('ai-history-position', 'children'), Output('ai-history-nav', 'style')],
        [Input('ai-history-store', 'data'), Input('ai-history-index-store', 'data')]
    )

    @app.callback(
        [Output('ai-history-store', 'data', allow_duplicate=True),
         Output('ai-history-index-store', 'data', allow_duplicate=True)],
        Input('dashboard-params-store', 'data'),
        prevent_initial_call=True
    )
    def reset_ai_history_on_session_change(_params):
        return [], 0

    @app.callback(
        [Output('ai-history-store', 'data'), Output('ai-question-input', 'value'),
         Output('ai-history-index-store', 'data'), Output('ai-loading-dummy', 'children')],
        [Input('ai-ask-button', 'n_clicks'), Input('ai-question-input', 'n_submit')],
        [State('ai-question-input', 'value'), State('session-context-store', 'data'),
         State('ai-history-store', 'data'), State('dashboard-params-store', 'data')],
        prevent_initial_call=True
    )
    def ask_ai(n_clicks, n_submit, question, session_context, history, params):
        """Send user question + session context to Gemini with guardrails."""
        if history is None:
            history = []
        history = _trim_history(history)

        total_clicks = (n_clicks or 0) + (n_submit or 0)
        if total_clicks == 0 or not question or not question.strip():
            raise PreventUpdate

        # Guard: API key.
        if not GEMINI_API_KEY:
            err = "AI Analysis is not available at this time."
            new_history = _trim_history(history + [{'question': question, 'answer': err}])
            return new_history, '', len(new_history) - 1, ''

        # Guard: session context.
        if not _ai_context_matches_params(session_context, params):
            session_context = ""

        if not session_context and params:
            try:
                with _timed_callback(
                    'ask_ai_context_recovery',
                    year=params.get('year'),
                    race=params.get('race'),
                    session=params.get('session_type')
                ):
                    session_context = _build_ai_session_context(params)
            except Exception as e:
                logging.error(f"AI Context Recovery Error: {e}")
                session_context = ""

        if not session_context:
            if params:
                err = "⚠️ AI session context could not be loaded for the selected dashboard session. Try Update Dashboard again, then ask your question."
            else:
                err = "⚠️ No session data loaded. Select a session and drivers, then click Update Dashboard."
            new_history = _trim_history(history + [{'question': question, 'answer': err}])
            return new_history, '', len(new_history) - 1, ''

        # Guard: input length.
        question = question.strip()
        if len(question) < 10:
            err = "⚠️ Please ask a more specific question (at least 10 characters)."
            new_history = _trim_history(history + [{'question': question, 'answer': err}])
            return new_history, '', len(new_history) - 1, ''
        if len(question) > 300:
            err = "⚠️ Question is too long. Please keep it under 300 characters."
            new_history = _trim_history(history + [{'question': question, 'answer': err}])
            return new_history, '', len(new_history) - 1, ''

        # Guard: per-user rate limit.
        forwarded_for = flask.request.headers.get('X-Forwarded-For', '')
        raw_ip = forwarded_for.split(',')[0].strip() if forwarded_for else flask.request.remote_addr

        from ai_cache import check_user_limit, get_cached_response, store_cached_response
        from ai_utils import build_ai_prompt

        allowed, current_count = check_user_limit(raw_ip)
        if not allowed:
            err = f"🛑 **Daily Limit Reached.** You have used your {USER_DAILY_LIMIT} AI analysis requests for today. Please come back tomorrow for more requests!"
            new_history = _trim_history(history + [{'question': question, 'answer': err}])
            return new_history, '', len(new_history) - 1, ''

        with _timed_callback('ask_ai', question_len=len(question)):
            # Check response cache first.
            cached = get_cached_response(session_context, question)
            if cached:
                new_history = _trim_history(history + [{'question': question, 'answer': cached}])
                return new_history, '', len(new_history) - 1, ''

            # Try configured Gemini models in random order.
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

                    # Append model attribution.
                    attribution = f"\n\n---\n*Response generated by {model_name}*"
                    full_answer = answer + attribution

                    # Cache response for identical future question/context.
                    store_cached_response(session_context, question, full_answer)

                    new_history = _trim_history(history + [{'question': question, 'answer': full_answer}])
                    return new_history, '', len(new_history) - 1, ''

                except Exception as e:
                    last_error = str(e)
                    logging.warning(f"AI model failed; trying fallback model={model_name} error={last_error}")
                    # Try next model on failure.
                    continue

            # All models failed.
            err = f"❌ **AI Analysis encountered an error after trying multiple models.**\n\n```text\n{last_error}\n```\nPlease try again in a moment."
            new_history = _trim_history(history + [{'question': question, 'answer': err}])
            return new_history, '', len(new_history) - 1, ''
