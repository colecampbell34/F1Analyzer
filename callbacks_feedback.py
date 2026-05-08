"""Feedback system callbacks: modal, submission, review panel, CSV download."""
import dash
from dash import dcc, ClientsideFunction
from dash.dependencies import Input, Output, State
from dash.exceptions import PreventUpdate
import flask
from datetime import datetime, timezone

import pandas as pd

from feedback import store_feedback_entry, load_feedback_entries
from ui_utils import _feedback_admin_authorized, _build_feedback_review_panel, _build_perf_review_panel
from perf_monitor import get_perf_snapshot
from data import get_preload_registry_snapshot, get_cache_stats


def register_feedback_callbacks(app):
    """Register all feedback-related callbacks."""

    # Feedback modal toggle (clientside).
    app.clientside_callback(
        ClientsideFunction(namespace='clientside', function_name='toggleFeedbackModal'),
        Output('feedback-modal', 'is_open'),
        [Input('open-feedback-modal-btn', 'n_clicks'),
         Input('mobile-open-feedback-modal-btn', 'n_clicks'),
         Input('cancel-feedback-btn', 'n_clicks'),
         Input('feedback-refresh-store', 'data')],
        State('feedback-modal', 'is_open'),
        prevent_initial_call=True
    )

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
         Output('feedback-review-controls', 'style'),
         Output('perf-review-panel', 'children'),
         Output('perf-review-controls', 'style')],
        [Input('url', 'search'),
         Input('feedback-refresh-store', 'data'),
         Input('refresh-feedback-review-btn', 'n_clicks'),
         Input('refresh-perf-review-btn', 'n_clicks')]
    )
    def update_feedback_review_panel(url_search, refresh_data, refresh_clicks, perf_clicks):
        if not _feedback_admin_authorized(url_search):
            return [], {'display': 'none'}, [], {'display': 'none'}
        control_style = {
            'display': 'flex',
            'gap': '0.5rem',
            'marginBottom': '1rem'
        }
        return (
            _build_feedback_review_panel(load_feedback_entries(limit=100)),
            control_style,
            _build_perf_review_panel(get_perf_snapshot(), get_preload_registry_snapshot(), get_cache_stats()),
            control_style
        )

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
        filename = f"feedback-inbox-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}.csv"
        return dcc.send_data_frame(df.to_csv, filename, index=False)
