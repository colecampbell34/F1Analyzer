"""Core callbacks: dropdowns, dashboard params, URL sync, leaderboard, lap constraints.

Domain-specific callbacks are registered by sub-modules:
  - callbacks_telemetry  (telemetry tab)
  - callbacks_tabs       (track map, strategy, race, grid pace tabs)
  - callbacks_ai         (AI analysis)
  - callbacks_feedback   (feedback system)
"""
import dash
from dash import html, ClientsideFunction
from dash.dependencies import Input, Output, State
from dash.exceptions import PreventUpdate
import pandas as pd
import logging

from data import (
    _load_drivers_fast, get_teammate_from_info, get_event_schedule_cached,
    get_event_sessions_cached,
    load_session_summary, preload_session,
    get_shared_data, is_race,
)
from ui_utils import _friendly_error, _build_leaderboard_children
from callbacks_shared import (
    _timed_callback,
    _parse_url_state,
    _build_url_search,
    _missing_required_fields,
)

# Sub-module registrations.
from callbacks_telemetry import register_telemetry_callbacks
from callbacks_tabs import register_tab_callbacks
from callbacks_ai import register_ai_callbacks
from callbacks_feedback import register_feedback_callbacks


def register_callbacks(app):
    """Register all application callbacks."""
    _register_core_callbacks(app)
    register_telemetry_callbacks(app)
    register_tab_callbacks(app)
    register_ai_callbacks(app)
    register_feedback_callbacks(app)


def _register_core_callbacks(app):
    """Core navigation, dropdown, and dashboard param callbacks."""

    @app.callback(
        Output('year-dropdown', 'value'),
        Input('url', 'search'),
        State('year-dropdown', 'value')
    )
    def hydrate_year_from_url(url_search, current_year):
        if not url_search:
            return dash.no_update
        url_state = _parse_url_state(url_search)
        if url_state.get('year') and url_state['year'] != current_year:
            return url_state['year']
        return dash.no_update

    @app.callback(
        Output('main-tabs', 'value'),
        Input('url', 'search'),
        State('main-tabs', 'value')
    )
    def hydrate_tab_from_url(url_search, current_tab):
        if not url_search:
            return dash.no_update
        url_state = _parse_url_state(url_search)
        if url_state.get('tab') and url_state['tab'] != current_tab:
            return url_state['tab']
        return dash.no_update

    @app.callback(
        [Output('race-dropdown', 'options'), Output('race-dropdown', 'value')],
        [Input('year-dropdown', 'value')],
        State('url', 'search')
    )
    def update_races(year, url_search):
        if not year:
            return [], None

        url_state = _parse_url_state(url_search)

        try:
            schedule = get_event_schedule_cached(int(year))
            if schedule.empty:
                return [], None

            schedule = schedule[schedule['EventFormat'] != 'testing'].copy()
            race_names = schedule['EventName'].tolist()
            options = [{'label': name, 'value': name} for name in race_names]

            if url_state.get('race') and url_state['race'] in race_names:
                return options, url_state['race']

            return options, None
        except Exception as e:
            print(f"Race Loading Error: {e}")
            return [], None

    @app.callback(
        [Output('session-dropdown', 'options'), Output('session-dropdown', 'value')],
        [Input('race-dropdown', 'value')],
        [State('year-dropdown', 'value'), State('url', 'search')]
    )
    def update_sessions(race, year, url_search):
        if not race or not year:
            return [], None

        url_state = _parse_url_state(url_search)

        try:
            sessions = get_event_sessions_cached(int(year), race)
            if not sessions:
                return [], None

            options = [{'label': s, 'value': s} for s in sessions]
            if url_state.get('session') and url_state['session'] in sessions:
                return options, url_state['session']

            return options, None
        except Exception as e:
            print(f"Session Loading Error: {e}")
            return [], None

    @app.callback(
        [Output('driver1-dropdown', 'options'), Output('driver1-dropdown', 'value'),
         Output('driver2-dropdown', 'options'), Output('driver2-dropdown', 'value')],
        [Input('session-dropdown', 'value')],
        [State('year-dropdown', 'value'), State('race-dropdown', 'value'),
         State('url', 'search')]
    )
    def update_drivers(session_type, year, race, url_search):
        if not session_type or not year or not race:
            return [], None, [], None

        url_state = _parse_url_state(url_search)

        try:
            driver_info = _load_drivers_fast(int(year), race, session_type)
            if not driver_info:
                return [], None, [], None

            options = [
                {'label': f"{d['abbr']} ({d['name']})", 'value': d['abbr']}
                for d in driver_info
            ]
            abbrs = [d['abbr'] for d in driver_info]

            # Logic: Only use URL drivers if the session matches the URL.
            # If the user has changed the session dropdown, url_state['session_type'] 
            # will still be the old one (or None), so we trigger the Top 2 default.
            if session_type == url_state.get('session_type'):
                d1_val = url_state.get('driver1')
                d2_val = url_state.get('driver2')
                
                # Validation
                if d1_val not in abbrs: d1_val = abbrs[0] if abbrs else None
                if d2_val not in abbrs: d2_val = abbrs[1] if len(abbrs) > 1 else None
            else:
                # Session changed or no URL match -> Top 2
                d1_val = abbrs[0] if abbrs else None
                d2_val = abbrs[1] if len(abbrs) > 1 else None

            return options, d1_val, options, d2_val
        except Exception as e:
            print(f"Driver Loading Error: {e}")
            return [], None, [], None

    @app.callback(
        Output('update-dashboard-btn', 'n_clicks'),
        [Input('url', 'search')],
        [State('update-dashboard-btn', 'n_clicks'),
         State('driver1-dropdown', 'value'), State('driver2-dropdown', 'value'),
         State('session-dropdown', 'value'), State('race-dropdown', 'value'),
         State('year-dropdown', 'value')]
    )
    def auto_trigger_dashboard_on_paste(url_search, n_clicks, d1, d2, sess, race, year):
        """Automatically click 'Update Dashboard' if we have a full URL state on first load."""
        if n_clicks > 0 or not url_search:
            raise PreventUpdate
            
        url_state = _parse_url_state(url_search)
        # If the URL has the core params, trigger the button click simulation.
        if all([url_state.get('year'), url_state.get('race'), url_state.get('session_type'),
                url_state.get('driver1'), url_state.get('driver2')]):
            return 1
        raise PreventUpdate

    @app.callback(
        Output('driver2-dropdown', 'value', allow_duplicate=True),
        Input('driver1-dropdown', 'value'),
        [State('session-dropdown', 'value'), State('year-dropdown', 'value'),
         State('race-dropdown', 'value'), State('driver2-dropdown', 'value')],
        prevent_initial_call=True
    )
    def teammate_for_d1(d1, session_type, year, race, current_d2):
        if not d1 or not session_type or not year or not race or current_d2:
            raise PreventUpdate
        try:
            driver_info = _load_drivers_fast(int(year), race, session_type)
            mate = get_teammate_from_info(d1, driver_info)
            return mate if mate else dash.no_update
        except Exception:
            raise PreventUpdate

    @app.callback(
        Output('driver1-dropdown', 'value', allow_duplicate=True),
        Input('driver2-dropdown', 'value'),
        [State('session-dropdown', 'value'), State('year-dropdown', 'value'),
         State('race-dropdown', 'value'), State('driver1-dropdown', 'value')],
        prevent_initial_call=True
    )
    def teammate_for_d2(d2, session_type, year, race, current_d1):
        if not d2 or not session_type or not year or not race or current_d1:
            raise PreventUpdate
        try:
            driver_info = _load_drivers_fast(int(year), race, session_type)
            mate = get_teammate_from_info(d2, driver_info)
            return mate if mate else dash.no_update
        except Exception:
            raise PreventUpdate

    # Leaderboard.
    @app.callback(
        Output('leaderboard-container', 'children'),
        [Input('dashboard-params-store', 'data'),
         Input('update-leaderboard-btn', 'n_clicks')],
        [State('year-dropdown', 'value'),
         State('race-dropdown', 'value'),
         State('session-dropdown', 'value')],
        prevent_initial_call=False
    )
    def update_leaderboard(params, n_clicks, year, race, session_type):
        ctx = dash.callback_context
        if not ctx.triggered:
            if params:
                y, r, s = params['year'], params['race'], params['session_type']
            else:
                raise PreventUpdate
        else:
            trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
            if trigger_id == 'dashboard-params-store':
                if not params:
                    return []
                y, r, s = params['year'], params['race'], params['session_type']
            else:  # update-leaderboard-btn
                if not all([year, race, session_type]):
                    return dash.no_update
                y, r, s = year, race, session_type

        with _timed_callback('update_leaderboard', year=y, race=r, session=s):
            try:
                session = load_session_summary(y, r, s, include_laps=True)
                return _build_leaderboard_children(session, s, year=y)
            except Exception as e:
                return html.Div(_friendly_error(e), style={'color': 'red', 'fontSize': '0.9rem'})

    # Update dashboard params and metadata.
    @app.callback(
        [Output('dashboard-params-store', 'data'), Output('error-dialog', 'displayed'),
         Output('error-dialog', 'message')],
        [Input('update-dashboard-btn', 'n_clicks')],
        [State('driver1-dropdown', 'value'), State('driver2-dropdown', 'value'),
         State('session-dropdown', 'value'), State('race-dropdown', 'value'),
         State('year-dropdown', 'value'), State('main-tabs', 'value')]
    )
    def update_dashboard_params(n_clicks, driver1, driver2, session_type, race, year, active_tab):
        if not n_clicks:
            return dash.no_update, False, ""
        missing = _missing_required_fields({
            'Year': year,
            'Race': race,
            'Session': session_type,
            'Driver 1': driver1,
            'Driver 2': driver2
        })

        if missing:
            msg = (
                "Please select: " + ", ".join(missing) + " before updating.\n\n"
                f"Debug values: year={year!r}, race={race!r}, session={session_type!r}, "
                f"driver1={driver1!r}, driver2={driver2!r}"
            )
            print(f"[update_dashboard_params] missing={missing} values: year={year!r} race={race!r} "
                  f"session={session_type!r} driver1={driver1!r} driver2={driver2!r}")
            return dash.no_update, True, msg

        preload_kwargs = {'laps': True, 'telemetry': False, 'weather': False, 'messages': False}
        if active_tab in ('tab-telemetry', 'tab-trackmap'):
            preload_kwargs['telemetry'] = True
        elif active_tab in ('tab-strategy', 'tab-gridpace'):
            preload_kwargs['weather'] = True
        elif active_tab == 'tab-ai':
            preload_kwargs.update({'telemetry': True, 'weather': True, 'messages': True})
        preload_session(year, race, session_type, **preload_kwargs)

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

        with _timed_callback('update_dashboard_metadata', year=year, race=race, session=session_type):
            try:
                session = load_session_summary(year, race, session_type, include_laps=False)

                # Include finishing position in title when available.
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

                title_text = f"{year} {race} | {session_type} | {lbl1} vs {lbl2}"
                return title_text, ""

            except Exception as e:
                print(f"Metadata Error: {e}")
                return f"{year} {race} | Data Unavailable", ""

    @app.callback(
        Output('url', 'search', allow_duplicate=True),
        [Input('dashboard-params-store', 'data'), Input('main-tabs', 'value')],
        State('url', 'search'),
        prevent_initial_call=True
    )
    def sync_url_with_dashboard(params, active_tab, current_search):
        if not params:
            raise PreventUpdate
        new_search = _build_url_search(params, active_tab)
        if new_search == (current_search or ''):
            return dash.no_update
        return new_search

    @app.callback(
        [Output('d1-lap-number', 'min'), Output('d1-lap-number', 'max'),
         Output('d2-lap-number', 'min'), Output('d2-lap-number', 'max')],
        Input('dashboard-params-store', 'data')
    )
    def update_lap_input_constraints(params):
        if not params:
            return dash.no_update, dash.no_update, dash.no_update, dash.no_update

        year, race, session_type = params['year'], params['race'], params['session_type']

        try:
            # Load lightweight session to determine lap bounds.
            session = load_session_summary(year, race, session_type, include_laps=True)

            # Start from maximum completed lap.
            max_lap = 1
            if not session.laps.empty:
                max_lap = int(session.laps['LapNumber'].max())

            # For Race/Sprint, use official total when available.
            if is_race(session_type):
                official_total = getattr(session, 'total_laps', None)
                if official_total is not None and pd.notna(official_total):
                    max_lap = max(max_lap, int(official_total))

            if max_lap < 1: max_lap = 1

            return 1, max_lap, 1, max_lap
        except Exception:
            return 1, 100, 1, 100

    app.clientside_callback(
        ClientsideFunction(namespace='clientside', function_name='toggleLapNumbers'),
        [Output('d1-lap-number', 'style'), Output('d2-lap-number', 'style')],
        [Input('d1-lap-mode', 'value'), Input('d2-lap-mode', 'value')]
    )
