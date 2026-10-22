"""Shared Plotly configuration and graph helper utilities."""


def _collapse_lap_ranges(laps):
    if not laps:
        return []
    ordered = sorted(int(l) for l in laps)
    ranges = []
    start = ordered[0]
    prev = ordered[0]
    for lap in ordered[1:]:
        if lap == prev + 1:
            prev = lap
            continue
        ranges.append((start, prev))
        start = lap
        prev = lap
    ranges.append((start, prev))
    return ranges


COMPOUND_COLORS = {
    'SOFT': '#ff3333', 'MEDIUM': '#ffff00', 'HARD': '#ffffff',
    'INTERMEDIATE': '#00ff00', 'WET': '#0099ff'
}

def _error_figure(message):
    import plotly.graph_objects as go
    from ui_utils import _apply_base_layout

    fig = go.Figure()
    _apply_base_layout(fig)
    fig.add_annotation(text=f"Error: {message}", showarrow=False,
                       font=dict(size=14, color='#ff4444'),
                       xref="paper", yref="paper", x=0.5, y=0.5)
    return fig


def _not_applicable_figure(message):
    import plotly.graph_objects as go
    from ui_utils import _apply_base_layout

    fig = go.Figure()
    _apply_base_layout(fig)
    fig.update_xaxes(visible=False).update_yaxes(visible=False)
    fig.add_annotation(text=message, showarrow=False,
                       font=dict(size=15, color='#888'),
                       xref="paper", yref="paper", x=0.5, y=0.5)
    return fig


def _sort_fastest_driver(d1, tel1, c1, lap1, d2, tel2, c2, lap2, lbl1, lbl2):
    t1 = float(lap1['lap_duration'])
    t2 = float(lap2['lap_duration'])
    data1 = (d1, tel1, c1, t1, lap1, lbl1)
    data2 = (d2, tel2, c2, t2, lap2, lbl2)
    return (data1, data2) if t1 <= t2 else (data2, data1)


def _telemetry_delta_fallback(reference_tel, compare_tel):
    """Compute an approximate delta by aligning sampled traces on lap progress."""
    import numpy as np
    import pandas as pd

    def _prepare(telemetry):
        if telemetry is None or telemetry.empty or not {'Distance', 'Time'}.issubset(telemetry.columns):
            raise ValueError("No usable distance/time trace is available for delta calculation.")
        frame = telemetry.loc[:, ['Distance', 'Time']].copy()
        frame['Distance'] = pd.to_numeric(frame['Distance'], errors='coerce')
        frame['TimeSeconds'] = pd.to_timedelta(frame['Time'], errors='coerce').dt.total_seconds()
        frame = frame.replace([np.inf, -np.inf], np.nan).dropna().sort_values('Distance')
        frame = frame.drop_duplicates('Distance', keep='first')
        if len(frame) < 6 or frame['Distance'].iloc[-1] <= frame['Distance'].iloc[0]:
            raise ValueError("Distance/time trace is too short for delta calculation.")
        frame['Distance'] -= frame['Distance'].iloc[0]
        frame['TimeSeconds'] -= frame['TimeSeconds'].iloc[0]
        return frame

    ref = _prepare(reference_tel)
    comp = _prepare(compare_tel)
    points = min(1800, max(160, min(len(ref), len(comp))))
    progress = np.linspace(0.0, 1.0, points)
    ref_distance = ref['Distance'].to_numpy(dtype=float)
    comp_distance = comp['Distance'].to_numpy(dtype=float)
    ref_time = np.interp(progress, ref_distance / ref_distance[-1], ref['TimeSeconds'].to_numpy(dtype=float))
    comp_time = np.interp(progress, comp_distance / comp_distance[-1], comp['TimeSeconds'].to_numpy(dtype=float))
    ref_out = pd.DataFrame({'Distance': progress * ref_distance[-1]})
    comp_out = pd.DataFrame({'Distance': progress * comp_distance[-1]})
    return comp_time - ref_time, ref_out, comp_out


def _compute_lap_delta(reference_lap, compare_lap, reference_tel=None, compare_tel=None):
    """Return a distance-aligned delta from the normalized selected traces."""
    if reference_tel is None or compare_tel is None:
        raise ValueError("Both normalized traces are required for lap delta.")
    return _telemetry_delta_fallback(reference_tel, compare_tel)
