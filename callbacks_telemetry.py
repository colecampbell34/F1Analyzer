"""Telemetry tab callbacks: speed graph, mini track map, GG diagram, and playback."""
import dash
import logging
from dash import ClientsideFunction
from dash.dependencies import Input, Output, State
from dash.exceptions import PreventUpdate

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from data import get_shared_data, get_best_lap
from graphs import _sort_fastest_driver, _build_telemetry_fig, _error_figure
from callbacks_shared import _timed_callback, _has_valid_lap, _pick_driver_lap
from ui_utils import _friendly_error


def register_telemetry_callbacks(app):
    """Register all telemetry-related callbacks."""

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
        with _timed_callback('update_telemetry', year=params['year'], race=params['race'], session=params['session_type']):
            try:
                session, d1, d2, lbl1, lbl2, c1, c2 = get_shared_data(params, laps=True, telemetry=True)
                lap1 = _pick_driver_lap(session, d1, d1_mode, d1_lap_num, get_best_lap)
                lap2 = _pick_driver_lap(session, d2, d2_mode, d2_lap_num, get_best_lap)

                if not _has_valid_lap(lap1, pd):
                    raise ValueError(f"{d1} did not set a valid lap.")
                if not _has_valid_lap(lap2, pd):
                    raise ValueError(f"{d2} did not set a valid lap.")

                tel1 = lap1.get_telemetry().add_distance()
                tel2 = lap2.get_telemetry().add_distance()
                if not tel1.empty: tel1['Distance'] -= tel1['Distance'].min()
                if not tel2.empty: tel2['Distance'] -= tel2['Distance'].min()

                fast_data, slow_data = _sort_fastest_driver(d1, tel1, c1, lap1, d2, tel2, c2, lap2, lbl1, lbl2)
                return _build_telemetry_fig(fast_data, slow_data)
            except Exception as e:
                logging.error(f"Telemetry Error: {e}")
                return _error_figure(_friendly_error(e))

    @app.callback(
        [Output('mini-track-map', 'figure'), Output('mini-map-store', 'data')],
        [Input('dashboard-params-store', 'data'), Input('main-tabs', 'value'),
         Input('update-laps-btn', 'n_clicks')],
        [State('d1-lap-mode', 'value'), State('d2-lap-mode', 'value'),
         State('d1-lap-number', 'value'), State('d2-lap-number', 'value')],
        prevent_initial_call=True
    )
    def update_mini_map_base(params, active_tab, n_laps, d1_mode, d2_mode, d1_lap_num, d2_lap_num):
        """Precompute track polyline once; hover only moves marker."""
        if not params or active_tab != 'tab-telemetry':
            return dash.no_update, dash.no_update
        try:
            session, d1, d2, lbl1, lbl2, c1, c2 = get_shared_data(params, laps=True, telemetry=True)
            lap1 = _pick_driver_lap(session, d1, d1_mode, d1_lap_num, get_best_lap)
            lap2 = _pick_driver_lap(session, d2, d2_mode, d2_lap_num, get_best_lap)

            if lap1 is None or pd.isna(lap1.get('LapTime')) or lap2 is None or pd.isna(lap2.get('LapTime')):
                raise PreventUpdate

            tel1 = lap1.get_telemetry().add_distance().dropna(subset=['X', 'Y', 'Distance', 'Time'])
            tel2 = lap2.get_telemetry().add_distance().dropna(subset=['X', 'Y', 'Distance', 'Time'])
            if tel1.empty or tel2.empty:
                raise PreventUpdate

            max_pts = 1800

            def _sample_for_playback(tel):
                n = len(tel)
                step = max(1, n // max_pts)
                return {
                    'x': tel['X'].to_numpy(dtype=float)[::step].tolist(),
                    'y': tel['Y'].to_numpy(dtype=float)[::step].tolist(),
                    'dist': tel['Distance'].to_numpy(dtype=float)[::step].tolist(),
                    't': tel['Time'].dt.total_seconds().to_numpy(dtype=float)[::step].tolist()
                }

            d1_data = _sample_for_playback(tel1)
            d2_data = _sample_for_playback(tel2)
            track_x = tel1['X'].to_numpy(dtype=float)[::max(1, len(tel1) // 1400)]
            track_y = tel1['Y'].to_numpy(dtype=float)[::max(1, len(tel1) // 1400)]

            store = {
                'track': {'x': track_x.tolist(), 'y': track_y.tolist()},
                'd1': {**d1_data, 'name': d1, 'color': c1, 'lap_s': float(lap1['LapTime'].total_seconds())},
                'd2': {**d2_data, 'name': d2, 'color': c2, 'lap_s': float(lap2['LapTime'].total_seconds())},
                # Keep top-level arrays for existing hover marker behavior.
                'x': d1_data['x'],
                'y': d1_data['y'],
                'dist': d1_data['dist']
            }

            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=track_x, y=track_y,
                mode='lines',
                line=dict(color='#444', width=2),
                hoverinfo='skip',
                showlegend=False
            ))
            fig.add_trace(go.Scatter(
                x=[d1_data['x'][0]], y=[d1_data['y'][0]],
                mode='markers',
                marker=dict(color=c1, size=11, symbol='circle', line=dict(color='white', width=1.5)),
                name=d1,
                showlegend=False,
                hovertemplate=f"<b>{d1}</b><br>t=0.00s<extra></extra>",
                meta='driver-marker'
            ))
            fig.add_trace(go.Scatter(
                x=[d2_data['x'][0]], y=[d2_data['y'][0]],
                mode='markers',
                marker=dict(color=c2, size=11, symbol='circle', line=dict(color='white', width=1.5)),
                name=d2,
                showlegend=False,
                hovertemplate=f"<b>{d2}</b><br>t=0.00s<extra></extra>",
                meta='driver-marker'
            ))

            fig.update_layout(
                template='plotly_dark',
                margin=dict(l=0, r=0, t=0, b=0),
                xaxis=dict(visible=False, scaleanchor="y", scaleratio=1),
                yaxis=dict(visible=False),
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                uirevision='mini-track-map'
            )
            return fig, store
        except PreventUpdate:
            raise
        except Exception:
            return dash.no_update, dash.no_update

    app.clientside_callback(
        ClientsideFunction(namespace='clientside', function_name='updateMiniMap'),
        Output('mini-track-map', 'figure', allow_duplicate=True),
        Input('speed-graph', 'hoverData'),
        [State('mini-map-store', 'data'), State('mini-track-map', 'figure'),
         State('lap-playback-interval', 'disabled')],
        prevent_initial_call=True
    )

    app.clientside_callback(
        ClientsideFunction(namespace='clientside', function_name='animateMiniMapPlayback'),
        [Output('mini-track-map', 'figure', allow_duplicate=True),
         Output('lap-playback-interval', 'disabled'),
         Output('lap-playback-interval', 'n_intervals'),
         Output('pause-resume-lap-btn', 'children'),
         Output('lap-playback-time-label', 'children'),
         Output('lap-playback-store', 'data')],
        [Input('play-lap-btn', 'n_clicks'),
         Input('pause-resume-lap-btn', 'n_clicks'),
         Input('lap-playback-interval', 'n_intervals')],
        [State('mini-map-store', 'data'),
         State('mini-track-map', 'figure'),
         State('lap-playback-interval', 'disabled'),
         State('lap-playback-store', 'data')],
        prevent_initial_call=True
    )

    @app.callback(
        [Output('gg-diagram', 'figure', allow_duplicate=True), Output('gg-data-store', 'data')],
        [Input('dashboard-params-store', 'data'), Input('main-tabs', 'value'),
         Input('update-laps-btn', 'n_clicks')],
        [State('d1-lap-mode', 'value'), State('d2-lap-mode', 'value'),
         State('d1-lap-number', 'value'), State('d2-lap-number', 'value')],
        prevent_initial_call=True,
    )
    def update_gg_base(params, active_tab, n_laps, d1_mode, d2_mode, d1_lap_num, d2_lap_num):
        """Build base friction-circle figure and cache G-series for hover."""
        if not params or active_tab != 'tab-telemetry':
            return dash.no_update, dash.no_update

        def calculate_g_series(tel):
            # Return (t, dist, lat_g, long_g) arrays.
            t = tel['Time'].dt.total_seconds()
            dt = t.diff().fillna(0.1).to_numpy(dtype=float)
            dt = np.where(dt <= 1e-3, 1e-3, dt)

            v_ms = (tel['Speed'].to_numpy(dtype=float) / 3.6)
            accel_ms2 = np.diff(v_ms, prepend=v_ms[0]) / dt
            long_g = np.clip(accel_ms2 * 0.1019, -6.0, 6.0)

            x = tel['X'].to_numpy(dtype=float)
            y = tel['Y'].to_numpy(dtype=float)
            dx = np.diff(x, prepend=x[0])
            dy = np.diff(y, prepend=y[0])
            heading = np.arctan2(dy, dx)
            d_heading = np.diff(heading, prepend=heading[0])
            d_heading = (d_heading + np.pi) % (2 * np.pi) - np.pi
            lat_g = np.clip((v_ms * (d_heading / dt)) * 0.1019, -6.0, 6.0)

            dist = tel['Distance'].to_numpy(dtype=float)
            t_sec = t.to_numpy(dtype=float)
            return t_sec, dist, lat_g, long_g

        with _timed_callback('update_gg_base', year=params['year'], race=params['race'], session=params['session_type']):
            session, d1, d2, lbl1, lbl2, c1, c2 = get_shared_data(params, laps=True, telemetry=True)

            lap1 = _pick_driver_lap(session, d1, d1_mode, d1_lap_num, get_best_lap)
            lap2 = _pick_driver_lap(session, d2, d2_mode, d2_lap_num, get_best_lap)
            if not _has_valid_lap(lap1, pd):
                raise PreventUpdate
            if not _has_valid_lap(lap2, pd):
                raise PreventUpdate

            tel1 = lap1.get_telemetry().add_distance()
            tel2 = lap2.get_telemetry().add_distance()
            if not tel1.empty:
                tel1['Distance'] -= tel1['Distance'].min()
            if not tel2.empty:
                tel2['Distance'] -= tel2['Distance'].min()

            t1, dist1, lat1, long1 = calculate_g_series(tel1)
            t2, dist2, lat2, long2 = calculate_g_series(tel2)

            # Downsample payload before writing to browser store.
            def ds(t_sec, dist, lat, lng, max_pts=3600):
                n = len(dist)
                if n <= max_pts:
                    return t_sec.tolist(), dist.tolist(), lat.tolist(), lng.tolist()
                step = max(1, n // max_pts)
                return (
                    t_sec[::step].tolist(),
                    dist[::step].tolist(),
                    lat[::step].tolist(),
                    lng[::step].tolist()
                )

            d1_t, d1_dist, d1_lat, d1_long = ds(t1, dist1, lat1, long1)
            d2_t, d2_dist, d2_lat, d2_long = ds(t2, dist2, lat2, long2)
            store = {
                'd1': {'driver': d1, 'color': c1, 't': d1_t, 'dist': d1_dist, 'lat': d1_lat, 'long': d1_long},
                'd2': {'driver': d2, 'color': c2, 't': d2_t, 'dist': d2_dist, 'lat': d2_lat, 'long': d2_long},
            }

            fig = go.Figure()
            # Reference rings.
            for r0 in [1, 2, 3, 4, 5]:
                th = np.linspace(0, 2 * np.pi, 160)
                fig.add_trace(go.Scatter(
                    x=r0 * np.cos(th), y=r0 * np.sin(th),
                    mode='lines',
                    line=dict(color='#2a2a2a', dash='dot', width=1),
                    showlegend=False,
                    hoverinfo='skip'
                ))

            fig.update_layout(
                xaxis=dict(title="Lateral G", range=[-6, 6], gridcolor='#222', zerolinecolor='#444'),
                yaxis=dict(title="Longitudinal G", range=[-6, 6], gridcolor='#222', zerolinecolor='#444', scaleanchor="x", scaleratio=1),
                margin=dict(l=40, r=20, t=55, b=40),
                showlegend=False,
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                template='plotly_dark',
                uirevision='gg-friction'
            )
            return fig, store

    app.clientside_callback(
        ClientsideFunction(namespace='clientside', function_name='updateGGHover'),
        Output('gg-diagram', 'figure', allow_duplicate=True),
        Input('speed-graph', 'hoverData'),
        [State('gg-data-store', 'data'), State('gg-diagram', 'figure'),
         State('lap-playback-interval', 'disabled')],
        prevent_initial_call=True
    )

    app.clientside_callback(
        ClientsideFunction(namespace='clientside', function_name='updateGGFromPlayback'),
        Output('gg-diagram', 'figure', allow_duplicate=True),
        Input('lap-playback-store', 'data'),
        [State('gg-data-store', 'data'), State('gg-diagram', 'figure')],
        prevent_initial_call=True
    )

    app.clientside_callback(
        ClientsideFunction(namespace='clientside', function_name='updateTelemetryPlaybackCursor'),
        Output('speed-graph', 'figure', allow_duplicate=True),
        Input('lap-playback-store', 'data'),
        [State('mini-map-store', 'data'), State('speed-graph', 'figure')],
        prevent_initial_call=True
    )
