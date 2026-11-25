"""Track map and Driver DNA graph builders."""
import numpy as np
import pandas as pd
import plotly.graph_objects as go

from graphs_common import _add_driver_legend_entries
from ui_utils import _apply_base_layout, _downsample, _hex_to_rgba


DNA_CATEGORY_LABELS = [
    'Top Speed (km/h)',
    'Mean Corner Apex Speed (km/h)',
    'Full Throttle (%)',
    'Throttle Ramp (p90 Δ)',
    'Brake Usage (%)',
    'Gear Diversity (entropy)',
]

DNA_ABBRS = ['TS', 'CS', 'FT', 'TR', 'BU', 'GD']


def _identify_corners(tel1, tel2):
    """Detects corners as local minima in speed and extracts comparison metrics."""
    corners = []
    if tel1 is None or tel1.empty or tel2 is None or tel2.empty:
        return corners
    required_cols_1 = ['Speed', 'Distance', 'X', 'Y']
    required_cols_2 = ['Speed', 'Distance']
    if not all(col in tel1.columns for col in required_cols_1) or not all(col in tel2.columns for col in required_cols_2):
        return corners
    
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


def _validated_circuit_corners(circuit_corners, telemetry):
    """Accept official turn points only when their coordinates match the lap."""
    if telemetry is None or telemetry.empty or circuit_corners is None:
        return []
    corners = circuit_corners.copy() if hasattr(circuit_corners, 'copy') and hasattr(circuit_corners, 'columns') else circuit_corners
    if hasattr(corners, 'to_dict'):
        corners = corners.to_dict('records')
    if not isinstance(corners, (list, tuple)) or not corners:
        return []
    valid = []
    for row in corners:
        try:
            number, x, y = int(row['number']), float(row['x']), float(row['y'])
        except (KeyError, TypeError, ValueError):
            continue
        if np.isfinite(x) and np.isfinite(y):
            valid.append({**row, 'number': number, 'x': x, 'y': y})
    if not valid or not {'X', 'Y'}.issubset(telemetry.columns):
        return []
    track_x = telemetry['X'].to_numpy(dtype=float)
    track_y = telemetry['Y'].to_numpy(dtype=float)
    track_x, track_y = track_x[np.isfinite(track_x)], track_y[np.isfinite(track_y)]
    if not len(track_x) or not len(track_y):
        return []
    span = max(float(np.ptp(track_x)), float(np.ptp(track_y)), 1.0)
    margin = max(60.0, span * 0.06)
    inside = [
        row for row in valid
        if track_x.min() - margin <= row['x'] <= track_x.max() + margin
        and track_y.min() - margin <= row['y'] <= track_y.max() + margin
    ]
    return sorted(inside, key=lambda row: row['number']) if len(inside) >= max(4, int(len(valid) * 0.75)) else []


def _build_dominance_fig(
    driver1,
    driver2,
    c1,
    c2,
    tel1,
    tel2,
    fast_data,
    slow_data,
    mode='dominance',
    session=None,
    circuit_corners=None,
):
    """Builds the 2D Track Map with multiple overlay modes."""
    from plotly.subplots import make_subplots
    fast_driver, _, fast_c, fast_t, _, fast_lbl = fast_data
    slow_driver, _, slow_c, slow_t, _, slow_lbl = slow_data

    tel1_s = _downsample(tel1, max_points=3000)
    tel2_s = _downsample(tel2, max_points=3000)
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

    official_corners = _validated_circuit_corners(circuit_corners, tel1)
    corner_note = "official numbered corner markers" if official_corners else "estimated speed-dip markers"
    title_text = f"Track Map - {mode_title}<br><sup>{d1_lbl}: {d1_time:.3f}s | {d2_lbl}: {d2_time:.3f}s · sampled locations · {corner_note}</sup>"

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
                # Adjacent colour runs share only their endpoint; retaining that
                # endpoint keeps the circuit continuous without stacking whole
                # mini-sector traces on top of each other.
                sector_data = tel1_s[(tel1_s['MS'] >= group_start) & (tel1_s['MS'] <= ms)]
                if not sector_data.empty:
                    color = c1 if winners[group_start] == driver1 else c2
                    fig.add_trace(go.Scatter(
                        x=sector_data['X'], y=sector_data['Y'], mode='lines',
                        line=dict(color=color, width=6), showlegend=False,
                        hoverinfo='skip'
                    ))
                group_start = ms

        # OpenF1 location traces can finish a few metres before their first
        # sample. Close that tiny start/finish seam so every circuit is drawn
        # continuously. A compact checkered marker identifies the join.
        track_x = tel1_s['X'].to_numpy(dtype=float)
        track_y = tel1_s['Y'].to_numpy(dtype=float)
        if len(track_x) > 2:
            closure = float(np.hypot(track_x[-1] - track_x[0], track_y[-1] - track_y[0]))
            circuit_scale = float(np.hypot(np.ptp(track_x), np.ptp(track_y)))
            # Close only a small seam. Larger gaps may reflect missing location
            # samples and must stay visible instead of being bridged.
            if circuit_scale > 0 and closure <= circuit_scale * 0.03:
                fig.add_trace(go.Scatter(
                    x=[track_x[-1], track_x[0]], y=[track_y[-1], track_y[0]],
                    mode='lines', line=dict(color=c1, width=7),
                    showlegend=False, hoverinfo='skip',
                ))
            dx, dy = track_x[1] - track_x[0], track_y[1] - track_y[0]
            norm = float(np.hypot(dx, dy))
            if norm > 0 and circuit_scale > 0 and closure <= circuit_scale * 0.03:
                # Use small alternating squares across an estimated track-width
                # line; coordinates remain illustrative, like the location data.
                nx, ny = -dy / norm, dx / norm
                extent = max(float(np.ptp(track_x)), float(np.ptp(track_y))) * 0.012
                fig.add_trace(go.Scatter(
                    x=[track_x[0] + nx * extent * t for t in (-1, -0.5, 0, 0.5, 1)],
                    y=[track_y[0] + ny * extent * t for t in (-1, -0.5, 0, 0.5, 1)],
                    mode='markers', marker=dict(
                        color=['#f4f1e8', '#101216', '#f4f1e8', '#101216', '#f4f1e8'],
                        size=7, symbol='square', line=dict(color='#f4f1e8', width=0.5),
                    ), showlegend=False, hoverinfo='skip',
                ))

        if not official_corners:
            for corner in _identify_corners(tel1, tel2):
                winner = driver1 if corner['v1_min'] > corner['v2_min'] else driver2
                color = c1 if winner == driver1 else c2
                fig.add_trace(go.Scatter(
                    x=[corner['x']], y=[corner['y']], mode='markers+text',
                    marker=dict(color=color, size=14, symbol='circle', line=dict(color='white', width=1)),
                    text=[str(corner['id'])], textposition="top center",
                    textfont=dict(size=10, color='white'), name=f"Estimated turn {corner['id']}",
                    showlegend=False,
                    hovertext=(
                        f"Estimated turn {corner['id']} speed dip<br>"
                        f"{driver1}: {int(corner['v1_min'])} km/h<br>"
                        f"{driver2}: {int(corner['v2_min'])} km/h"
                    ),
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

    if official_corners and mode == 'dominance':
        customdata = [row.get('letter') or '' for row in official_corners]
        fig.add_trace(go.Scatter(
            x=[row['x'] for row in official_corners],
            y=[row['y'] for row in official_corners],
            mode='markers+text', text=[str(row['number']) for row in official_corners],
            textposition='middle center', textfont=dict(size=8, color='#101216'),
            customdata=customdata,
            marker=dict(color='#f4f1e8', size=13, symbol='circle', line=dict(color='#101216', width=1.4)),
            name='Official turn', showlegend=False,
            hovertemplate='Turn %{text}%{customdata}<extra></extra>',
        ))

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


def _driver_dna_trace_arrays(telemetry):
    """Return finite distance, position, and speed arrays for corner analysis."""
    required = {'Distance', 'X', 'Y', 'Speed'}
    if telemetry is None or getattr(telemetry, 'empty', True) or not required.issubset(telemetry.columns):
        return None
    arrays = [
        pd.to_numeric(telemetry[column], errors='coerce').to_numpy(dtype=float)
        for column in ('Distance', 'X', 'Y', 'Speed')
    ]
    distance, x, y, speed = arrays
    valid = np.isfinite(distance) & np.isfinite(x) & np.isfinite(y) & np.isfinite(speed)
    if valid.sum() < 20:
        return None
    distance, x, y, speed = (values[valid] for values in arrays)
    order = np.argsort(distance, kind='stable')
    distance, x, y, speed = (values[order] for values in (distance, x, y, speed))
    unique = np.concatenate(([True], np.diff(distance) > 1e-6))
    distance, x, y, speed = (values[unique] for values in (distance, x, y, speed))
    if len(distance) < 20 or distance[-1] <= distance[0]:
        return None
    return distance, x, y, speed


def _circuit_corner_apex_speeds(telemetry, circuit_corners):
    """Measure local apex speeds at mapped corners that align with the lap trace."""
    arrays = _driver_dna_trace_arrays(telemetry)
    corners = _validated_circuit_corners(circuit_corners, telemetry)
    if arrays is None or not corners:
        return {}
    distance, x, y, speed = arrays
    track_span = max(float(np.ptp(x)), float(np.ptp(y)), 1.0)
    snap_limit = max(45.0, track_span * 0.02)
    apex_speeds = {}
    for corner in corners:
        offsets = np.hypot(x - corner['x'], y - corner['y'])
        nearest = int(np.argmin(offsets))
        if offsets[nearest] > snap_limit:
            continue
        # Circuit points mark the turn location, not always its exact apex.
        # Use a short derived-distance window to cover sparse position samples.
        window = np.abs(distance - distance[nearest]) <= 35.0
        local_speed = speed[window]
        if len(local_speed):
            key = (corner['number'], str(corner.get('letter') or ''))
            apex_speeds[key] = float(np.min(local_speed))
    return apex_speeds


def _estimated_corner_progresses(telemetry):
    """Estimate turn apex progress from smoothed path curvature when maps are absent."""
    arrays = _driver_dna_trace_arrays(telemetry)
    if arrays is None:
        return []
    distance, x, y, _ = arrays
    start, end = float(distance[0]), float(distance[-1])
    total = end - start
    step = 10.0
    if total < 500.0:
        return []
    grid = np.arange(start + 60.0, end - 60.0, step)
    if len(grid) < 30:
        return []
    x_grid, y_grid = np.interp(grid, distance, x), np.interp(grid, distance, y)
    # Position samples are noisy. Smooth a short distance window before looking
    # for sustained direction changes; this does not depend on absolute origin.
    kernel = np.ones(5, dtype=float) / 5.0
    x_smooth = np.convolve(x_grid, kernel, mode='same')
    y_smooth = np.convolve(y_grid, kernel, mode='same')
    half_window = 5
    centers = np.arange(half_window, len(grid) - half_window)
    before_x = x_smooth[centers] - x_smooth[centers - half_window]
    before_y = y_smooth[centers] - y_smooth[centers - half_window]
    after_x = x_smooth[centers + half_window] - x_smooth[centers]
    after_y = y_smooth[centers + half_window] - y_smooth[centers]
    cross = before_x * after_y - before_y * after_x
    dot = before_x * after_x + before_y * after_y
    turn_angle = np.abs(np.arctan2(cross, dot))
    turning = np.flatnonzero(turn_angle >= 0.18)
    if not len(turning):
        return []

    # Join nearby curvature peaks into one turn, then keep the strongest point
    # in each group as the estimated apex location.
    groups = [[int(turning[0])]]
    for index in turning[1:]:
        index = int(index)
        previous = groups[-1][-1]
        if grid[centers[index]] - grid[centers[previous]] <= 90.0:
            groups[-1].append(index)
        else:
            groups.append([index])
    progresses = []
    last_distance = -np.inf
    for group in groups:
        strongest = max(group, key=lambda index: turn_angle[index])
        apex_distance = float(grid[centers[strongest]])
        if apex_distance - last_distance < 100.0:
            continue
        progresses.append((apex_distance - start) / total)
        last_distance = apex_distance
    return progresses


def _estimated_apex_speeds(telemetry, progresses):
    arrays = _driver_dna_trace_arrays(telemetry)
    if arrays is None or not progresses:
        return []
    distance, _, _, speed = arrays
    total = float(distance[-1] - distance[0])
    radius = max(30.0, total * 0.008)
    apex_speeds = []
    for progress in progresses:
        center = distance[0] + float(progress) * total
        local_speed = speed[np.abs(distance - center) <= radius]
        if len(local_speed):
            apex_speeds.append(float(np.min(local_speed)))
    return apex_speeds


def _driver_dna_corner_speeds(tel1, tel2, circuit_corners=None):
    """Return comparable mean apex speeds, preferring aligned mapped turns."""
    mapped1 = _circuit_corner_apex_speeds(tel1, circuit_corners)
    mapped2 = _circuit_corner_apex_speeds(tel2, circuit_corners)
    common_corners = sorted(set(mapped1).intersection(mapped2))
    if len(common_corners) >= 4:
        return (
            float(np.mean([mapped1[number] for number in common_corners])),
            float(np.mean([mapped2[number] for number in common_corners])),
        )

    # Circuit turn coordinates are optional. Derive candidate apex locations
    # from both traces' path curvature and compare the same lap-progress points.
    estimated = sorted(_estimated_corner_progresses(tel1) + _estimated_corner_progresses(tel2))
    progress_groups = []
    for progress in estimated:
        if not progress_groups or progress - np.mean(progress_groups[-1]) > 0.025:
            progress_groups.append([progress])
        else:
            progress_groups[-1].append(progress)
    progresses = [float(np.mean(group)) for group in progress_groups]
    speeds1 = _estimated_apex_speeds(tel1, progresses)
    speeds2 = _estimated_apex_speeds(tel2, progresses)
    if len(speeds1) < 4 or len(speeds2) < 4:
        return np.nan, np.nan
    return float(np.mean(speeds1)), float(np.mean(speeds2))


def _compute_driver_dna_raw(tel, *, corner_speed=None):
    """Return raw Driver DNA metrics using the same source data as the radar chart."""
    if tel is None or getattr(tel, 'empty', False):
        return [0.0] * len(DNA_CATEGORY_LABELS)
        
    required = ['Speed', 'Brake', 'Throttle', 'nGear']
    if not all(col in tel.columns for col in required):
        return [0.0] * len(DNA_CATEGORY_LABELS)

    if corner_speed is None:
        progresses = _estimated_corner_progresses(tel)
        corner_speeds = _estimated_apex_speeds(tel, progresses)
        corner_speed = float(np.mean(corner_speeds)) if len(corner_speeds) >= 4 else np.nan
    throttle = tel['Throttle'].to_numpy(dtype=float)
    throttle_smooth = np.clip(np.diff(throttle, prepend=throttle[0]), 0, None)
    gear_counts = tel['nGear'].value_counts(normalize=True, dropna=True)
    gear_entropy = float(-(gear_counts * np.log2(gear_counts)).sum()) if not gear_counts.empty else 0.0
    computed = {
        'Top Speed (km/h)': float(tel['Speed'].max()),
        'Mean Corner Apex Speed (km/h)': float(corner_speed),
        'Full Throttle (%)': float((tel['Throttle'] >= 99).mean() * 100.0),
        'Throttle Ramp (p90 Δ)': float(np.percentile(throttle_smooth, 90)),
        'Brake Usage (%)': float((tel['Brake'] > 0.05).mean() * 100.0),
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
        if not np.isfinite(a) or not np.isfinite(b):
            norm1.append(50.0)
            norm2.append(50.0)
            continue
        scale = max(abs(a), abs(b), 1.0)
        rel = (a - b) / scale
        if abs(a - b) <= 0.005 * scale:
            d = 0.0
        else:
            d = float(np.tanh(rel / k))
        norm1.append(50.0 + amp * d)
        norm2.append(50.0 - amp * d)
    return norm1, norm2


def _compute_driver_dna_summary(tel1, tel2, circuit_corners=None):
    """Return legend, raw values, and normalized chart values for Driver DNA."""
    corner_speed1, corner_speed2 = _driver_dna_corner_speeds(tel1, tel2, circuit_corners)
    raw1 = _compute_driver_dna_raw(tel1, corner_speed=corner_speed1)
    raw2 = _compute_driver_dna_raw(tel2, corner_speed=corner_speed2)
    norm1, norm2 = _normalize_driver_dna(raw1, raw2)
    return _driver_dna_legend(), raw1, raw2, norm1, norm2


def _build_driver_radar(driver1, driver2, c1, c2, tel1, tel2, circuit_corners=None):
    """Computes and builds a normalized Driver DNA radar chart.

    Returns:
        (fig, legend_map): Plotly figure + list of (letter, long_label) tuples for UI legend.
    """
    legend_map, _, _, norm1, norm2 = _compute_driver_dna_summary(tel1, tel2, circuit_corners)
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
            radialaxis=dict(visible=True, range=[0, 100], tickfont=dict(size=13), gridcolor='#333'),
            angularaxis=dict(tickfont=dict(size=19)),
            bgcolor='rgba(0,0,0,0)'
        ),
        showlegend=True,
        legend=dict(orientation='h', yanchor='bottom', y=1.08, xanchor='center', x=0.5, font=dict(size=15)),
        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
        margin=dict(l=32, r=32, t=40, b=18),
        autosize=True,
        template='plotly_dark'
    )
    return fig, legend_map
