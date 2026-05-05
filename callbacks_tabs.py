"""Visualization tab callbacks: Track Map, Strategy, Race Analysis, Grid Pace."""
import dash
import logging
from dash import dcc, html
from dash.dependencies import Input, Output

from data import (
    get_shared_data, is_qualifying, is_race, is_practice,
    load_session_with_preload, ensure_preload_for_tab,
)
from graphs import (
    _build_dominance_fig, _build_strategy_fig,
    _build_deg_fig, _build_race_gaps_fig, _build_grid_pace_fig,
    _build_pit_stops_fig, _build_driver_radar,
)
from graph_shared import _sort_fastest_driver, _error_figure, _not_applicable_figure, _loading_figure
from callbacks_shared import _timed_callback
from ui_utils import _friendly_error
from telemetry_prep import prepare_selected_lap_comparison


def register_tab_callbacks(app):
    """Register callbacks for Track Map, Strategy, Race, and Grid Pace tabs."""

    # Track map tab.
    @app.callback(
        [Output('2d-dominance-graph', 'figure'), Output('driver-dna-container', 'children')],
        [Input('dashboard-params-store', 'data'), Input('main-tabs', 'value'),
         Input('trackmap-mode', 'value'), Input('preload-status-store', 'data')]
    )
    def update_dominance(params, active_tab, mode, _preload_status):
        if not params or active_tab != 'tab-trackmap':
            return dash.no_update, dash.no_update
        status = ensure_preload_for_tab(params, active_tab)
        if status.get('status') in ('queued', 'loading', 'idle'):
            return _loading_figure(
                f"Loading track map data for {params['year']} {params['race']} {params['session_type']}..."
            ), html.Div("DNA analysis loading...", style={'color': '#888', 'textAlign': 'center'})
        if status.get('status') == 'error':
            return _error_figure(_friendly_error(status.get('error') or 'Session data failed to load.')), html.Div(
                "DNA analysis unavailable"
            )
        with _timed_callback('update_dominance', year=params['year'], race=params['race'], session=params['session_type']):
            try:
                cmp = prepare_selected_lap_comparison(params)
                session = cmp['session']
                d1, d2 = cmp['d1'], cmp['d2']
                lbl1, lbl2, c1, c2 = cmp['lbl1'], cmp['lbl2'], cmp['c1'], cmp['c2']
                lap1, lap2 = cmp['lap1'], cmp['lap2']
                tel1, tel2 = cmp['tel1'], cmp['tel2']

                fast_data, slow_data = _sort_fastest_driver(
                    d1, tel1, c1, lap1, d2, tel2, c2, lap2, lbl1, lbl2
                )

                # Build Driver DNA radar chart.
                radar_fig, dna_legend = _build_driver_radar(d1, d2, c1, c2, tel1, tel2)
                legend_ui = html.Div(
                    [
                        html.Span([html.Strong(f"{letter}:"), f" {label}"])
                        for (letter, label) in (dna_legend or [])
                    ],
                    style={
                        'display': 'flex',
                        'flexWrap': 'wrap',
                        'gap': '4px 10px',
                        'justifyContent': 'center',
                        'color': '#bbb',
                        'fontSize': '0.72rem',
                        'lineHeight': '1.15',
                        'marginBottom': '6px',
                    }
                )
                norm_note = html.Div(
                    [
                        "Normalization: values are compressed around 50 based on relative differences between the two drivers.",
                        html.Br(),
                        "Small raw deltas can still be visible, but won't dominate the shape."
                    ],
                    style={
                        'textAlign': 'center',
                        'color': '#888',
                        'fontSize': '0.70rem',
                        'lineHeight': '1.15',
                        'marginBottom': '6px',
                        'whiteSpace': 'normal',
                        'wordBreak': 'break-word',
                        'maxWidth': '100%'
                    }
                )
                dna_ui = html.Div(
                    [
                        html.H6(
                            [
                                html.Span("Driver DNA"),
                                html.Span(
                                    "?",
                                    className="help-tip tip-intermediate",
                                    title=(
                                        "Driver DNA summarizes relative driving traits from the selected laps. "
                                        "It is normalized between the two drivers, so use it as a shape comparison rather than an absolute rating."
                                    )
                                )
                            ],
                            style={
                                'textAlign': 'center',
                                'color': '#ff4444',
                                'marginBottom': '6px'
                            }
                        ),
                        legend_ui,
                        norm_note,
                        dcc.Graph(
                            figure=radar_fig,
                            config={'displayModeBar': False},
                            style={'flex': '1 1 auto', 'minHeight': 0}
                        )
                    ],
                    style={
                        'backgroundColor': '#151515',
                        'borderRadius': '8px',
                        'padding': '10px',
                        'height': '100%',
                        'display': 'flex',
                        'flexDirection': 'column'
                    }
                )

                return _build_dominance_fig(
                    d1, d2, c1, c2, tel1, tel2, fast_data, slow_data,
                    mode=mode, session=session
                ), dna_ui
            except Exception as e:
                logging.error(f"Dominance Error: {e}")
                return _error_figure(_friendly_error(e)), html.Div("DNA analysis unavailable")

    # Strategy tab.
    @app.callback(
        [Output('strategy-graph', 'figure'), Output('deg-graph', 'figure')],
        [Input('dashboard-params-store', 'data'), Input('main-tabs', 'value'),
         Input('preload-status-store', 'data')]
    )
    def update_strategy(params, active_tab, _preload_status):
        if not params or active_tab != 'tab-strategy':
            return dash.no_update, dash.no_update
        status = ensure_preload_for_tab(params, active_tab)
        if status.get('status') in ('queued', 'loading', 'idle'):
            fig = _loading_figure(
                f"Loading strategy data for {params['year']} {params['race']} {params['session_type']}..."
            )
            return fig, fig
        if status.get('status') == 'error':
            err = _error_figure(_friendly_error(status.get('error') or 'Session data failed to load.'))
            return err, err
        with _timed_callback('update_strategy', year=params['year'], race=params['race'], session=params['session_type']):
            try:
                # Strategy view needs laps + weather; no telemetry.
                session, d1, d2, lbl1, lbl2, c1, c2 = get_shared_data(params, laps=True, telemetry=False, weather=True)
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
                logging.error(f"Strategy Error: {e}")
                err = _error_figure(_friendly_error(e))
                return err, err

    # Race tab.
    @app.callback(
        [Output('race-gaps-graph', 'figure'), Output('pit-stops-graph', 'figure')],
        [Input('dashboard-params-store', 'data'), Input('main-tabs', 'value'),
         Input('preload-status-store', 'data')]
    )
    def update_race_analysis(params, active_tab, _preload_status):
        if not params or active_tab != 'tab-race':
            return dash.no_update, dash.no_update
        status = ensure_preload_for_tab(params, active_tab)
        if status.get('status') in ('queued', 'loading', 'idle'):
            fig = _loading_figure(
                f"Loading race data for {params['year']} {params['race']} {params['session_type']}..."
            )
            return fig, fig
        if status.get('status') == 'error':
            err = _error_figure(_friendly_error(status.get('error') or 'Session data failed to load.'))
            return err, err
        with _timed_callback('update_race_analysis', year=params['year'], race=params['race'], session=params['session_type']):
            try:
                # Race analysis needs laps only.
                session, d1, d2, lbl1, lbl2, c1, c2 = get_shared_data(params, laps=True, telemetry=False)
                session_type = params['session_type']

                if is_race(session_type):
                    fig_gaps = _build_race_gaps_fig(session, d1, d2, lbl1, lbl2, c1, c2)
                    fig_pits = _build_pit_stops_fig(session, d1, d2, lbl1, lbl2, c1, c2)
                else:
                    fig_gaps = _not_applicable_figure("Race gap analysis available for Race & Sprint sessions only")
                    fig_pits = _not_applicable_figure("Pit stop data available for Race & Sprint sessions only")
                return fig_gaps, fig_pits
            except Exception as e:
                logging.error(f"Error in callback: {e}")
                err = _error_figure(_friendly_error(e))
                return err, err

    # Grid pace tab.
    @app.callback(
        Output('grid-pace-graph', 'figure'),
        [Input('dashboard-params-store', 'data'), Input('main-tabs', 'value'),
         Input('preload-status-store', 'data')]
    )
    def update_grid_pace(params, active_tab, _preload_status):
        if not params or active_tab != 'tab-gridpace':
            return dash.no_update
        status = ensure_preload_for_tab(params, active_tab)
        if status.get('status') in ('queued', 'loading', 'idle'):
            return _loading_figure(
                f"Loading grid pace data for {params['year']} {params['race']} {params['session_type']}..."
            )
        if status.get('status') == 'error':
            return _error_figure(_friendly_error(status.get('error') or 'Session data failed to load.'))
        with _timed_callback('update_grid_pace', year=params['year'], race=params['race'], session=params['session_type']):
            try:
                # Use weather to detect wet conditions for pace filtering.
                session = load_session_with_preload(
                    params['year'],
                    params['race'],
                    params['session_type'],
                    laps=True,
                    telemetry=False,
                    weather=True,
                    messages=False
                )
                return _build_grid_pace_fig(session, params['session_type'])
            except Exception as e:
                logging.error(f"Grid Pace Error: {e}")
                return _error_figure(_friendly_error(e))
