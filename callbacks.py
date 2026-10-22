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
import logging

from ux_helpers import get_comparison_shortcut_pair
from callbacks_shared import (
    _timed_callback,
    _parse_url_state,
    _build_url_search,
    _missing_required_fields,
    analysis_view_options,
)

# Sub-module registrations.
from callbacks_telemetry import register_telemetry_callbacks
from callbacks_tabs import register_tab_callbacks
from callbacks_ai import register_ai_callbacks
from callbacks_feedback import register_feedback_callbacks


def _loaded_selection_matches(params, year, race, session_type, driver1, driver2):
    """Return whether the sidebar selection exactly matches the loaded analysis."""
    return bool(
        params
        and params.get('year') == year
        and params.get('race') == race
        and params.get('session_type') == session_type
        and params.get('driver1') == driver1
        and params.get('driver2') == driver2
    )


def register_callbacks(app):
    """Register all application callbacks."""
    _register_core_callbacks(app)
    register_telemetry_callbacks(app)
    register_tab_callbacks(app)
    register_ai_callbacks(app)
    register_feedback_callbacks(app)


def _register_core_callbacks(app):
    """Core navigation, dropdown, and dashboard param callbacks."""

    app.clientside_callback(
        ClientsideFunction(namespace='clientside', function_name='resizeVisiblePlots'),
        Output('plot-resize-sentinel', 'children'),
        [Input('main-tabs', 'value'), Input('speed-graph', 'figure'),
         Input('preload-status-store', 'data')]
    )

    app.clientside_callback(
        ClientsideFunction(namespace='clientside', function_name='showPhoneDisclaimer'),
        [Output('phone-disclaimer-modal', 'is_open'),
         Output('phone-disclaimer-store', 'data')],
        [Input('url', 'pathname'), Input('phone-disclaimer-dismiss-btn', 'n_clicks')],
        State('phone-disclaimer-store', 'data')
    )

    @app.callback(
        Output('app-root', 'className'),
        [Input('replay-focus-store', 'data'),
         Input('dashboard-params-store', 'data'),
         Input('year-dropdown', 'value'), Input('race-dropdown', 'value'),
         Input('session-dropdown', 'value'), Input('driver1-dropdown', 'value'),
         Input('driver2-dropdown', 'value'), Input('mobile-setup-open-store', 'data'),
         Input('sidebar-collapsed-store', 'data')]
    )
    def update_app_root_class(replay_focus, params, year, race, session_type, driver1, driver2, mobile_setup_open, sidebar_collapsed):
        classes = ['app-root']
        if mobile_setup_open:
            classes.append('mobile-setup-open')
        if not all([year, race, session_type]):
            classes.append('mobile-flow-needs-session')
        elif not all([driver1, driver2]):
            classes.append('mobile-flow-needs-drivers')
        elif not params:
            classes.append('mobile-flow-ready')
        else:
            loaded_matches_selection = _loaded_selection_matches(
                params, year, race, session_type, driver1, driver2
            )
            classes.append('mobile-flow-loaded' if loaded_matches_selection else 'mobile-flow-ready mobile-flow-dirty')
        if replay_focus:
            classes.append('replay-focus-active')
        if sidebar_collapsed:
            classes.append('sidebar-collapsed')
        return ' '.join(classes)

    @app.callback(
        [Output('selection-dirty-warning', 'children'),
         Output('selection-dirty-warning', 'style')],
        [Input('dashboard-params-store', 'data'),
         Input('year-dropdown', 'value'), Input('race-dropdown', 'value'),
         Input('session-dropdown', 'value'), Input('driver1-dropdown', 'value'),
         Input('driver2-dropdown', 'value')]
    )
    def update_selection_dirty_warning(params, year, race, session_type, driver1, driver2):
        if not params or _loaded_selection_matches(params, year, race, session_type, driver1, driver2):
            return "", {'display': 'none'}
        return "Sidebar selections have changed. Click Load analysis to update this view.", {}

    @app.callback(
        [Output('sidebar-collapsed-store', 'data'),
         Output('sidebar-collapse-btn', 'children')],
        Input('sidebar-collapse-btn', 'n_clicks'),
        State('sidebar-collapsed-store', 'data'),
        prevent_initial_call=True,
    )
    def toggle_sidebar(n_clicks, collapsed):
        if not n_clicks:
            raise PreventUpdate
        next_collapsed = not bool(collapsed)
        return next_collapsed, ('›' if next_collapsed else '‹')

    @app.callback(
        Output('mobile-setup-open-store', 'data'),
        [Input('mobile-edit-selection-btn', 'n_clicks'),
         Input('dashboard-params-store', 'data'),
         Input('year-dropdown', 'value'), Input('race-dropdown', 'value'),
         Input('session-dropdown', 'value'), Input('driver1-dropdown', 'value'),
         Input('driver2-dropdown', 'value')],
        State('mobile-setup-open-store', 'data')
    )
    def toggle_mobile_setup_panel(edit_clicks, params, year, race, session_type, driver1, driver2, current_open):
        trigger_id = dash.ctx.triggered_id
        if trigger_id == 'mobile-edit-selection-btn':
            return not bool(current_open)

        if params and (
            params.get('year') == year
            and params.get('race') == race
            and params.get('session_type') == session_type
            and params.get('driver1') == driver1
            and params.get('driver2') == driver2
        ):
            return False

        return current_open if current_open is not None else False

    @app.callback(
        Output('mobile-edit-selection-btn', 'children'),
        Input('mobile-setup-open-store', 'data')
    )
    def render_mobile_setup_toggle(is_open):
        return 'Close' if is_open else 'Edit'

    @app.callback(
        [Output('replay-focus-store', 'data'),
         Output('replay-focus-btn', 'children'),
         Output('replay-focus-btn', 'outline')],
        [Input('replay-focus-btn', 'n_clicks'), Input('main-tabs', 'value')],
        State('replay-focus-store', 'data'),
        prevent_initial_call=True
    )
    def toggle_replay_focus(n_clicks, active_tab, current):
        trigger_id = dash.ctx.triggered_id
        if trigger_id == 'main-tabs' and active_tab != 'tab-telemetry':
            return False, 'Replay Focus', True
        if trigger_id != 'replay-focus-btn':
            raise PreventUpdate
        next_value = not bool(current)
        return next_value, ('Exit Focus' if next_value else 'Replay Focus'), (not next_value)

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
        Output('analysis-view-panels', 'value'),
        Input('main-tabs', 'value')
    )
    def render_selected_analysis_view(active_tab):
        return active_tab or 'tab-trackmap'

    @app.callback(
        Output('trackmap-mode', 'value'),
        Input('url', 'search')
    )
    def hydrate_view_state_from_url(url_search):
        if not url_search:
            return dash.no_update
        url_state = _parse_url_state(url_search)
        return url_state.get('trackmap_mode') or dash.no_update

    @app.callback(
        [Output('latest-race-store', 'data'),
         Output('year-dropdown', 'value', allow_duplicate=True)],
        Input('latest-race-btn', 'n_clicks'),
        prevent_initial_call=True
    )
    def select_latest_race(n_clicks):
        if not n_clicks:
            raise PreventUpdate

        from data import get_latest_race_session_default

        try:
            latest = get_latest_race_session_default()
        except Exception as exc:
            logging.warning("Latest race lookup failed error_type=%s", type(exc).__name__)
            return dash.no_update, dash.no_update
        if not latest:
            raise PreventUpdate

        return latest, latest['year']

    @app.callback(
        [Output('race-dropdown', 'options'), Output('race-dropdown', 'value')],
        [Input('year-dropdown', 'value'), Input('latest-race-store', 'data')],
        [State('url', 'search'), State('race-dropdown', 'value')]
    )
    def update_races(year, latest_race, url_search, persisted_race):
        if not year:
            return [], None

        url_state = _parse_url_state(url_search)

        try:
            from data import get_event_schedule

            schedule = get_event_schedule(int(year))
            race_names = [event['race'] for event in schedule]
            if not race_names:
                return [], None

            options = [{'label': name, 'value': name} for name in race_names]

            if (
                latest_race
                and int(latest_race.get('year')) == int(year)
                and latest_race.get('race') in race_names
            ):
                return options, latest_race['race']

            if url_state.get('race') and url_state['race'] in race_names:
                return options, url_state['race']

            if persisted_race in race_names:
                return options, persisted_race

            return options, None
        except Exception as e:
            logging.error(f"Race Loading Error: {e}")
            return [], None

    @app.callback(
        [Output('session-dropdown', 'options'), Output('session-dropdown', 'value')],
        [Input('race-dropdown', 'value'), Input('latest-race-store', 'data')],
        [State('year-dropdown', 'value'), State('url', 'search'), State('session-dropdown', 'value')]
    )
    def update_sessions(race, latest_race, year, url_search, persisted_session):
        if not race or not year:
            return [], None

        url_state = _parse_url_state(url_search)

        try:
            from data import get_event_schedule

            event = next((item for item in get_event_schedule(int(year)) if item['race'] == race), None)
            sessions = event.get('sessions', []) if event else []
            if not sessions:
                return [], None

            options = [{'label': s, 'value': s} for s in sessions]
            if (
                latest_race
                and int(latest_race.get('year')) == int(year)
                and latest_race.get('race') == race
                and latest_race.get('session_type') in sessions
            ):
                return options, latest_race['session_type']

            if url_state.get('session_type') and url_state['session_type'] in sessions:
                return options, url_state['session_type']

            if persisted_session in sessions:
                return options, persisted_session

            return options, None
        except Exception as e:
            logging.error(f"Session Loading Error: {e}")
            return [], None

    @app.callback(
        [Output('driver1-dropdown', 'options'), Output('driver1-dropdown', 'value'),
         Output('driver2-dropdown', 'options'), Output('driver2-dropdown', 'value')],
        [Input('session-dropdown', 'value')],
        [State('year-dropdown', 'value'), State('race-dropdown', 'value'),
         State('url', 'search'), State('driver1-dropdown', 'value'),
         State('driver2-dropdown', 'value')]
    )
    def update_drivers(session_type, year, race, url_search, persisted_d1, persisted_d2):
        if not session_type or not year or not race:
            return [], None, [], None

        url_state = _parse_url_state(url_search)

        try:
            from data import _load_drivers_fast

            driver_info = _load_drivers_fast(int(year), race, session_type)
            if not driver_info:
                return [], None, [], None

            options = [
                {'label': f"{d['abbr']} ({d['name']})", 'value': d['abbr']}
                for d in driver_info
            ]
            abbrs = [d['abbr'] for d in driver_info]

            # Only a complete matching URL may supply a driver. A partial or
            # stale query string must not replace persisted drivers with Top 2
            # during browser hydration.
            url_matches_current_session = (
                url_state.get('year') == int(year)
                and url_state.get('race') == race
                and url_state.get('session_type') == session_type
            )
            url_d1 = url_state.get('driver1') if url_matches_current_session else None
            url_d2 = url_state.get('driver2') if url_matches_current_session else None
            d1_val = (
                url_d1 if url_d1 in abbrs
                else persisted_d1 if persisted_d1 in abbrs
                else (abbrs[0] if abbrs else None)
            )
            d2_val = (
                url_d2 if url_d2 in abbrs
                else persisted_d2 if persisted_d2 in abbrs
                else (abbrs[1] if len(abbrs) > 1 else None)
            )

            return options, d1_val, options, d2_val
        except Exception as e:
            logging.error(f"Driver Loading Error: {e}")
            return [], None, [], None

    @app.callback(
        [Output('driver1-dropdown', 'value', allow_duplicate=True),
         Output('driver2-dropdown', 'value', allow_duplicate=True)],
        [Input('shortcut-top-two', 'n_clicks'),
         Input('shortcut-closest', 'n_clicks'),
         Input('mobile-shortcut-top-two', 'n_clicks'),
         Input('mobile-shortcut-closest', 'n_clicks')],
        [State('session-dropdown', 'value'), State('year-dropdown', 'value'),
         State('race-dropdown', 'value'), State('driver1-dropdown', 'value'),
         State('driver2-dropdown', 'value')],
        prevent_initial_call=True
    )
    def apply_comparison_shortcut(*args):
        session_type, year, race, current_d1, current_d2 = args[-5:]
        if not all([session_type, year, race]):
            raise PreventUpdate
        trigger_id = dash.ctx.triggered_id
        if not trigger_id:
            raise PreventUpdate
        shortcut = str(trigger_id).replace('mobile-', '').replace('shortcut-', '').replace('-', '_')
        try:
            from data import _load_drivers_fast, load_session_summary

            driver_info = _load_drivers_fast(int(year), race, session_type)
            session = load_session_summary(year, race, session_type, include_laps=False)
            d1, d2 = get_comparison_shortcut_pair(
                shortcut,
                driver_info,
                current_driver1=current_d1,
                current_driver2=current_d2,
                results=getattr(session, 'results', None)
            )
            if not d1 or not d2:
                raise PreventUpdate
            return d1, d2
        except Exception as e:
            logging.error(f"Comparison Shortcut Error: {e}")
            raise PreventUpdate

    @app.callback(
        [Output('driver1-dropdown', 'value', allow_duplicate=True),
         Output('driver2-dropdown', 'value', allow_duplicate=True),
         Output('teammate-toast', 'is_open'),
         Output('teammate-toast', 'children')],
        [Input('teammate1-btn', 'n_clicks'),
         Input('teammate2-btn', 'n_clicks')],
        [State('session-dropdown', 'value'), State('year-dropdown', 'value'),
         State('race-dropdown', 'value'), State('driver1-dropdown', 'value'),
         State('driver2-dropdown', 'value')],
        prevent_initial_call=True
    )
    def apply_teammate_button(_d1_clicks, _d2_clicks, session_type, year, race, current_d1, current_d2):
        if not all([session_type, year, race]):
            return dash.no_update, dash.no_update, True, "Select a session before using the teammate shortcut."

        trigger_id = dash.ctx.triggered_id
        if trigger_id == 'teammate1-btn':
            source_driver = current_d1
            source_label = "Driver 1"
        elif trigger_id == 'teammate2-btn':
            source_driver = current_d2
            source_label = "Driver 2"
        else:
            raise PreventUpdate

        if not source_driver:
            return dash.no_update, dash.no_update, True, f"Select {source_label} before using the teammate shortcut."

        try:
            from data import _load_drivers_fast, get_teammate_from_info

            driver_info = _load_drivers_fast(int(year), race, session_type)
            teammate = get_teammate_from_info(source_driver, driver_info)
            if not teammate:
                return dash.no_update, dash.no_update, True, f"No teammate found for {source_driver} in this session."

            if trigger_id == 'teammate1-btn':
                return dash.no_update, teammate, False, dash.no_update
            return teammate, dash.no_update, False, dash.no_update
        except PreventUpdate:
            raise
        except Exception as e:
            logging.error(f"Teammate Button Error: {e}")
            return dash.no_update, dash.no_update, True, "Could not load teammate data for this session."

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
            from data import _load_drivers_fast, get_teammate_from_info

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
            from data import _load_drivers_fast, get_teammate_from_info

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
                from data import load_session_with_preload
                from ui_utils import _build_leaderboard_children

                # The optional rail only needs lap metadata; keep it lighter
                # than the active analysis view's telemetry profile.
                session = load_session_with_preload(y, r, s, laps=True, telemetry=False)
                return _build_leaderboard_children(session, s, year=y, race=r)
            except Exception as e:
                from ui_utils import _friendly_error

                logging.error(f"Leaderboard Error: {e}")
                return html.Div(_friendly_error(e), style={'color': 'red', 'fontSize': '0.9rem'})

    # Update dashboard params and metadata.
    @app.callback(
        [Output('dashboard-params-store', 'data'), Output('error-dialog', 'displayed'),
         Output('error-dialog', 'message')],
        [Input('update-dashboard-btn', 'n_clicks'),
         Input('mobile-update-dashboard-btn', 'n_clicks')],
        [State('driver1-dropdown', 'value'), State('driver2-dropdown', 'value'),
         State('session-dropdown', 'value'), State('race-dropdown', 'value'),
         State('year-dropdown', 'value'), State('main-tabs', 'value'),
         State('url', 'search')],
        prevent_initial_call=True,
    )
    def update_dashboard_params(n_clicks, mobile_clicks, driver1, driver2, session_type, race, year, active_tab, url_search):
        if not ((n_clicks or 0) + (mobile_clicks or 0)):
            return dash.no_update, False, ""
        missing = _missing_required_fields({
            'Year': year,
            'Race': race,
            'Session': session_type,
            'Driver 1': driver1,
            'Driver 2': driver2
        })

        if missing:
            url_state = _parse_url_state(url_search)
            if all(url_state.get(key) for key in ('year', 'race', 'session_type', 'driver1', 'driver2')):
                # A click count can fire while a bookmarked URL is still
                # hydrating its dependent dropdowns. Use the complete URL state
                # so the initial analysis still loads instead of showing a
                # misleading missing-selection warning.
                year = int(url_state['year'])
                race = url_state['race']
                session_type = url_state['session_type']
                driver1 = url_state['driver1']
                driver2 = url_state['driver2']
                active_tab = url_state.get('tab') or active_tab
                missing = []
            else:
                msg = (
                    "Please select: " + ", ".join(missing) + " before updating.\n\n"
                    f"Debug values: year={year!r}, race={race!r}, session={session_type!r}, "
                    f"driver1={driver1!r}, driver2={driver2!r}"
                )
                logging.warning(
                    "[update_dashboard_params] missing=%s values: year=%r race=%r session=%r driver1=%r driver2=%r",
                    missing, year, race, session_type, driver1, driver2,
                )
                return dash.no_update, True, msg

        from data import get_preload_kwargs_for_tab, preload_session

        preload_kwargs = get_preload_kwargs_for_tab(active_tab)
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
                import pandas as pd
                from data import get_driver_info, load_session_summary

                session = load_session_summary(year, race, session_type, include_laps=False)
                info_by_abbr = {
                    item['abbr']: item
                    for item in get_driver_info(session)
                    if item.get('abbr')
                }

                def _driver_title(driver):
                    info = info_by_abbr.get(driver, {})
                    full_name = info.get('name') or driver
                    color = info.get('color') or '#d8d8d4'
                    position = None
                    try:
                        value = session.results.loc[
                            session.results['abbreviation'] == driver, 'position'
                        ].values[0]
                        position = int(value) if pd.notna(value) else None
                    except (IndexError, KeyError, TypeError, ValueError):
                        position = None
                    position_text = f"P{position}" if position else "Selected driver"
                    return html.Span([
                        html.Span(driver, className='matchup-driver-code'),
                        html.Span(full_name, className='matchup-driver-name'),
                        html.Span(position_text, className='matchup-driver-position'),
                    ], className='matchup-driver', style={'--driver-accent': color})

                title = html.Div([
                    html.Div(f"{year} · {race} · {session_type}", className='session-title-context'),
                    html.Div([
                        _driver_title(driver1),
                        html.Span("VS", className='matchup-versus'),
                        _driver_title(driver2),
                    ], className='driver-matchup-title'),
                ], className='comparison-header-title')
                return title, ""

            except Exception as e:
                logging.error(f"Metadata Error: {e}")
                return f"{year} {race} | Data Unavailable", ""

    @app.callback(
        Output('mobile-session-summary', 'children'),
        [Input('dashboard-params-store', 'data'),
         Input('year-dropdown', 'value'), Input('race-dropdown', 'value'),
         Input('session-dropdown', 'value'),
         Input('driver1-dropdown', 'value'), Input('driver2-dropdown', 'value')]
    )
    def update_mobile_session_summary(params, year, race, session_type, d1, d2):
        if params:
            return (
                f"{params['year']} {str(params['race']).replace('Grand Prix', 'GP')} | "
                f"{params['session_type']} | {params['driver1']} vs {params['driver2']}"
            )
        parts = [str(part) for part in [year, race, session_type] if part]
        drivers = ' vs '.join(str(part) for part in [d1, d2] if part)
        if parts and drivers:
            return f"{' | '.join(parts)} | {drivers}"
        if parts:
            return ' | '.join(parts)
        return "Choose a session and comparison"

    @app.callback(
        [Output('loading-status-banner', 'children'),
         Output('loading-status-banner', 'className'),
         Output('preload-status-store', 'data'),
         Output('preload-status-interval', 'disabled')],
        [Input('dashboard-params-store', 'data'),
         Input('main-tabs', 'value'),
         Input('preload-status-interval', 'n_intervals'),
         Input('active-tab-preload-store', 'data')]
    )
    def update_loading_status(params, active_tab, _n, _preload_state):
        if not params:
            return (
                html.Span(
                    "Choose a session and click Load analysis.",
                    title='This status tracks whether the selected session profile is idle, loading, cached, or failed.'
                ),
                "loading-status-banner sr-only status-idle",
                {'status': 'idle'},
                True
            )
        from data import get_preload_status_for_tab

        status = get_preload_status_for_tab(params, active_tab)
        state = status.get('status', 'idle')
        profile = status.get('profile', 'session')
        session_label = f"{params['year']} {params['race']} {params['session_type']}"
        if state in ('queued', 'loading'):
            text = f"Loading {profile} data for {session_label}..."
        elif state == 'ready':
            text = f"Ready: {profile} data is cached for {session_label}."
        elif state == 'error':
            text = f"Could not load {profile} data: {status.get('error') or 'unknown error'}"
        elif state == 'direct':
            text = f"Loading {profile} data for {session_label}…"
        else:
            text = f"Ready to load {profile} data for {session_label}."
        return html.Span(
            text,
            title='This status tracks whether the selected session profile is idle, loading, cached, or failed.'
        ), f"loading-status-banner sr-only status-{state}", status, state not in ('queued', 'loading')

    @app.callback(
        Output('graph-summary', 'children'),
        [Input('dashboard-params-store', 'data'),
         Input('main-tabs', 'value')]
    )
    def update_graph_summary(params, active_tab):
        if not params:
            return "No chart loaded yet. Select a session and two drivers."
        tab_label = {
            'tab-telemetry': 'telemetry',
            'tab-trackmap': 'track map',
            'tab-strategy': 'strategy',
            'tab-racepace': 'race and pace',
            'tab-ai': 'AI analysis',
        }.get(active_tab, 'analysis')
        return (
            f"{tab_label.title()} view for {params['year']} {params['race']} "
            f"{params['session_type']}, comparing {params['driver1']} and {params['driver2']}."
        )

    @app.callback(
        Output('active-tab-preload-store', 'data'),
        [Input('dashboard-params-store', 'data'), Input('main-tabs', 'value')]
    )
    def preload_active_tab(params, active_tab):
        if not params:
            return {'status': 'idle'}
        from data import ensure_preload_for_tab
        return ensure_preload_for_tab(params, active_tab)

    @app.callback(
        Output('url', 'search', allow_duplicate=True),
        [Input('dashboard-params-store', 'data'), Input('main-tabs', 'value'),
         Input('year-dropdown', 'value'), Input('race-dropdown', 'value'),
         Input('session-dropdown', 'value'), Input('driver1-dropdown', 'value'),
         Input('driver2-dropdown', 'value'),
         Input('d1-lap-dropdown', 'value'), Input('d2-lap-dropdown', 'value'),
         Input('trackmap-d1-lap-dropdown', 'value'), Input('trackmap-d2-lap-dropdown', 'value'),
         Input('trackmap-mode', 'value')],
        State('url', 'search'),
        prevent_initial_call=True
    )
    def sync_url_with_dashboard(
        params, active_tab, year, race, session_type, driver1, driver2,
        d1_lap_value, d2_lap_value,
        tm_d1_lap_value, tm_d2_lap_value, trackmap_mode, current_search,
    ):
        selected_params = (
            {
                'year': year,
                'race': race,
                'session_type': session_type,
                'driver1': driver1,
                'driver2': driver2,
            }
            if all([year, race, session_type, driver1, driver2])
            else params
        )
        if not selected_params:
            raise PreventUpdate
        d1_specific = d1_lap_value not in (None, '', 'fastest')
        d2_specific = d2_lap_value not in (None, '', 'fastest')
        tm_d1_specific = tm_d1_lap_value not in (None, '', 'fastest')
        tm_d2_specific = tm_d2_lap_value not in (None, '', 'fastest')
        new_search = _build_url_search(selected_params, active_tab, {
            'd1_lap_mode': 'specific' if d1_specific else 'fastest',
            'd2_lap_mode': 'specific' if d2_specific else 'fastest',
            'd1_lap': d1_lap_value if d1_specific else None,
            'd2_lap': d2_lap_value if d2_specific else None,
            'tm_d1_lap_mode': 'specific' if tm_d1_specific else 'fastest',
            'tm_d2_lap_mode': 'specific' if tm_d2_specific else 'fastest',
            'tm_d1_lap': tm_d1_lap_value if tm_d1_specific else None,
            'tm_d2_lap': tm_d2_lap_value if tm_d2_specific else None,
            'trackmap_mode': trackmap_mode,
        })
        if new_search == (current_search or ''):
            return dash.no_update
        return new_search

    @app.callback(Output('main-tabs', 'options'), Input('session-dropdown', 'value'))
    def update_tab_availability(session_type):
        if not session_type:
            return analysis_view_options()
        from data import is_qualifying, is_practice

        disabled_views = set()
        if is_qualifying(session_type) or is_practice(session_type):
            disabled_views.add('tab-strategy')
        return analysis_view_options(disabled_views)

    @app.callback(
        Output('main-tabs', 'value', allow_duplicate=True),
        [Input('session-dropdown', 'value'), Input('main-tabs', 'value')],
        prevent_initial_call=True
    )
    def move_from_unavailable_tab(session_type, active_tab):
        if not session_type:
            raise PreventUpdate
        from data import is_qualifying, is_practice

        if active_tab == 'tab-strategy' and (is_qualifying(session_type) or is_practice(session_type)):
            return 'tab-trackmap'
        raise PreventUpdate

    @app.callback(
        [Output('d1-lap-dropdown', 'options'), Output('d1-lap-dropdown', 'value'),
         Output('d2-lap-dropdown', 'options'), Output('d2-lap-dropdown', 'value'),
         Output('trackmap-d1-lap-dropdown', 'options'), Output('trackmap-d1-lap-dropdown', 'value'),
         Output('trackmap-d2-lap-dropdown', 'options'), Output('trackmap-d2-lap-dropdown', 'value')],
        [Input('dashboard-params-store', 'data')],
        [State('d1-lap-dropdown', 'value'), State('d2-lap-dropdown', 'value'),
         State('trackmap-d1-lap-dropdown', 'value'), State('trackmap-d2-lap-dropdown', 'value'),
         State('url', 'search')]
    )
    def update_lap_dropdown_options(
        params, current_d1_lap, current_d2_lap,
        current_tm_d1_lap, current_tm_d2_lap, url_search,
    ):
        if not params:
            default_options = [{'label': 'Fastest', 'value': 'fastest'}]
            return (
                default_options, 'fastest', default_options, 'fastest',
                default_options, 'fastest', default_options, 'fastest',
            )

        year, race, session_type = params['year'], params['race'], params['session_type']

        try:
            import pandas as pd
            from data import load_session_with_preload

            # The active view preload owns this profile, so lap controls should
            # join it rather than begin another identical session request.
            session = load_session_with_preload(
                year, race, session_type, laps=True, telemetry=True, weather=False, messages=False,
            )

            def _options_for_driver(driver):
                options = [{'label': 'Fastest', 'value': 'fastest'}]
                try:
                    laps = session.laps[session.laps['abbreviation'] == driver]
                    timed = pd.to_numeric(laps['lap_duration'], errors='coerce')
                    lap_numbers = sorted(
                        int(lap)
                        for lap in laps.loc[timed.gt(0), 'lap_number'].dropna().unique().tolist()
                    )
                except Exception:
                    lap_numbers = []
                options.extend({'label': f'Lap {lap}', 'value': lap} for lap in lap_numbers)
                return options

            def _url_value(prefix):
                url_state = _parse_url_state(url_search)
                if not (
                    url_state.get('year') == params.get('year')
                    and url_state.get('race') == params.get('race')
                    and url_state.get('session_type') == params.get('session_type')
                    and url_state.get('driver1') == params.get('driver1')
                    and url_state.get('driver2') == params.get('driver2')
                ):
                    return None
                mode = url_state.get(f'{prefix}_lap_mode')
                lap = url_state.get(f'{prefix}_lap')
                return lap if mode == 'specific' and lap else None

            def _valid_value(current_value, options, fallback_from_url):
                values = {option['value'] for option in options}
                if fallback_from_url in values:
                    return fallback_from_url
                if current_value in values:
                    return current_value
                return 'fastest'

            d1_options = _options_for_driver(params['driver1'])
            d2_options = _options_for_driver(params['driver2'])

            return (
                d1_options,
                _valid_value(current_d1_lap, d1_options, _url_value('d1')),
                d2_options,
                _valid_value(current_d2_lap, d2_options, _url_value('d2')),
                d1_options,
                _valid_value(current_tm_d1_lap, d1_options, _url_value('tm_d1')),
                d2_options,
                _valid_value(current_tm_d2_lap, d2_options, _url_value('tm_d2')),
            )
        except Exception:
            default_options = [{'label': 'Fastest', 'value': 'fastest'}]
            return (
                default_options, 'fastest', default_options, 'fastest',
                default_options, 'fastest', default_options, 'fastest',
            )

    app.clientside_callback(
        ClientsideFunction(namespace='clientside', function_name='downloadActiveChart'),
        Output('export-status', 'children', allow_duplicate=True),
        Input('download-active-chart-btn', 'n_clicks'),
        [State('main-tabs', 'value'), State('main-title', 'children')],
        prevent_initial_call=True
    )
