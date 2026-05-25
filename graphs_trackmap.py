"""Track map and Driver DNA graph builders."""
import numpy as np
import pandas as pd
import plotly.graph_objects as go

from graphs_common import _add_driver_legend_entries
from ui_utils import _apply_base_layout, _downsample, _hex_to_rgba


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
