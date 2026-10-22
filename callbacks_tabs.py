"""Visualization tab callbacks: Track Map, Strategy, and Race & Pace."""
import dash
import logging
from dash import dcc, html
from dash.dependencies import Input, Output, State

from callbacks_shared import _active_tab_ready, _figure_cache_key, _lap_dropdown_to_mode, _timed_callback


def _render_stint_overview(stints_by_driver):
    """Render a compact, proportional stint strip above the strategy charts."""
    from graph_shared import COMPOUND_COLORS

    rows = []
    for driver, stints in stints_by_driver:
        if not stints:
            continue
        drawable = [stint for stint in stints if stint.get('start_lap') is not None and stint.get('end_lap') is not None]
        if not drawable:
            continue
        total_laps = max(stint['end_lap'] for stint in drawable)
        bars = []
        for index, stint in enumerate(drawable):
            if index:
                bars.append(html.Span(
                    title=f"Pit stop before lap {stint['start_lap']}",
                    className='stint-pit-marker',
                    **{'aria-label': f"Pit stop before lap {stint['start_lap']}"},
                ))
            lap_count = max(1, stint['end_lap'] - stint['start_lap'] + 1)
            compound = stint['compound']
            start_lap = int(stint['start_lap']) if float(stint['start_lap']).is_integer() else stint['start_lap']
            end_lap = int(stint['end_lap']) if float(stint['end_lap']).is_integer() else stint['end_lap']
            label = f"{compound} {start_lap}–{end_lap}"
            bars.append(html.Span(
                label,
                title=(label if compound != 'UNAVAILABLE' else f"{label} · compound unavailable from source"),
                className='stint-bar-segment',
                style={
                    'flex': f'{lap_count:g} 1 0',
                    'backgroundColor': COMPOUND_COLORS.get(compound, '#737980'),
                    'color': '#101216' if compound in {'MEDIUM', 'HARD', 'INTERMEDIATE'} else '#f7f7f3',
                },
            ))
        rows.append(html.Div([
            html.Strong(driver, className='stint-driver-code'),
            html.Div(bars, className='stint-bar', title=f'{driver}: {int(total_laps) if float(total_laps).is_integer() else total_laps} laps'),
        ], className='stint-overview-row'))

    if not rows:
        return html.Div('No tyre-stint data is available for the selected drivers.', className='stint-overview-empty')
    return html.Div([
        html.Div('Stint plan', className='stint-overview-kicker'),
        html.Div(rows, className='stint-overview-rows'),
    ], className='stint-overview-panel')


def _render_race_context(session, driver1, driver2, color1, color2):
    """Return one compact grid-to-finish reference for the Race & Pace tab."""
    cards = []
    results = getattr(session, 'results', None)
    colors = {driver1: color1, driver2: color2}
    for driver in (driver1, driver2):
        row = None
        try:
            match = results[results['abbreviation'] == driver]
            row = match.iloc[0] if not match.empty else None
        except Exception:
            pass
        if row is None:
            continue
        grid = row.get('grid_position')
        finish = row.get('position')
        try:
            grid_label = f'G{int(grid)}' if int(grid) > 0 else 'Pit lane'
        except (TypeError, ValueError):
            grid_label = 'Grid —'
        try:
            finish_label = f'P{int(finish)}'
        except (TypeError, ValueError):
            finish_label = 'Finish —'
        cards.append(html.Div([
            html.Strong(driver, style={'color': colors.get(driver, '#f7f7f3')}),
            html.Span(f'{grid_label} → {finish_label}')
        ], className='race-context-card'))
    return html.Div([
        html.Div('Race context', className='race-summary-kicker'),
        html.Div(cards or [html.Span('Classification context unavailable.')], className='race-context-cards'),
    ], className='race-context-panel')


def _compound_chip(compound):
    from graph_shared import COMPOUND_COLORS

    return html.Span(
        compound.title(),
        className='compound-chip',
        style={
            'backgroundColor': COMPOUND_COLORS.get(compound, '#737980'),
            'color': '#101216' if compound in {'MEDIUM', 'HARD', 'INTERMEDIATE'} else '#f7f7f3',
        },
    )


def _render_strategy_impact(impacts_by_driver):
    """Present tyre-service decisions, not a low-signal pit-stop time chart."""
    lines = []
    for driver, color, impacts in impacts_by_driver:
        driver_label = html.Strong(driver, style={'color': color})
        if not impacts:
            lines.append(html.Div([
                driver_label, html.Span(' No tyre-service change recorded.')
            ], className='race-impact-line'))
            continue
        for event in impacts:
            position = []
            if event['position_before'] is not None and event['position_after'] is not None:
                position = [html.Span(
                    f" · P{event['position_before']} → P{event['position_after']}"
                )]
            if event['from_compound'] == event['to_compound']:
                service = [
                    html.Span(f" L{event['pit_lap']} pit stop · stayed on "),
                    _compound_chip(event['to_compound']),
                ]
            else:
                service = [
                    html.Span(f" L{event['pit_lap']} "),
                    _compound_chip(event['from_compound']),
                    html.Span(' → '),
                    _compound_chip(event['to_compound']),
                ]
            lines.append(html.Div([
                driver_label, *service, *position,
            ], className='race-impact-line'))
    return html.Div([
        html.Div('Strategy calls', className='race-summary-kicker'),
        html.Div(lines or [html.Span('No pit strategy data is available.')], className='race-impact-lines'),
    ], className='race-impact-panel')


def register_tab_callbacks(app):
    """Register callbacks for Track Map, Strategy, and Race & Pace tabs."""

    @app.callback(
        Output('trackmap-lap-summary', 'children'),
        [Input('dashboard-params-store', 'data'),
         Input('trackmap-d1-lap-dropdown', 'value'),
         Input('trackmap-d2-lap-dropdown', 'value')]
    )
    def update_trackmap_lap_summary(params, d1_lap_value, d2_lap_value):
        def _label(value):
            if value in (None, '', 'fastest'):
                return 'fastest'
            return f"Lap {int(value)}"

        if not params:
            return "Laps: fastest vs fastest"
        return (
            f"Laps: {params.get('driver1')} {_label(d1_lap_value)} "
            f"vs {params.get('driver2')} {_label(d2_lap_value)}"
        )

    # Track map tab.
    @app.callback(
        [Output('2d-dominance-graph', 'figure'), Output('driver-dna-container', 'children'),
         Output('trackmap-cache-key-store', 'data')],
        [Input('dashboard-params-store', 'data'), Input('main-tabs', 'value'),
         Input('trackmap-d1-lap-dropdown', 'value'), Input('trackmap-d2-lap-dropdown', 'value'),
         Input('trackmap-mode', 'value'), Input('preload-status-interval', 'n_intervals'),
         Input('active-tab-preload-store', 'data')],
        State('trackmap-cache-key-store', 'data')
    )
    def update_dominance(params, active_tab, d1_lap_value, d2_lap_value, mode, _n, _preload_state, current_cache_key):
        if not _active_tab_ready(params, active_tab, 'tab-trackmap'):
            return dash.no_update, dash.no_update, dash.no_update
        cache_key = _figure_cache_key(params, 'trackmap', mode, d1_lap_value, d2_lap_value)
        if current_cache_key == cache_key:
            return dash.no_update, dash.no_update, dash.no_update
        with _timed_callback('update_dominance', year=params['year'], race=params['race'], session=params['session_type']):
            try:
                from graphs import _build_dominance_fig, _build_driver_radar
                from graph_shared import _sort_fastest_driver
                from telemetry_prep import prepare_selected_lap_comparison

                d1_mode, d1_lap_num = _lap_dropdown_to_mode(d1_lap_value)
                d2_mode, d2_lap_num = _lap_dropdown_to_mode(d2_lap_value)
                cmp = prepare_selected_lap_comparison(
                    params, d1_mode, d2_mode, d1_lap_num, d2_lap_num,
                    require_position=True,
                )
                from data import load_session_with_preload

                # The track-map preload already includes optional circuit
                # metadata; reuse that profile so official turn markers are
                # available to the figure builder.
                session = load_session_with_preload(
                    params['year'], params['race'], params['session_type'],
                    laps=True, telemetry=True, circuit=True,
                )
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
                            "Driver DNA",
                            title=(
                                "Driver DNA summarizes relative driving traits from the selected laps. "
                                "It is normalized between the two drivers, so use it as a shape comparison rather than an absolute rating."
                            ),
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

                fig = _build_dominance_fig(
                    d1, d2, c1, c2, tel1, tel2, fast_data, slow_data,
                    mode=mode,
                    session=session,
                    circuit_corners=session.circuit_corners.to_dict('records'),
                )
                return fig, dna_ui, cache_key
            except Exception as e:
                from graph_shared import _error_figure
                from ui_utils import _friendly_error

                logging.error(f"Dominance Error: {e}")
                return _error_figure(_friendly_error(e)), html.Div("DNA analysis unavailable"), None

    # Strategy tab.
    @app.callback(
        [Output('strategy-stint-overview', 'children'),
         Output('strategy-graph', 'figure'), Output('deg-graph', 'figure'),
         Output('strategy-cache-key-store', 'data')],
        [Input('dashboard-params-store', 'data'), Input('main-tabs', 'value'),
         Input('preload-status-interval', 'n_intervals'), Input('active-tab-preload-store', 'data')],
        State('strategy-cache-key-store', 'data')
    )
    def update_strategy(params, active_tab, _n, _preload_state, current_cache_key):
        if not _active_tab_ready(params, active_tab, 'tab-strategy'):
            return dash.no_update, dash.no_update, dash.no_update, dash.no_update
        cache_key = _figure_cache_key(params, 'strategy')
        if current_cache_key == cache_key:
            return dash.no_update, dash.no_update, dash.no_update, dash.no_update
        with _timed_callback('update_strategy', year=params['year'], race=params['race'], session=params['session_type']):
            try:
                from data import get_shared_data, is_qualifying, is_practice
                from graphs import _build_strategy_fig, _build_deg_fig
                from graph_shared import _not_applicable_figure

                # Strategy view needs laps + weather; no telemetry.
                session, d1, d2, lbl1, lbl2, c1, c2 = get_shared_data(
                    params, laps=True, telemetry=False, weather=True, strategy=True, race_context=True,
                )
                session_type = params['session_type']

                if is_qualifying(session_type):
                    fig_strat = _not_applicable_figure("Strategy timeline is not applicable for Qualifying sessions")
                    fig_deg = _not_applicable_figure("Tyre degradation is not applicable for Qualifying sessions")
                    stint_overview = html.Div('Stint plan is available for Race and Sprint sessions.', className='stint-overview-empty')
                elif is_practice(session_type):
                    fig_strat = _not_applicable_figure(
                        "Strategy view available for Race & Sprint sessions.\n"
                        "For practice, check Race & Pace for field context.")
                    fig_deg = _not_applicable_figure("Tyre degradation not applicable for practice sessions")
                    stint_overview = html.Div('Stint plan is available for Race and Sprint sessions.', className='stint-overview-empty')
                else:
                    from strategy_insights import build_driver_stints
                    fig_strat = _build_strategy_fig(session, d1, d2, lbl1, lbl2, c1, c2)
                    fig_deg = _build_deg_fig(session, d1, d2, lbl1, lbl2, c1, c2)
                    stint_overview = _render_stint_overview([
                        (d1, build_driver_stints(session, d1)),
                        (d2, build_driver_stints(session, d2)),
                    ])

                return stint_overview, fig_strat, fig_deg, cache_key
            except Exception as e:
                from graph_shared import _error_figure
                from ui_utils import _friendly_error

                logging.error(f"Strategy Error: {e}")
                err = _error_figure(_friendly_error(e))
                return html.Div('Stint overview unavailable.', className='stint-overview-empty'), err, err, None

    # Race & Pace intentionally combines selected-driver race context with the
    # field-wide pace distribution. Pit-stop timestamps alone rarely explain
    # anything, so the compact strategy-call summary replaces that large chart.
    @app.callback(
        [Output('race-session-summary', 'children'), Output('race-strategy-impact', 'children'),
         Output('race-gaps-graph', 'figure'), Output('grid-pace-graph', 'figure'),
         Output('race-cache-key-store', 'data')],
        [Input('dashboard-params-store', 'data'), Input('main-tabs', 'value'),
         Input('preload-status-interval', 'n_intervals'), Input('active-tab-preload-store', 'data')],
        State('race-cache-key-store', 'data')
    )
    def update_race_pace(params, active_tab, _n, _preload_state, current_cache_key):
        if not _active_tab_ready(params, active_tab, 'tab-racepace'):
            return (dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update)
        cache_key = _figure_cache_key(params, 'racepace')
        if current_cache_key == cache_key:
            return (dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update)
        with _timed_callback('update_race_pace', year=params['year'], race=params['race'], session=params['session_type']):
            try:
                from data import get_shared_data, is_race
                from graphs import _build_grid_pace_fig, _build_race_gaps_fig
                from graph_shared import _not_applicable_figure
                from strategy_insights import build_driver_pit_impacts

                session, d1, d2, lbl1, lbl2, c1, c2 = get_shared_data(
                    params, laps=True, telemetry=False, weather=True, strategy=True, race_context=True,
                )
                pace_fig = _build_grid_pace_fig(session, params['session_type'])
                if is_race(params['session_type']):
                    gap_fig = _build_race_gaps_fig(session, d1, d2, lbl1, lbl2, c1, c2)
                    impacts = _render_strategy_impact([
                        (d1, c1, build_driver_pit_impacts(session, d1)),
                        (d2, c2, build_driver_pit_impacts(session, d2)),
                    ])
                else:
                    gap_fig = _not_applicable_figure(
                        'Race gap analysis is available for Race and Sprint sessions only.'
                    )
                    impacts = html.Div([
                        html.Div('Strategy calls', className='race-summary-kicker'),
                        html.Span('Pit strategy is available for Race and Sprint sessions.'),
                    ], className='race-impact-panel')
                return _render_race_context(session, d1, d2, c1, c2), impacts, gap_fig, pace_fig, cache_key
            except Exception as e:
                from graph_shared import _error_figure
                from ui_utils import _friendly_error

                logging.error(f"Race & Pace Error: {e}")
                err = _error_figure(_friendly_error(e))
                unavailable = html.Div('Race context unavailable.', className='race-impact-panel')
                return unavailable, unavailable, err, err, None
