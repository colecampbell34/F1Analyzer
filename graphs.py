import numpy as np
import pandas as pd
import plotly.graph_objects as go
from data import get_pit_stop_data, get_track_status_events, get_single_driver_color, is_practice
from ui_utils import _downsample, _apply_base_layout, _hex_to_rgba
from graph_shared import (
    COMPOUND_COLORS,
    _collapse_lap_ranges,
    _compute_lap_delta,
)


def _add_driver_legend_entries(fig, drivers, row=None, col=None):
    """Add simple color-to-driver legend entries without tying them to metric traces."""
    for driver, color in drivers:
        trace = go.Scatter(
            x=[None],
            y=[None],
            mode='lines',
            name=str(driver),
            line=dict(color=color, width=3),
            hoverinfo='skip',
            showlegend=True,
        )
        if row is not None and col is not None:
            fig.add_trace(trace, row=row, col=col)
        else:
            fig.add_trace(trace)


def _identify_corners(tel1, tel2):
    """Detects corners as local minima in speed and extracts comparison metrics."""
    corners = []
    
    # Smooth speed slightly for cleaner apex detection
    s1 = tel1['Speed'].rolling(window=15, center=True).mean().fillna(tel1['Speed'])
    
    # Use tel1 as the reference for distance.
    # Corner heuristic: local minima in a smoothed speed trace, spaced apart by distance.
    # This is intentionally approximate (not official corner numbering).
    for i in range(20, len(tel1) - 20):
        speed = s1.iloc[i]
        # Require a meaningful dip vs the surrounding trace to avoid spurious markers.
        if speed < (s1.iloc[i-12] - 6) and speed < (s1.iloc[i+12] - 6):
            dist = tel1['Distance'].iloc[i]
            # Avoid duplicate corners too close together
            if not corners or dist - corners[-1]['distance'] > 180:
                # Find corresponding point in tel2
                idx2 = (tel2['Distance'] - dist).abs().idxmin()
                
                corners.append({
                    'id': len(corners) + 1,
                    'distance': dist,
                    'v1_min': speed,
                    'v2_min': tel2['Speed'].iloc[idx2],
                    'x': tel1['X'].iloc[i],
                    'y': tel1['Y'].iloc[i]
                })
    return corners


def _identify_corners_from_circuit(session, tel1, tel2, window_m=30.0):
    """Map FastF1 circuit corner definitions onto lap telemetry.

    This uses `session.get_circuit_info().corners` when available to get the intended
    corner count and numbering, then finds the nearest telemetry point for placement.
    """
    try:
        circuit_info = session.get_circuit_info()
        corners_df = getattr(circuit_info, 'corners', None)
    except Exception:
        corners_df = None

    if corners_df is None:
        return []

    try:
        if isinstance(corners_df, pd.DataFrame):
            df = corners_df.copy()
        else:
            return []
    except Exception:
        return []

    if df.empty:
        return []

    # Expected columns (varies by FastF1 versions): Number, Letter, X, Y
    for required in ('Number', 'X', 'Y'):
        if required not in df.columns:
            return []

    # Normalize ordering: Number asc, then Letter (if present)
    if 'Letter' in df.columns:
        df['Letter'] = df['Letter'].fillna('').astype(str)
        df = df.sort_values(by=['Number', 'Letter'], kind='mergesort')
    else:
        df = df.sort_values(by=['Number'], kind='mergesort')

    tel_ref = _downsample(tel1, max_points=5000)
    tel_other = _downsample(tel2, max_points=5000)

    x_ref = tel_ref['X'].to_numpy(dtype=float)
    y_ref = tel_ref['Y'].to_numpy(dtype=float)
    d_ref = tel_ref['Distance'].to_numpy(dtype=float)

    corners = []
    for _, row in df.iterrows():
        try:
            num = int(row['Number'])
        except Exception:
            continue
        letter = ''
        if 'Letter' in df.columns:
            try:
                letter = str(row.get('Letter') or '').strip()
            except Exception:
                letter = ''
        turn_label = f"{num}{letter}" if letter else f"{num}"

        try:
            cx = float(row['X'])
            cy = float(row['Y'])
        except Exception:
            continue

        # Find nearest telemetry point by XY distance.
        # (Small N corners, modest telemetry size: brute force is fine.)
        dx = x_ref - cx
        dy = y_ref - cy
        idx = int((dx * dx + dy * dy).argmin())
        dist0 = float(d_ref[idx])

        # Use a distance window around the mapped point and take local min speeds.
        lo = dist0 - float(window_m)
        hi = dist0 + float(window_m)

        try:
            v1_min = float(tel1[(tel1['Distance'] >= lo) & (tel1['Distance'] <= hi)]['Speed'].min())
        except Exception:
            v1_min = float('nan')
        try:
            v2_min = float(tel2[(tel2['Distance'] >= lo) & (tel2['Distance'] <= hi)]['Speed'].min())
        except Exception:
            v2_min = float('nan')

        corners.append({
            'id': len(corners) + 1,
            'turn': turn_label,
            'distance': dist0,
            'v1_min': v1_min,
            'v2_min': v2_min,
            'x': float(x_ref[idx]),
            'y': float(y_ref[idx]),
        })

    return corners


def _build_mini_map_fig(tel1, hover_data):
    """Builds the small track map with a marker showing the current position."""
    import plotly.graph_objects as go
    fig = go.Figure()
    
    # Base track line (gray)
    tel_sampled = _downsample(tel1, max_points=1000)
    fig.add_trace(go.Scatter(
        x=tel_sampled['X'], y=tel_sampled['Y'], 
        mode='lines', line=dict(color='#444', width=2),
        hoverinfo='skip'
    ))
    
    # Hover position marker
    if hover_data and 'points' in hover_data:
        dist = hover_data['points'][0]['x']
        idx = (tel1['Distance'] - dist).abs().idxmin()
        fig.add_trace(go.Scatter(
            x=[tel1['X'].iloc[idx]], y=[tel1['Y'].iloc[idx]],
            mode='markers', marker=dict(color='#ff0000', size=12, symbol='circle',
                                        line=dict(color='white', width=2)),
            name='Current Position'
        ))
    
    _apply_base_layout(
        fig,
        margin=dict(l=0, r=0, t=0, b=0),
        xaxis=dict(visible=False, scaleanchor="y", scaleratio=1),
        yaxis=dict(visible=False),
        showlegend=False,
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)'
    )
    return fig


def _split_delta_by_sign(delta_dist, delta_values):
    """Split delta into ahead/behind traces that meet exactly at zero crossings."""
    ahead_x, ahead_y = [], []
    behind_x, behind_y = [], []
    prev_x, prev_y = None, None

    for raw_x, raw_y in zip(delta_dist, delta_values):
        x = float(raw_x) if np.isfinite(raw_x) else np.nan
        y = float(raw_y) if np.isfinite(raw_y) else np.nan

        if not np.isfinite(x) or not np.isfinite(y):
            ahead_x.append(x)
            ahead_y.append(np.nan)
            behind_x.append(x)
            behind_y.append(np.nan)
            prev_x, prev_y = None, None
            continue

        if prev_x is not None and (prev_y >= 0) != (y >= 0):
            denom = y - prev_y
            ratio = 0.0 if denom == 0 else -prev_y / denom
            cross_x = prev_x + ratio * (x - prev_x)

            ahead_x.append(cross_x)
            ahead_y.append(0.0)
            behind_x.append(cross_x)
            behind_y.append(0.0)

        ahead_x.append(x)
        behind_x.append(x)
        if y >= 0:
            ahead_y.append(y)
            behind_y.append(np.nan)
        else:
            ahead_y.append(np.nan)
            behind_y.append(y)

        prev_x, prev_y = x, y

    return (
        np.asarray(ahead_x, dtype=float),
        np.asarray(ahead_y, dtype=float),
        np.asarray(behind_x, dtype=float),
        np.asarray(behind_y, dtype=float),
    )


def _build_telemetry_fig(fast_data, slow_data, driver1_delta_data=None, driver2_delta_data=None):
    """Builds the 4-Row Telemetry Subplot (Delta, Speed, Throttle/Brake, Gear)."""
    from plotly.subplots import make_subplots
    fast_driver, fast_tel, fast_c, fast_t, fast_lap, fast_lbl = fast_data
    slow_driver, slow_tel, slow_c, slow_t, slow_lap, slow_lbl = slow_data

    if driver1_delta_data is None or driver2_delta_data is None:
        driver1, driver1_lap = slow_driver, slow_lap
        driver2, driver2_lap = fast_driver, fast_lap
    else:
        driver1, driver1_lap = driver1_delta_data
        driver2, driver2_lap = driver2_delta_data

    # FastF1 returns compare_time - reference_time. Use Driver 2 as the
    # reference and invert the sign so positive means Driver 1 is ahead.
    delta_time, ref_tel, comp_tel = _compute_lap_delta(driver2_lap, driver1_lap)

    fast_tel = _downsample(fast_tel)
    slow_tel = _downsample(slow_tel)

    fig = make_subplots(
        rows=4, cols=1, shared_xaxes=True, vertical_spacing=0.03,
        specs=[[{"secondary_y": False}], [{"secondary_y": False}], [{"secondary_y": True}], [{"secondary_y": False}]],
        row_heights=[0.15, 0.35, 0.25, 0.25]
    )

    # Row 1: Time Delta
    delta_values = -pd.Series(delta_time).astype(float).to_numpy()
    delta_dist = ref_tel['Distance'].to_numpy(dtype=float)
    delta_ahead_x, delta_ahead, delta_behind_x, delta_behind = _split_delta_by_sign(delta_dist, delta_values)
    finite_delta = delta_values[np.isfinite(delta_values)]
    delta_tick_kwargs = {}
    if len(finite_delta):
        max_abs_delta = float(np.nanmax(np.abs(finite_delta)))
        if max_abs_delta > 0:
            tick_vals = np.linspace(-max_abs_delta, max_abs_delta, 5)

            def _inverted_tick_label(value):
                shown = -float(value)
                if abs(shown) < 0.005:
                    shown = 0.0
                return f"{shown:+.2f}" if shown != 0 else "0.00"

            delta_tick_kwargs = {
                'tickmode': 'array',
                'tickvals': tick_vals.tolist(),
                'ticktext': [_inverted_tick_label(v) for v in tick_vals],
            }

    fig.add_trace(
        go.Scatter(
            x=delta_ahead_x,
            y=delta_ahead,
            mode='lines',
            name=f"{driver1} ahead",
            line=dict(color='#00c853', width=2),
            connectgaps=False,
            showlegend=False,
            hovertemplate=(
                f"Distance: %{{x:.0f}} m<br>"
                f"{driver1} gap: %{{y:.3f}} s<br>"
            )
        ),
        row=1, col=1)
    fig.add_trace(
        go.Scatter(
            x=delta_behind_x,
            y=delta_behind,
            mode='lines',
            name=f"{driver1} behind",
            line=dict(color='#ff4444', width=2),
            connectgaps=False,
            showlegend=False,
            hovertemplate=(
                f"Distance: %{{x:.0f}} m<br>"
                f"{driver1} gap: %{{y:.3f}} s<br>"
            )
        ),
        row=1, col=1)
    fig.add_annotation(
        xref="paper", yref="y domain", x=0.995, y=0.92,
        text=f" {driver1} ahead",
        showarrow=False, xanchor="right",
        font=dict(size=10, color='#60e890')
    )
    fig.add_annotation(
        xref="paper", yref="y domain", x=0.995, y=0.08,
        text=f" {driver1} behind",
        showarrow=False, xanchor="right",
        font=dict(size=10, color='#ff7777')
    )

    # Row 2: Speed
    fig.add_trace(go.Scatter(x=fast_tel['Distance'], y=fast_tel['Speed'], mode='lines', name=f'{fast_driver} Speed',
                             line=dict(color=fast_c, width=2), showlegend=False), row=2, col=1)
    fig.add_trace(go.Scatter(x=slow_tel['Distance'], y=slow_tel['Speed'], mode='lines', name=f'{slow_driver} Speed',
                             line=dict(color=slow_c, width=2), showlegend=False), row=2, col=1)

    # Row 3: Throttle and Brake
    fig.add_trace(
        go.Scatter(x=fast_tel['Distance'], y=fast_tel['Throttle'], mode='lines', name=f'{fast_driver} Throttle',
                   line=dict(color=fast_c, dash='solid'), showlegend=False), row=3, col=1, secondary_y=False)
    fig.add_trace(
        go.Scatter(x=slow_tel['Distance'], y=slow_tel['Throttle'], mode='lines', name=f'{slow_driver} Throttle',
                   line=dict(color=slow_c, dash='solid'), showlegend=False), row=3, col=1, secondary_y=False)
    fig.add_trace(go.Scatter(x=fast_tel['Distance'], y=fast_tel['Brake'], mode='lines', name=f'{fast_driver} Brake',
                             line=dict(color=fast_c, dash='dot'), opacity=0.7, showlegend=False), row=3, col=1, secondary_y=True)
    fig.add_trace(go.Scatter(x=slow_tel['Distance'], y=slow_tel['Brake'], mode='lines', name=f'{slow_driver} Brake',
                             line=dict(color=slow_c, dash='dot'), opacity=0.7, showlegend=False), row=3, col=1, secondary_y=True)

    # Row 4: Gear
    fig.add_trace(go.Scatter(x=fast_tel['Distance'], y=fast_tel['nGear'], mode='lines', name=f'{fast_driver} Gear',
                             line=dict(color=fast_c, width=2), showlegend=False), row=4, col=1)
    fig.add_trace(go.Scatter(x=slow_tel['Distance'], y=slow_tel['nGear'], mode='lines', name=f'{slow_driver} Gear',
                             line=dict(color=slow_c, width=2), showlegend=False), row=4, col=1)
    _add_driver_legend_entries(fig, [(fast_driver, fast_c), (slow_driver, slow_c)], row=2, col=1)

    _apply_base_layout(
        fig,
        title=f'Telemetry Traces: {fast_lbl} ({fast_t:.3f}s) vs {slow_lbl} ({slow_t:.3f}s)',
        title_font=dict(size=16),
        margin=dict(l=40, r=40, t=80, b=40),
        legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="center", x=0.5, font=dict(size=10)),
        uirevision='telemetry'
    )

    fig.update_yaxes(
        title_text=f"Time Delta (s)",
        zeroline=True,
        zerolinecolor='#bbbbbb',
        zerolinewidth=1,
        row=1,
        col=1,
        **delta_tick_kwargs
    )
    fig.update_yaxes(title_text="Speed (km/h)", row=2, col=1)
    fig.update_yaxes(title_text="Throttle (%)", row=3, col=1, secondary_y=False)
    fig.update_yaxes(title_text="Brake", row=3, col=1, secondary_y=True, showgrid=False)
    fig.update_yaxes(title_text="Gear", row=4, col=1, tickvals=[1, 2, 3, 4, 5, 6, 7, 8])
    fig.update_xaxes(title_text="Distance along track (meters)", row=4, col=1)

    return fig


def _build_dominance_fig(driver1, driver2, c1, c2, tel1, tel2, fast_data, slow_data, mode='dominance', session=None):
    """Builds the 2D Track Map with multiple overlay modes."""
    from plotly.subplots import make_subplots
    fast_driver, fast_tel, fast_c, fast_t, _, fast_lbl = fast_data
    slow_driver, slow_tel, slow_c, slow_t, _, slow_lbl = slow_data

    tel1_s = _downsample(tel1, max_points=3000)
    tel2_s = _downsample(tel2, max_points=3000)
    fast_tel_s = _downsample(fast_tel, max_points=3000)
    slow_tel_s = _downsample(slow_tel, max_points=3000)

    def _build_dense_grid(base_df, step_m=6.0):
        """Build a shared dense distance grid for marker overlays."""
        d = base_df['Distance'].to_numpy(dtype=float)
        x = base_df['X'].to_numpy(dtype=float)
        y = base_df['Y'].to_numpy(dtype=float)
        if len(d) < 2:
            return d, x, y
        d_dense = np.arange(float(d.min()), float(d.max()), step_m)
        if len(d_dense) < 2:
            return d, x, y
        x_dense = np.interp(d_dense, d, x)
        y_dense = np.interp(d_dense, d, y)
        return d_dense, x_dense, y_dense

    def _interp_metric(df, col, d_dense):
        """Interpolate a telemetry metric onto the shared dense grid."""
        if col not in df.columns or len(df) < 2:
            return np.zeros(len(d_dense))
        d = df['Distance'].to_numpy(dtype=float)
        v = np.nan_to_num(df[col].to_numpy(dtype=float), nan=0.0)
        return np.interp(d_dense, d, v)

    # Mini-sector logic
    num_ms = 50
    total_dist = max(tel1_s['Distance'].max(), tel2_s['Distance'].max())
    ms_len = total_dist / num_ms
    tel1_s['MS'] = (tel1_s['Distance'] // ms_len).astype(int).clip(upper=num_ms)
    tel2_s['MS'] = (tel2_s['Distance'] // ms_len).astype(int).clip(upper=num_ms)
    
    mode_title = {
        'dominance': 'Dominance',
        'braking': 'Braking',
        'speed': 'Speed'
    }.get(mode, str(mode).title())

    # Map lap times back to driver1/driver2 for display.
    if fast_driver == driver1:
        d1_time, d1_lbl = fast_t, fast_lbl
        d2_time, d2_lbl = slow_t, slow_lbl
    else:
        d1_time, d1_lbl = slow_t, slow_lbl
        d2_time, d2_lbl = fast_t, fast_lbl

    title_text = f"Track Map - {mode_title}<br><sup>{d1_lbl}: {d1_time:.3f}s | {d2_lbl}: {d2_time:.3f}s</sup>"

    if mode in ('braking', 'speed'):
        fig = make_subplots(
            rows=1,
            cols=2,
            subplot_titles=(
                f"{d1_lbl} ({d1_time:.3f}s)",
                f"{d2_lbl} ({d2_time:.3f}s)",
            ),
            horizontal_spacing=0.03,
        )
    else:
        fig = go.Figure()

    if mode == 'dominance':
        v1_avg = tel1_s.groupby('MS')['Speed'].mean()
        v2_avg = tel2_s.groupby('MS')['Speed'].mean()
        winners = [driver1 if v1_avg.get(i, 0) > v2_avg.get(i, 0) else driver2 for i in range(num_ms + 1)]
        
        # Plot with consecutive sector grouping
        group_start = 0
        for ms in range(1, num_ms + 1):
            if ms == num_ms or winners[ms] != winners[group_start]:
                sector_data = tel1_s[(tel1_s['MS'] >= group_start) & (tel1_s['MS'] <= ms)]
                if not sector_data.empty:
                    color = c1 if winners[group_start] == driver1 else c2
                    fig.add_trace(go.Scatter(
                        x=sector_data['X'], y=sector_data['Y'], mode='lines',
                        line=dict(color=color, width=8), showlegend=False,
                        hoverinfo='skip'
                    ))
                group_start = ms

        # Add Apex Markers for all corners if circuit corner metadata is available.
        corners = []
        if session is not None:
            corners = _identify_corners_from_circuit(session, tel1, tel2, window_m=28.0)
        if not corners:
            corners = _identify_corners(tel1, tel2)
        for c in corners:
            winner = driver1 if c['v1_min'] > c['v2_min'] else driver2
            color = c1 if winner == driver1 else c2
            fig.add_trace(go.Scatter(
                x=[c['x']], y=[c['y']], mode='markers+text',
                marker=dict(color=color, size=14, symbol='circle', line=dict(color='white', width=1)),
                # Use the corner number label to avoid cluttering the map with speed text.
                text=[str(c.get('turn', c.get('id', '')))], textposition="top center",
                textfont=dict(size=10, color='white'),
                name=f"Turn {c.get('turn', c.get('id'))} Apex",
                showlegend=False,
                hovertext=(
                    f"Turn {c.get('turn', c.get('id'))} Apex Speed<br>"
                    f"{driver1}: {int(c['v1_min'])} km/h<br>"
                    f"{driver2}: {int(c['v2_min'])} km/h"
                )
            ))

    elif mode == 'braking':
        # Braking intensity map, side-by-side (driver1 vs driver2).
        colorscale = [
            [0.00, '#2a2a2a'],
            [0.10, '#4d1f1f'],
            [0.30, '#8a1c1c'],
            [0.55, '#cc2020'],
            [1.00, '#ff3b3b']
        ]

        def _add_brake_subplot(base_tel_s, drv_label, col, show_scale):
            d_dense, x_dense, y_dense = _build_dense_grid(base_tel_s, step_m=4.5)
            brake_dense = _interp_metric(base_tel_s, 'Brake', d_dense)
            brake_view = np.power(np.clip(brake_dense, 0, 1), 0.6)
            fig.add_trace(go.Scatter(
                x=x_dense, y=y_dense, mode='lines',
                line=dict(color='rgba(255,255,255,0.18)', width=3),
                showlegend=False, hoverinfo='skip'
            ), row=1, col=col)
            fig.add_trace(go.Scatter(
                x=x_dense, y=y_dense, mode='markers',
                customdata=brake_dense,
                marker=dict(
                    color=brake_view,
                    colorscale=colorscale,
                    cmin=0,
                    cmax=1,
                    size=9,
                    opacity=0.98,
                    line=dict(width=0),
                    showscale=bool(show_scale),
                    colorbar=dict(
                        title='',
                        thickness=14,
                        len=0.78,
                        x=1.03,
                        y=0.5
                    ) if show_scale else None
                ),
                showlegend=False,
                hovertemplate=f'{drv_label}<br>Brake: %{{customdata:.2f}}<extra></extra>'
            ), row=1, col=col)

        _add_brake_subplot(tel1_s, driver1, col=1, show_scale=False)
        _add_brake_subplot(tel2_s, driver2, col=2, show_scale=True)
    
    elif mode == 'speed':
        # Top speed map, side-by-side (driver1 vs driver2).
        def _add_speed_subplot(base_tel_s, drv_label, col, show_scale):
            d_dense, x_dense, y_dense = _build_dense_grid(base_tel_s, step_m=4.5)
            speed_dense = _interp_metric(base_tel_s, 'Speed', d_dense)
            fig.add_trace(go.Scatter(
                x=x_dense, y=y_dense, mode='lines',
                line=dict(color='rgba(255,255,255,0.18)', width=3),
                showlegend=False, hoverinfo='skip'
            ), row=1, col=col)
            fig.add_trace(go.Scatter(
                x=x_dense, y=y_dense, mode='markers',
                marker=dict(
                    color=speed_dense,
                    colorscale='Viridis',
                    size=8,
                    opacity=0.95,
                    line=dict(width=0),
                    showscale=bool(show_scale),
                    colorbar=dict(
                        title='',
                        thickness=14,
                        len=0.78,
                        x=1.03,
                        y=0.5
                    ) if show_scale else None
                ),
                showlegend=False,
                hovertemplate=f'{drv_label}<br>Speed: %{{marker.color:.1f}} km/h<extra></extra>'
            ), row=1, col=col)

        _add_speed_subplot(tel1_s, driver1, col=1, show_scale=False)
        _add_speed_subplot(tel2_s, driver2, col=2, show_scale=True)

    # Legend surrogates
    if mode == 'dominance':
        _add_driver_legend_entries(fig, [(driver1, c1), (driver2, c2)])
    # Braking / speed use a colorbar instead of a legend.

    _apply_base_layout(
        fig,
        title=title_text,
        title_font=dict(size=18),
        hovermode="closest",
        showlegend=(mode == 'dominance'),
        legend=dict(yanchor="top", y=0.99, xanchor="left", x=0.01),
        margin=dict(l=40, r=(90 if mode in ('braking', 'speed') else 40), t=(95 if mode in ('braking', 'speed') else 70), b=40),
        uirevision=f'trackmap-{mode}'
    )

    if mode in ('braking', 'speed'):
        # Hide axes and preserve aspect ratio in both panels.
        fig.update_xaxes(visible=False, row=1, col=1)
        fig.update_yaxes(visible=False, row=1, col=1, scaleanchor="x1", scaleratio=1)
        fig.update_xaxes(visible=False, row=1, col=2)
        fig.update_yaxes(visible=False, row=1, col=2, scaleanchor="x2", scaleratio=1)
        # Push subplot titles (driver labels) down slightly so they don't clash with the main title.
        try:
            for ann in (fig.layout.annotations or []):
                if getattr(ann, 'text', None):
                    ann.update(y=float(getattr(ann, 'y', 1.0)) - 0.01, yanchor='top')
        except Exception:
            pass
    else:
        fig.update_layout(
            xaxis=dict(visible=False, scaleanchor="y", scaleratio=1),
            yaxis=dict(visible=False),
        )
    return fig


DNA_CATEGORY_LABELS = [
    'Top Speed (km/h)',
    'Corner Speed <220 (km/h)',
    'Full Throttle (%)',
    'Throttle Ramp (p90 Δ)',
    'Brake Usage (%)',
    'Brake Intensity (avg %)',
    'Gear Diversity (entropy)',
]

DNA_ABBRS = ['TS', 'CS', 'FT', 'TR', 'BU', 'BI', 'GD']


def _driver_dna_legend():
    """Return the short labels and long labels used by the Driver DNA chart."""
    abbrs = DNA_ABBRS[:]
    if len(abbrs) != len(DNA_CATEGORY_LABELS):
        abbrs = [chr(ord('A') + i) for i in range(len(DNA_CATEGORY_LABELS))]
    return list(zip(abbrs, DNA_CATEGORY_LABELS))


def _compute_driver_dna_raw(tel):
    """Return raw Driver DNA metrics using the same source data as the radar chart."""
    if tel is None or getattr(tel, 'empty', False):
        return [0.0] * len(DNA_CATEGORY_LABELS)

    speed_under_220 = tel[tel['Speed'] < 220]['Speed']
    brake_nonzero = tel[tel['Brake'] > 0.05]['Brake']
    throttle = tel['Throttle'].to_numpy(dtype=float)
    throttle_smooth = np.clip(np.diff(throttle, prepend=throttle[0]), 0, None)
    gear_counts = tel['nGear'].value_counts(normalize=True, dropna=True)
    gear_entropy = float(-(gear_counts * np.log2(gear_counts)).sum()) if not gear_counts.empty else 0.0
    computed = {
        'Top Speed (km/h)': float(tel['Speed'].max()),
        'Corner Speed <220 (km/h)': float(speed_under_220.mean()) if not speed_under_220.empty else 100.0,
        'Full Throttle (%)': float((tel['Throttle'] >= 99).mean() * 100.0),
        'Throttle Ramp (p90 Δ)': float(np.percentile(throttle_smooth, 90)),
        'Brake Usage (%)': float((tel['Brake'] > 0.05).mean() * 100.0),
        'Brake Intensity (avg %)': float(brake_nonzero.mean() * 100.0) if not brake_nonzero.empty else 0.0,
        'Gear Diversity (entropy)': float(gear_entropy),
    }
    return [computed[name] for name in DNA_CATEGORY_LABELS]


def _normalize_driver_dna(raw1, raw2):
    """Return the normalized 0-100 radar scores for a pair of raw DNA metric lists."""
    # Compressed, symmetric scoring around 50:
    # - 50 means "roughly equal"
    # - scores move toward 50 for small differences (so the chart isn't wildly different
    #   when the raw traces look similar), but meaningful deltas still show up.
    norm1, norm2 = [], []
    amp = 32.0  # max deviation from 50 in either direction (keeps the plot less extreme)
    k = 0.08    # ~8% relative difference is "strong"
    for a, b in zip(raw1, raw2):
        scale = max(abs(a), abs(b), 1.0)
        rel = (a - b) / scale
        if abs(a - b) <= 0.005 * scale:
            d = 0.0
        else:
            d = float(np.tanh(rel / k))
        norm1.append(50.0 + amp * d)
        norm2.append(50.0 - amp * d)
    return norm1, norm2


def _compute_driver_dna_summary(tel1, tel2):
    """Return legend, raw values, and normalized chart values for Driver DNA."""
    raw1 = _compute_driver_dna_raw(tel1)
    raw2 = _compute_driver_dna_raw(tel2)
    norm1, norm2 = _normalize_driver_dna(raw1, raw2)
    return _driver_dna_legend(), raw1, raw2, norm1, norm2


def _build_driver_radar(driver1, driver2, c1, c2, tel1, tel2):
    """Computes and builds a normalized Driver DNA radar chart.

    Returns:
        (fig, legend_map): Plotly figure + list of (letter, long_label) tuples for UI legend.
    """
    legend_map, _, _, norm1, norm2 = _compute_driver_dna_summary(tel1, tel2)
    abbrs = [abbr for abbr, _ in legend_map]

    # Close the loop explicitly so the first and last points connect around the horn.
    categories_closed = abbrs + [abbrs[0]] if abbrs else abbrs
    norm1_closed = norm1 + [norm1[0]] if norm1 else norm1
    norm2_closed = norm2 + [norm2[0]] if norm2 else norm2

    fig = go.Figure()
    fig.add_trace(go.Scatterpolar(
        r=norm1_closed, theta=categories_closed, fill='toself', name=driver1,
        line=dict(color=c1, width=2),
        fillcolor=_hex_to_rgba(c1, 0.15)
    ))
    fig.add_trace(go.Scatterpolar(
        r=norm2_closed, theta=categories_closed, fill='toself', name=driver2,
        line=dict(color=c2, width=2),
        fillcolor=_hex_to_rgba(c2, 0.15)
    ))

    fig.update_layout(
        title=dict(text='', x=0.5),
        polar=dict(
            radialaxis=dict(visible=True, range=[0, 100], tickfont=dict(size=8), gridcolor='#333'),
            angularaxis=dict(tickfont=dict(size=12)),
            bgcolor='rgba(0,0,0,0)'
        ),
        showlegend=True,
        legend=dict(orientation='h', yanchor='bottom', y=1.22, xanchor='center', x=0.5, font=dict(size=10)),
        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
        margin=dict(l=25, r=25, t=60, b=10),
        autosize=True,
        template='plotly_dark'
    )
    return fig, legend_map


def _build_strategy_fig(session, driver1, driver2, lbl1, lbl2, c1, c2):
    """Builds the Race Pace, Pits, Tyres & Weather dual-axis strategy plot."""
    from plotly.subplots import make_subplots

    # 1. Fetch unfiltered laps
    unf_1 = session.laps.pick_drivers(driver1).reset_index(drop=True)
    unf_2 = session.laps.pick_drivers(driver2).reset_index(drop=True)

    clean_1 = unf_1.pick_wo_box().pick_track_status('1')
    clean_2 = unf_2.pick_wo_box().pick_track_status('1')
    all_laps1 = clean_1[clean_1['LapNumber'] > 1].reset_index(drop=True)
    all_laps2 = clean_2[clean_2['LapNumber'] > 1].reset_index(drop=True)

    # 3. Calculate seconds, fallback for red flags (NaT)
    for laps_df in [all_laps1, all_laps2]:
        laps_df['LapTime_Sec'] = laps_df['LapTime'].dt.total_seconds()
        laps_df['LapTime_Sec'] = laps_df['LapTime_Sec'].fillna(
            (laps_df['Time'] - laps_df['LapStartTime']).dt.total_seconds())

    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.05,
        row_heights=[0.75, 0.25], subplot_titles=("", "Track Temperature (°C)")
    )

    comp_drawn = set()

    # 4. Plot Pace & Tyres
    for lap_data, drv, lbl, col, unf in [(all_laps1, driver1, lbl1, c1, unf_1),
                                          (all_laps2, driver2, lbl2, c2, unf_2)]:
        if 'Compound' in lap_data.columns and 'Stint' in lap_data.columns:
            for stint in lap_data['Stint'].dropna().unique():
                stint_subset = lap_data[lap_data['Stint'] == stint].sort_values(by='LapNumber')
                if stint_subset.empty:
                    continue

                comp = stint_subset['Compound'].iloc[0]
                comp_drawn.add(comp)

                fig.add_trace(go.Scatter(
                    x=stint_subset['LapNumber'], y=stint_subset['LapTime_Sec'],
                    mode='lines+markers', name=f'{drv} {comp}',
                    line=dict(color=col, width=2),
                    marker=dict(color=COMPOUND_COLORS.get(comp, 'grey'), size=10, symbol='circle', line=dict(width=0)),
                    showlegend=False
                ), row=1, col=1)

        pit_laps = unf[unf['PitInTime'].notna()]['LapNumber'].tolist()
        for pl in pit_laps:
            fig.add_vline(x=pl, line_width=1.5, line_dash="dot", line_color=col, opacity=0.6,
                          row='all', col='all')

    # 5. Overlay SC/VSC/Red Flag areas
    sc_laps, vsc_laps, red_laps = get_track_status_events(session)

    lines = [(sc_laps, 'orange', 'SC / YF'), (vsc_laps, 'yellow', 'VSC'), (red_laps, 'red', 'Red Flag')]
    for laps, color, name in lines:
        for start_lap, end_lap in _collapse_lap_ranges(laps):
            fig.add_vrect(x0=start_lap - 0.5, x1=end_lap + 0.5, fillcolor=color, opacity=0.15,
                          layer="below", line_width=0, row='all', col='all')
        if laps:
            fig.add_trace(go.Scatter(x=[None], y=[None], mode='markers',
                                     marker=dict(color=color, symbol='square', size=12, opacity=0.5),
                                     name=name, showlegend=False, legend='legend'), row=1, col=1)

    # General Legend additions
    _add_driver_legend_entries(fig, [(driver1, c1), (driver2, c2)], row=1, col=1)
    for comp in comp_drawn:
        if comp in COMPOUND_COLORS:
            fig.add_trace(go.Scatter(x=[None], y=[None], mode='markers', name=comp,
                                     marker=dict(color=COMPOUND_COLORS[comp], size=10),
                                     showlegend=False, legend='legend'), row=1, col=1)

    # 6. Weather & Rain Overlay
    weather_data = session.weather_data
    if not weather_data.empty and not session.laps.empty:
        try:
            laps_with_times = session.laps.dropna(subset=['LapNumber', 'Time']).copy()
            weather_sorted = weather_data.dropna(subset=['Time']).sort_values('Time')

            if not laps_with_times.empty and not weather_sorted.empty:
                if 'LapStartTime' in laps_with_times.columns:
                    laps_with_times['LapWeatherStart'] = laps_with_times['LapStartTime']
                elif 'LapTime' in laps_with_times.columns:
                    laps_with_times['LapWeatherStart'] = laps_with_times['Time'] - laps_with_times['LapTime']
                else:
                    laps_with_times['LapWeatherStart'] = laps_with_times['Time']

                lap_bounds = (
                    laps_with_times
                    .dropna(subset=['LapWeatherStart'])
                    .groupby('LapNumber')
                    .agg({'LapWeatherStart': 'min', 'Time': 'max'})
                    .reset_index()
                )
                
                # Track Temp plotting (nearest point is fine for a line)
                if not lap_bounds.empty and 'TrackTemp' in weather_sorted.columns:
                    lap_times_for_temp = lap_bounds[['LapNumber', 'Time']].copy()
                    temp_weather = weather_sorted[['Time', 'TrackTemp']].dropna(subset=['TrackTemp'])
                    if not temp_weather.empty:
                        merged_temp = pd.merge_asof(
                            lap_times_for_temp.sort_values('Time'),
                            temp_weather,
                            on='Time',
                            direction='nearest'
                        ).dropna(subset=['TrackTemp'])

                        if not merged_temp.empty:
                            fig.add_trace(go.Scatter(
                                x=merged_temp['LapNumber'], y=merged_temp['TrackTemp'],
                                mode='lines+markers', name='Track Temp (°C)',
                                line=dict(color='white', width=2), marker=dict(size=4), showlegend=False
                            ), row=2, col=1)

                # Rain detection: Check if ANY rainfall occurred within the lap's time window
                rain_laps = []
                rain_weather = (
                    weather_sorted[weather_sorted['Rainfall'].fillna(False).astype(bool)]
                    if 'Rainfall' in weather_sorted.columns else pd.DataFrame()
                )
                
                if not rain_weather.empty:
                    for _, lap in lap_bounds.iterrows():
                        # If any rain timestamp falls between StartTime and Time (end) of the lap
                        has_rain = rain_weather[(rain_weather['Time'] >= lap['LapWeatherStart']) &
                                                (rain_weather['Time'] <= lap['Time'])].any().any()
                        if has_rain:
                            rain_laps.append(lap['LapNumber'])

                for lap in rain_laps:
                    fig.add_vrect(x0=lap - 0.5, x1=lap + 0.5, fillcolor="blue", opacity=0.2, layer="below",
                                  line_width=0, row='all', col='all')
                
                if rain_laps:
                    fig.add_trace(go.Scatter(x=[None], y=[None], mode='markers',
                                             marker=dict(color='blue', opacity=0.5, symbol='square', size=15), name='Rain',
                                             showlegend=False, legend='legend'), row=1, col=1)
        except Exception:
            pass

    _apply_base_layout(
        fig,
        title="Strategy & Weather",
        legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="center", x=0.5, font=dict(size=10)),
        uirevision='strategy'
    )
    fig.update_xaxes(title_text="Lap Number", row=2, col=1)
    fig.update_yaxes(title_text="Pace (s)", row=1, col=1, autorange="reversed")
    fig.update_yaxes(title_text="Temp (°C)", row=2, col=1)

    return fig


def _build_deg_fig(session, driver1, driver2, lbl1, lbl2, c1, c2):
    """Fuel-corrected tyre degradation analysis per stint, side-by-side."""
    from plotly.subplots import make_subplots
    FUEL_CORRECTION = 0.06

    fig = make_subplots(rows=1, cols=2, shared_yaxes=True, subplot_titles=(lbl1, lbl2),
                        horizontal_spacing=0.05)

    for col_idx, (drv, lbl, color) in enumerate([(driver1, lbl1, c1), (driver2, lbl2, c2)], 1):
        try:
            all_laps = session.laps.pick_drivers(drv).reset_index(drop=True)
            clean_laps = all_laps.pick_wo_box().pick_track_status('1')
            racing_laps = clean_laps[clean_laps['LapNumber'] > 1].reset_index(drop=True)
            racing_laps['LapTime_Sec'] = racing_laps['LapTime'].dt.total_seconds()
            racing_laps = racing_laps.dropna(subset=['LapTime_Sec'])

            if 'Stint' not in racing_laps.columns or racing_laps.empty:
                continue

            for stint in sorted(racing_laps['Stint'].dropna().unique()):
                stint_data = racing_laps[racing_laps['Stint'] == stint].sort_values('LapNumber').copy()
                if len(stint_data) < 2:
                    continue

                comp = stint_data['Compound'].iloc[0] if 'Compound' in stint_data.columns else 'Unknown'
                stint_data['StintLap'] = range(1, len(stint_data) + 1)

                stint_data['CorrectedTime'] = stint_data['LapTime_Sec'] + FUEL_CORRECTION * stint_data['StintLap']
                marker_color = COMPOUND_COLORS.get(comp, 'grey')

                fig.add_trace(go.Scatter(
                    x=stint_data['StintLap'], y=stint_data['CorrectedTime'],
                    mode='lines+markers', name=f'{drv} {comp} (Stint {int(stint)})',
                    marker=dict(color=marker_color, size=7),
                    line=dict(color=marker_color, width=1.5),
                    showlegend=False,
                    hovertemplate=f'{drv} Stint {int(stint)} ({comp})<br>'
                                  f'Stint Lap %{{x}}<br>Corrected: %{{y:.3f}}s<extra></extra>'
                ), row=1, col=col_idx)

                fit_data = stint_data.dropna(subset=['StintLap', 'CorrectedTime'])
                if len(fit_data) >= 3:
                    slope, intercept = np.polyfit(
                        fit_data['StintLap'].values.astype(float),
                        fit_data['CorrectedTime'].values, 1)

                    x_fit = [fit_data['StintLap'].min(), fit_data['StintLap'].max()]
                    y_fit = [slope * x + intercept for x in x_fit]
                    fig.add_trace(go.Scatter(
                        x=x_fit, y=y_fit, mode='lines',
                        line=dict(dash='dash', color=marker_color, width=2),
                        name=f'{drv} {comp} [{slope:+.3f}s/lap]',
                        showlegend=False
                    ), row=1, col=col_idx)
        except Exception:
            continue

    _apply_base_layout(
        fig,
        title='Tyre Degradation Analysis (Fuel-Corrected, ~0.06s/lap)<br><sup>+ = more degradation, - = pace improving</sup>',
        margin=dict(l=40, r=40, t=80, b=40),
        showlegend=False,
        uirevision='degradation'
    )
    fig.update_yaxes(title_text='Fuel-Corrected Lap Time (s)', row=1, col=1, autorange='reversed')
    fig.update_xaxes(title_text='Stint Lap', row=1, col=1)
    fig.update_xaxes(title_text='Stint Lap', row=1, col=2)

    return fig


def _build_race_gaps_fig(session, driver1, driver2, lbl1, lbl2, c1, c2):
    """Builds the gap-between-drivers chart over race laps."""
    from plotly.subplots import make_subplots
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.08,
                        row_heights=[0.7, 0.3],
                        subplot_titles=('Gap Between Drivers', 'Position'))

    try:
        laps1 = session.laps.pick_drivers(driver1).sort_values('LapNumber').dropna(subset=['Time'])
        laps2 = session.laps.pick_drivers(driver2).sort_values('LapNumber').dropna(subset=['Time'])

        merged = pd.merge(
            laps1[['LapNumber', 'Time', 'Position']].rename(columns={'Time': 'Time1', 'Position': 'Pos1'}),
            laps2[['LapNumber', 'Time', 'Position']].rename(columns={'Time': 'Time2', 'Position': 'Pos2'}),
            on='LapNumber', how='inner'
        )

        if merged.empty:
            raise ValueError("No common laps between drivers")

        merged['Gap'] = (merged['Time1'] - merged['Time2']).dt.total_seconds()

        fig.add_trace(go.Scatter(
            x=merged['LapNumber'], y=merged['Gap'], mode='lines',
            fill='tozeroy', line=dict(color='white', width=2),
            fillcolor='rgba(255,255,255,0.1)',
            name='Gap',
            showlegend=False,
            hovertemplate='Lap %{x}<br>Gap: %{y:.3f}s<extra></extra>'
        ), row=1, col=1)

        fig.add_hline(y=0, line_dash="dash", line_color="grey", opacity=0.5, row=1, col=1)

        fig.add_annotation(xref="paper", yref="y domain", x=1.02, y=0.95,
                           text=f"↑ {driver2} ahead", showarrow=False, font=dict(size=11, color=c2),
                           xanchor="left", row=1, col=1)
        fig.add_annotation(xref="paper", yref="y domain", x=1.02, y=0.05,
                           text=f"↓ {driver1} ahead", showarrow=False, font=dict(size=11, color=c1),
                           xanchor="left", row=1, col=1)

        grid1, grid2 = None, None
        if getattr(session, 'results', None) is not None and not session.results.empty:
            res1 = session.results[session.results['Abbreviation'] == driver1]
            if not res1.empty: grid1 = res1.iloc[0].get('GridPosition')
            res2 = session.results[session.results['Abbreviation'] == driver2]
            if not res2.empty: grid2 = res2.iloc[0].get('GridPosition')

        if 'Pos1' in merged.columns:
            x_vals = merged['LapNumber'].tolist()
            y_vals = merged['Pos1'].astype(float).tolist()
            if grid1 is not None and grid1 > 0:
                x_vals = [0] + x_vals
                y_vals = [float(grid1)] + y_vals
            
            fig.add_trace(go.Scatter(
                x=x_vals, y=y_vals, mode='lines',
                name=f'{lbl1} Pos', line=dict(color=c1, width=2), showlegend=False
            ), row=2, col=1)

        if 'Pos2' in merged.columns:
            x_vals = merged['LapNumber'].tolist()
            y_vals = merged['Pos2'].astype(float).tolist()
            if grid2 is not None and grid2 > 0:
                x_vals = [0] + x_vals
                y_vals = [float(grid2)] + y_vals

            fig.add_trace(go.Scatter(
                x=x_vals, y=y_vals, mode='lines',
                name=f'{lbl2} Pos', line=dict(color=c2, width=2), showlegend=False
            ), row=2, col=1)

        _add_driver_legend_entries(fig, [(driver1, c1), (driver2, c2)], row=2, col=1)

        for drv, color, laps_df in [(driver1, c1, laps1), (driver2, c2, laps2)]:
            pit_laps = laps_df[laps_df['PitInTime'].notna()]['LapNumber'].tolist()
            for pl in pit_laps:
                fig.add_vline(x=pl, line_width=1.5, line_dash="dot", line_color=color, opacity=0.6,
                              row='all', col='all')

        sc_laps, vsc_laps, red_laps = get_track_status_events(session)
        for laps_set, color, name in [(sc_laps, 'orange', 'SC'), (vsc_laps, 'yellow', 'VSC'),
                                      (red_laps, 'red', 'Red Flag')]:
            for start_lap, end_lap in _collapse_lap_ranges(laps_set):
                fig.add_vrect(x0=start_lap - 0.5, x1=end_lap + 0.5, fillcolor=color, opacity=0.1,
                              layer="below", line_width=0, row='all', col='all')

    except Exception as e:
        fig.add_annotation(text=f"Race gap data unavailable: {e}", showarrow=False,
                           font=dict(size=16, color='#ff4444'), xref="paper", yref="paper", x=0.5, y=0.5)

    _apply_base_layout(
        fig,
        title='Race Gap & Position Analysis',
        margin=dict(l=40, r=40, t=80, b=40), uirevision='gaps'
    )
    fig.update_yaxes(title_text='Gap (seconds)', row=1, col=1)
    fig.update_yaxes(title_text='Position', row=2, col=1, autorange='reversed',
                     tickvals=list(range(1, 21)))
    fig.update_xaxes(title_text='Lap Number', row=2, col=1)

    return fig


def _build_grid_pace_fig(session, session_type):
    """Builds a box plot of lap time distributions for all drivers."""
    from data import is_race, is_qualifying
    fig = go.Figure()
    drivers_data = []

    if getattr(session, 'results', None) is not None and not session.results.empty:
        results_df = session.results.copy()
        results_df['Position_Num'] = pd.to_numeric(results_df['Position'], errors='coerce')
        results_df = results_df.sort_values(by='Position_Num')
        sorted_result_drivers = [
            d for d in results_df['Abbreviation'].dropna().tolist()
            if isinstance(d, str) and len(d) == 3
        ]
        all_drivers = sorted_result_drivers
    else:
        all_drivers = session.laps['Driver'].unique().tolist()

    has_results = getattr(session, 'results', None) is not None and not session.results.empty
    _is_race = is_race(session_type)
    _is_quali = is_qualifying(session_type)
    position_map = {}
    if has_results:
        position_map = {
            str(row.get('Abbreviation', '')): pd.to_numeric(row.get('Position'), errors='coerce')
            for _, row in session.results.iterrows()
        }
    # Calculate session-wide fastest lap for 107% filtering.
    lap_seconds_all = session.laps['LapTime'].dt.total_seconds().dropna()
    session_fastest = lap_seconds_all.min() if not lap_seconds_all.empty else float('nan')
    rain_ratio = 0
    weather_data = getattr(session, 'weather_data', None)
    if weather_data is not None and not weather_data.empty and 'Rainfall' in weather_data.columns:
        rain_ratio = weather_data['Rainfall'].astype(bool).mean()
    is_dry_session = rain_ratio < 0.02

    for drv in all_drivers:
        if not isinstance(drv, str) or len(drv) != 3:
            continue
        try:
            drv_laps = session.laps.pick_drivers(drv)
            if drv_laps.empty:
                continue

            if _is_race:
                clean_laps = drv_laps.pick_wo_box().pick_track_status('1')
                laps = clean_laps[clean_laps['LapNumber'] > 1]
            else:
                laps = drv_laps.pick_quicklaps()

            if laps.empty:
                continue

            lap_times = laps['LapTime'].dt.total_seconds().dropna()
            
            if is_dry_session and pd.notna(session_fastest) and not lap_times.empty:
                lap_times = lap_times[lap_times <= session_fastest * 1.07]

            if lap_times.empty:
                continue

            color = get_single_driver_color(drv, session)

            # For ordering/tie-break purposes in this chart, the filtered lap minimum is sufficient
            # and avoids an extra per-driver best-lap lookup.
            best_time = float(lap_times.min())

            pos = 999
            pos_num = position_map.get(drv)
            if pd.notna(pos_num):
                pos = int(pos_num)

            drivers_data.append({
                'driver': drv,
                'times': lap_times.tolist(),
                'fastest': best_time,
                'median': lap_times.median(),
                'color': color,
                'position': pos
            })

        except Exception:
            continue

    _is_practice = is_practice(session_type)
    _is_shootout = 'Shootout' in session_type

    if not has_results or _is_practice or _is_shootout:
        # For practice and shootout sessions (and any session where results are missing),
        # we calculate the sort order from the laps (fastest lap for practice/quali, median for race).
        sort_key = 'fastest' if (_is_quali or _is_practice or _is_shootout) else 'median'
        drivers_data.sort(key=lambda x: x[sort_key])
        category_array = [d['driver'] for d in drivers_data]
    else:
        # Use the exact same official ordering basis as leaderboard.
        category_array = sorted_result_drivers

    for d in drivers_data:
        fig.add_trace(go.Box(
            y=d['times'], name=d['driver'],
            marker_color=d['color'], line_color=d['color'],
            boxmean=True,
            hovertemplate=f"{d['driver']}<br>Lap Time: %{{y:.3f}}s<extra></extra>"
        ))

    session_label = "Racing Laps" if _is_race else "Practice Laps" if is_practice(
        session_type) else "Qualifying Laps"
    _apply_base_layout(
        fig,
        title=f'Grid Pace Distribution ({session_label}, Sorted by Finishing Position)',
        showlegend=False,
        hovermode='closest',
        yaxis_title='Lap Time (s)',
        xaxis=dict(
            categoryorder='array',
            categoryarray=category_array
        ),
        yaxis=dict(autorange='reversed'),
        uirevision='gridpace'
    )

    return fig


def _build_pit_stops_fig(session, driver1, driver2, lbl1, lbl2, c1, c2):
    """Builds a pit stop duration comparison chart for all drivers."""
    pit_data = []
    title = 'Pit Stop Durations (Time spent in pit lane)'
    hover_label = 'Stop Time'

    session_name = getattr(session, 'name', '')
    max_lap = 999
    try:
        if not session.laps.empty:
            max_lap = int(session.laps['LapNumber'].max())
    except Exception:
        pass

    try:
        # Only use official Ergast data for the main Race; Sprints use the robust fallback below
        if session_name == 'Race':
            pit_stops = get_pit_stop_data(session.event.year, session.event.RoundNumber)
        else:
            pit_stops = pd.DataFrame()
    except Exception:
        pit_stops = pd.DataFrame()

    if pit_stops is not None and not pit_stops.empty:
        if 'duration' in pit_stops.columns:
            pit_stops = pit_stops.copy()
            pit_stops['duration_seconds'] = pit_stops['duration'].apply(
                lambda x: x.total_seconds() if pd.notna(x) else None
            )
            valid = pit_stops[
                pit_stops['lap'].notna()
                & pit_stops['duration_seconds'].notna()
                & (pit_stops['lap'].astype(int) <= max_lap)
                & (pit_stops['duration_seconds'] > 0)
                & (pit_stops['duration_seconds'] < 120)
            ].copy()
            if not valid.empty:
                valid['driver_code'] = valid.apply(
                    lambda r: r.get('driverCode') or str(r.get('driverId', '')).upper()[:3],
                    axis=1
                )
                valid = valid[valid['driver_code'].astype(str).str.len() == 3]
                for stop in valid.to_dict('records'):
                    drv = stop['driver_code']
                    color = get_single_driver_color(drv, session)
                    pit_data.append({
                        'driver': drv,
                        'lap': int(stop['lap']),
                        'duration': float(stop['duration_seconds']),
                        'color': color,
                        'highlight': drv in [driver1, driver2]
                    })

    if not pit_data:
        title = 'Pit Stop Durations (Time Spent in Pit Lane)'
        hover_label = 'Pit Lane Time'

        all_drivers = []
        if getattr(session, 'results', None) is not None and not session.results.empty:
            all_drivers = [d for d in session.results['Abbreviation'].dropna().tolist()
                           if isinstance(d, str) and len(d) == 3]

        for drv in all_drivers:
            try:
                drv_laps = session.laps.pick_drivers(drv).sort_values('LapNumber')
                pit_in = drv_laps[drv_laps['PitInTime'].notna()][['LapNumber', 'PitInTime']]
                if pit_in.empty:
                    continue
                pit_out_map = drv_laps.set_index('LapNumber')['PitOutTime'].to_dict()
                color = get_single_driver_color(drv, session)
                for lap_num, pit_in_time in pit_in.itertuples(index=False):
                    pit_out_time = pit_out_map.get(lap_num + 1)
                    if pd.notna(pit_out_time):
                        duration = (pit_out_time - pit_in_time).total_seconds()
                        if 10 < duration < 120:
                            pit_data.append({
                                'driver': drv,
                                'lap': int(lap_num),
                                'duration': duration,
                                'color': color,
                                'highlight': drv in [driver1, driver2]
                            })
            except Exception:
                continue

    if not pit_data:
        fig = go.Figure()
        fig.add_annotation(text="No pit stop data available", showarrow=False,
                           font=dict(size=18), xref="paper", yref="paper", x=0.5, y=0.5)
        _apply_base_layout(fig, hovermode='closest')
        return fig

    pit_data.sort(key=lambda x: x['duration'])

    x_labels = [f"{p['driver']} L{p['lap']}" for p in pit_data]
    y_values = [p['duration'] for p in pit_data]
    colors = [p['color'] for p in pit_data]
    border_widths = [3 if p['highlight'] else 0 for p in pit_data]
    border_colors = ['white' if p['highlight'] else p['color'] for p in pit_data]
    text_labels = [f"{p['duration']:.1f}s" for p in pit_data]
    hover_texts = [f"{p['driver']} - Lap {p['lap']}<br>{hover_label}: {p['duration']:.1f}s" for p in pit_data]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=x_labels,
        y=y_values,
        marker_color=colors,
        marker_line_width=border_widths,
        marker_line_color=border_colors,
        text=text_labels,
        textposition='auto',
        showlegend=False,
        hovertext=hover_texts,
        hoverinfo='text'
    ))

    _apply_base_layout(
        fig,
        title=title,
        hovermode='closest',
        yaxis_title='Duration (s)',
        xaxis_title='Driver & Lap',
        margin=dict(l=40, r=40, t=60, b=80),
        xaxis_tickangle=-45,
        uirevision='pitstops'
    )

    return fig
