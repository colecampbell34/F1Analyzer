"""Telemetry graph builders."""
import numpy as np
import pandas as pd
import plotly.graph_objects as go

from graph_shared import _compute_lap_delta
from graphs_common import _add_driver_legend_entries
from ui_utils import _apply_base_layout, _downsample


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
