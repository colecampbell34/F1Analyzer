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
    t1 = lap1['LapTime'].total_seconds()
    t2 = lap2['LapTime'].total_seconds()
    data1 = (d1, tel1, c1, t1, lap1, lbl1)
    data2 = (d2, tel2, c2, t2, lap2, lbl2)
    return (data1, data2) if t1 <= t2 else (data2, data1)


def _compute_lap_delta(reference_lap, compare_lap):
    import fastf1.utils
    delta_time, ref_tel, comp_tel = fastf1.utils.delta_time(reference_lap, compare_lap)

    if not ref_tel.empty:
        ref_tel = ref_tel.copy()
        ref_tel['Distance'] -= ref_tel['Distance'].min()
    if not comp_tel.empty:
        comp_tel = comp_tel.copy()
        comp_tel['Distance'] -= comp_tel['Distance'].min()

    return delta_time, ref_tel, comp_tel
