"""Telemetry tab callbacks: speed graph, mini track map, GG diagram, and playback."""
import dash
import logging
from dash import ClientsideFunction
from dash.dependencies import Input, Output, State
from dash.exceptions import PreventUpdate
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from graphs import _build_telemetry_fig
from graph_shared import _sort_fastest_driver, _error_figure, _compute_lap_delta
from callbacks_shared import _timed_callback
from ui_utils import _friendly_error
from telemetry_prep import prepare_selected_lap_comparison


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
                cmp = prepare_selected_lap_comparison(params, d1_mode, d2_mode, d1_lap_num, d2_lap_num)
                d1, d2 = cmp['d1'], cmp['d2']
                lbl1, lbl2, c1, c2 = cmp['lbl1'], cmp['lbl2'], cmp['c1'], cmp['c2']
                lap1, lap2 = cmp['lap1'], cmp['lap2']
                tel1, tel2 = cmp['tel1'], cmp['tel2']

                fast_data, slow_data = _sort_fastest_driver(d1, tel1, c1, lap1, d2, tel2, c2, lap2, lbl1, lbl2)
                return _build_telemetry_fig(
                    fast_data,
                    slow_data,
                    driver1_delta_data=(d1, lap1),
                    driver2_delta_data=(d2, lap2),
                )
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
            cmp = prepare_selected_lap_comparison(
                params, d1_mode, d2_mode, d1_lap_num, d2_lap_num, drop_xy_time=True
            )
            d1, d2 = cmp['d1'], cmp['d2']
            c1, c2 = cmp['c1'], cmp['c2']
            lap1, lap2 = cmp['lap1'], cmp['lap2']
            tel1, tel2 = cmp['tel1'], cmp['tel2']
            
            lap1_dist_max = 0
            lap2_dist_max = 0
            
            if not tel1.empty:
                tel1['Distance'] -= tel1['Distance'].min()
                lap1_dist_max = tel1['Distance'].max()
                if lap1_dist_max > 0: tel1['Distance'] /= lap1_dist_max
                
                tel1['Time'] -= tel1['Time'].min()
                t_raw_max = tel1['Time'].max().total_seconds()
                lap_time1 = float(lap1['LapTime'].total_seconds())
                if t_raw_max > 0:
                    tel1['Time'] = (tel1['Time'].dt.total_seconds() / t_raw_max) * lap_time1
                else:
                    tel1['Time'] = tel1['Time'].dt.total_seconds()
                
            if not tel2.empty:
                tel2['Distance'] -= tel2['Distance'].min()
                lap2_dist_max = tel2['Distance'].max()
                if lap2_dist_max > 0: tel2['Distance'] /= lap2_dist_max
                
                tel2['Time'] -= tel2['Time'].min()
                t_raw_max = tel2['Time'].max().total_seconds()
                lap_time2 = float(lap2['LapTime'].total_seconds())
                if t_raw_max > 0:
                    tel2['Time'] = (tel2['Time'].dt.total_seconds() / t_raw_max) * lap_time2
                else:
                    tel2['Time'] = tel2['Time'].dt.total_seconds()

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
                    't': tel['Time'].to_numpy(dtype=float)[::step].tolist(),
                    'speed': tel['Speed'].to_numpy(dtype=float)[::step].tolist(),
                    'gear': tel['nGear'].to_numpy(dtype=int)[::step].tolist(),
                    'rpm': tel['RPM'].to_numpy(dtype=int)[::step].tolist()
                }

            d1_data = _sample_for_playback(tel1)
            d2_data = _sample_for_playback(tel2)
            track_x = tel1['X'].to_numpy(dtype=float)[::max(1, len(tel1) // 1400)]
            track_y = tel1['Y'].to_numpy(dtype=float)[::max(1, len(tel1) // 1400)]
            # Positive delta means Driver 1 is ahead of Driver 2 at that point.
            delta_time, ref_tel, _ = _compute_lap_delta(lap2, lap1)
            delta_dist = ref_tel['Distance'].to_numpy(dtype=float)
            delta_vals = -pd.Series(delta_time).astype(float).to_numpy()
            valid_delta = np.isfinite(delta_dist) & np.isfinite(delta_vals)

            store = {
                'track': {'x': track_x.tolist(), 'y': track_y.tolist()},
                'd1': {**d1_data, 'name': d1, 'color': c1, 'lap_s': float(lap1['LapTime'].total_seconds()), 'dist_max': float(lap1_dist_max)},
                'd2': {**d2_data, 'name': d2, 'color': c2, 'lap_s': float(lap2['LapTime'].total_seconds()), 'dist_max': float(lap2_dist_max)},
                'delta': {
                    'dist': delta_dist[valid_delta].tolist(),
                    'value': delta_vals[valid_delta].tolist(),
                    'primary': d1,
                    'secondary': d2,
                    'reference': 'd2',
                },
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
        ClientsideFunction(namespace='clientside', function_name='handlePlaybackAnimation'),
        [Output('mini-track-map', 'figure', allow_duplicate=True),
         Output('gg-diagram', 'figure', allow_duplicate=True),
         Output('speed-graph', 'figure', allow_duplicate=True),
         Output('lap-playback-interval', 'disabled'),
         Output('lap-playback-interval', 'n_intervals'),
         Output('pause-resume-lap-btn', 'children'),
         Output('lap-playback-time-label', 'children'),
         Output('lap-playback-store', 'data')],
        [Input('play-lap-btn', 'n_clicks'),
         Input('pause-resume-lap-btn', 'n_clicks'),
         Input('lap-playback-interval', 'n_intervals')],
        [State('mini-map-store', 'data'),
         State('gg-data-store', 'data'),
         State('mini-track-map', 'figure'),
         State('gg-diagram', 'figure'),
         State('speed-graph', 'figure'),
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
            t_sec = t.to_numpy(dtype=float)
            if len(t_sec) < 5:
                return t_sec, tel['Distance'].to_numpy(dtype=float), np.zeros(len(t_sec)), np.zeros(len(t_sec))
            for idx in range(1, len(t_sec)):
                if not np.isfinite(t_sec[idx]) or t_sec[idx] <= t_sec[idx - 1]:
                    t_sec[idx] = t_sec[idx - 1] + 1e-3

            def smooth(values, window=11):
                series = (
                    pd.Series(values)
                    .replace([np.inf, -np.inf], np.nan)
                    .interpolate(limit_direction='both')
                    .ffill()
                    .bfill()
                )
                if series.isna().all():
                    return np.zeros(len(series), dtype=float)
                return (
                    series
                    .rolling(window=window, center=True, min_periods=1)
                    .median()
                    .rolling(window=window, center=True, min_periods=1)
                    .mean()
                    .to_numpy(dtype=float)
                )

            v_ms = smooth(tel['Speed'].to_numpy(dtype=float) / 3.6, window=9)
            x = smooth(tel['X'].to_numpy(dtype=float), window=7)
            y = smooth(tel['Y'].to_numpy(dtype=float), window=7)

            accel_ms2 = np.gradient(v_ms, t_sec, edge_order=1)
            long_g = smooth(accel_ms2 * 0.1019, window=13)

            dx = np.gradient(x, t_sec, edge_order=1)
            dy = np.gradient(y, t_sec, edge_order=1)
            heading = np.unwrap(np.arctan2(dy, dx))
            yaw_rate = np.gradient(heading, t_sec, edge_order=1)
            lat_g = smooth((v_ms * yaw_rate) * 0.1019, window=13)

            # Ignore occasional telemetry timestamp/position spikes that otherwise make
            # the marker jump around the friction circle.
            lat_g = np.clip(lat_g, -5.5, 5.5)
            long_g = np.clip(long_g, -5.5, 5.5)

            dist = tel['Distance'].to_numpy(dtype=float)
            return t_sec, dist, lat_g, long_g

        with _timed_callback('update_gg_base', year=params['year'], race=params['race'], session=params['session_type']):
            cmp = prepare_selected_lap_comparison(params, d1_mode, d2_mode, d1_lap_num, d2_lap_num)
            d1, d2 = cmp['d1'], cmp['d2']
            c1, c2 = cmp['c1'], cmp['c2']
            tel1, tel2 = cmp['tel1'], cmp['tel2']

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
                    line=dict(color='#3a3a3a', dash='dot', width=1),
                    showlegend=False,
                    hoverinfo='skip'
                ))
            fig.add_trace(go.Scatter(
                x=[-5.5, 5.5], y=[0, 0],
                mode='lines',
                line=dict(color='#555', width=1),
                showlegend=False,
                hoverinfo='skip'
            ))
            fig.add_trace(go.Scatter(
                x=[0, 0], y=[-5.5, 5.5],
                mode='lines',
                line=dict(color='#555', width=1),
                showlegend=False,
                hoverinfo='skip'
            ))

            fig.update_layout(
                xaxis=dict(title="Lateral G", range=[-5.5, 5.5], gridcolor='#2c2c2c', zeroline=False),
                yaxis=dict(title="Longitudinal G", range=[-5.5, 5.5], gridcolor='#2c2c2c', zeroline=False, scaleanchor="x", scaleratio=1),
                margin=dict(l=36, r=14, t=18, b=34),
                showlegend=False,
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                template='plotly_dark',
                annotations=[
                    dict(text="ACCEL", x=0.5, y=0.99, xref="paper", yref="paper", showarrow=False, font=dict(size=10, color="#777")),
                    dict(text="BRAKE", x=0.5, y=0.01, xref="paper", yref="paper", showarrow=False, font=dict(size=10, color="#777")),
                    dict(text="LEFT", x=0.02, y=0.5, xref="paper", yref="paper", showarrow=False, textangle=-90, font=dict(size=10, color="#777")),
                    dict(text="RIGHT", x=0.98, y=0.5, xref="paper", yref="paper", showarrow=False, textangle=90, font=dict(size=10, color="#777")),
                ]
            )

            # Add placeholder traces for 2 drivers (Beam, Trail, Ball each)
            for i in range(2):
                color = c1 if i == 0 else c2
                name = d1 if i == 0 else d2
                # Beam
                fig.add_trace(go.Scatter(
                    x=[0, 0], y=[0, 0], mode='lines',
                    line=dict(color=color, width=1.5, dash='dot'),
                    opacity=0.5, showlegend=False, meta='hover', hoverinfo='skip'
                ))
                # Trail
                fig.add_trace(go.Scatter(
                    x=[], y=[], mode='lines',
                    line=dict(color=color, width=3, shape='spline', smoothing=1.2),
                    opacity=0.45, showlegend=False, meta='hover', hoverinfo='skip'
                ))
                # Ball
                fig.add_trace(go.Scatter(
                    x=[None], y=[None], mode='markers',
                    marker=dict(color=color, size=11, line=dict(color='white', width=1.5), symbol='diamond'),
                    name=name, showlegend=False, meta='hover',
                    hovertemplate=f"<b>{name}</b><br>Lat: %{{x:.2f}}G<br>Long: %{{y:.2f}}G<extra></extra>"
                ))

            return fig, store

    app.clientside_callback(
        ClientsideFunction(namespace='clientside', function_name='updateGGHover'),
        Output('gg-diagram', 'figure', allow_duplicate=True),
        Input('speed-graph', 'hoverData'),
        [State('gg-data-store', 'data'), State('gg-diagram', 'figure'),
         State('lap-playback-interval', 'disabled')],
        prevent_initial_call=True
    )
