from data import get_pit_stop_data, get_track_status_events, get_best_lap, get_single_driver_color


def _downsample(df, max_points=2000):
    """Downsample a DataFrame to max_points rows via even spacing. Visually identical at chart resolution."""
    import pandas as pd
    if len(df) <= max_points:
        return df
    step = max(1, len(df) // max_points)
    return df.iloc[::step].reset_index(drop=True)

# Shared tyre compound color map
COMPOUND_COLORS = {
    'SOFT': '#ff3333', 'MEDIUM': '#ffff00', 'HARD': '#ffffff',
    'INTERMEDIATE': '#00ff00', 'WET': '#0099ff'
}

GRAPH_CONFIG = {
    'displayModeBar': True,
    'toImageButtonOptions': {'format': 'png', 'height': 900, 'width': 1600, 'filename': 'f1_analysis'},
    'modeBarButtonsToAdd': ['toImage'],
}

BASE_LAYOUT = dict(
    template='plotly_dark',
    margin=dict(l=40, r=40, t=60, b=40),
    hovermode='x unified'
)

def _apply_base_layout(fig, **kwargs):
    """Applies the base F1 analyzer layout, allowing kwargs to override specifics."""
    fig.update_layout(**BASE_LAYOUT)
    fig.update_layout(**kwargs)
    return fig


def _error_figure(message):
    """Creates a standard dark-themed error annotation figure."""
    import plotly.graph_objects as go
    fig = go.Figure()
    _apply_base_layout(fig)
    fig.add_annotation(text=f"Error: {message}", showarrow=False,
                       font=dict(size=14, color='#ff4444'),
                       xref="paper", yref="paper", x=0.5, y=0.5)
    return fig


def _not_applicable_figure(message):
    """Creates a standard dark-themed 'N/A' placeholder figure."""
    import plotly.graph_objects as go
    fig = go.Figure()
    _apply_base_layout(fig)
    fig.update_xaxes(visible=False).update_yaxes(visible=False)
    fig.add_annotation(text=message, showarrow=False,
                       font=dict(size=15, color='#888'),
                       xref="paper", yref="paper", x=0.5, y=0.5)
    return fig


def _get_driver_colors(driver1, driver2, session):
    """Fetches driver colors and handles teammate color collisions."""
    import fastf1.plotting
    try:
        c1 = fastf1.plotting.get_driver_color(driver1, session)
        c2 = fastf1.plotting.get_driver_color(driver2, session)
    except (KeyError, ValueError):
        c1, c2 = '#00ffff', '#ff00ff'

    if not c1.startswith('#'): c1 = f"#{c1}"
    if not c2.startswith('#'): c2 = f"#{c2}"
    if c1.lower() == c2.lower():
        c2 = '#ffffff' if c1.lower() != '#ffffff' else '#ffff00'

    return c1, c2


def _sort_fastest_driver(d1, tel1, c1, lap1, d2, tel2, c2, lap2, lbl1, lbl2):
    """Compares lap times and returns (fast_data, slow_data) tuples to standardize plotting."""
    t1 = lap1['LapTime'].total_seconds()
    t2 = lap2['LapTime'].total_seconds()

    data1 = (d1, tel1, c1, t1, lap1, lbl1)
    data2 = (d2, tel2, c2, t2, lap2, lbl2)

    return (data1, data2) if t1 <= t2 else (data2, data1)


def _build_telemetry_fig(fast_data, slow_data):
    """Builds the 4-Row Telemetry Subplot (Delta, Speed, Throttle/Brake, Gear)."""
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    fast_driver, fast_tel, fast_c, fast_t, fast_lap, fast_lbl = fast_data
    slow_driver, slow_tel, slow_c, slow_t, slow_lap, slow_lbl = slow_data

    import fastf1.utils
    delta_time, ref_tel, comp_tel = fastf1.utils.delta_time(fast_lap, slow_lap)

    fast_tel = _downsample(fast_tel)
    slow_tel = _downsample(slow_tel)

    fig = make_subplots(
        rows=4, cols=1, shared_xaxes=True, vertical_spacing=0.03,
        specs=[[{"secondary_y": False}], [{"secondary_y": False}], [{"secondary_y": True}], [{"secondary_y": False}]],
        row_heights=[0.15, 0.35, 0.25, 0.25]
    )

    # Row 1: Time Delta
    fig.add_trace(
        go.Scatter(x=ref_tel['Distance'], y=delta_time, mode='lines', name="Time Delta", line=dict(color='white')),
        row=1, col=1)
    fig.add_annotation(xref="paper", yref="y domain", x=0.94, y=1, text=f"{fast_driver} faster", showarrow=False,
                       xanchor="left")
    fig.add_annotation(xref="paper", yref="y domain", x=0.94, y=0, text=f"{slow_driver} faster", showarrow=False,
                       xanchor="left")

    # Row 2: Speed
    fig.add_trace(go.Scatter(x=fast_tel['Distance'], y=fast_tel['Speed'], mode='lines', name=f'{fast_driver} Speed',
                             line=dict(color=fast_c)), row=2, col=1)
    fig.add_trace(go.Scatter(x=slow_tel['Distance'], y=slow_tel['Speed'], mode='lines', name=f'{slow_driver} Speed',
                             line=dict(color=slow_c)), row=2, col=1)

    # Row 3: Throttle and Brake
    fig.add_trace(
        go.Scatter(x=fast_tel['Distance'], y=fast_tel['Throttle'], mode='lines', name=f'{fast_driver} Throttle',
                   line=dict(color=fast_c, dash='solid')), row=3, col=1, secondary_y=False)
    fig.add_trace(
        go.Scatter(x=slow_tel['Distance'], y=slow_tel['Throttle'], mode='lines', name=f'{slow_driver} Throttle',
                   line=dict(color=slow_c, dash='solid')), row=3, col=1, secondary_y=False)
    fig.add_trace(go.Scatter(x=fast_tel['Distance'], y=fast_tel['Brake'], mode='lines', name=f'{fast_driver} Brake',
                             line=dict(color=fast_c, dash='dot'), opacity=0.7), row=3, col=1, secondary_y=True)
    fig.add_trace(go.Scatter(x=slow_tel['Distance'], y=slow_tel['Brake'], mode='lines', name=f'{slow_driver} Brake',
                             line=dict(color=slow_c, dash='dot'), opacity=0.7), row=3, col=1, secondary_y=True)

    # Row 4: Gear
    fig.add_trace(go.Scatter(x=fast_tel['Distance'], y=fast_tel['nGear'], mode='lines', name=f'{fast_driver} Gear',
                             line=dict(color=fast_c)), row=4, col=1)
    fig.add_trace(go.Scatter(x=slow_tel['Distance'], y=slow_tel['nGear'], mode='lines', name=f'{slow_driver} Gear',
                             line=dict(color=slow_c)), row=4, col=1)

    _apply_base_layout(
        fig,
        title=f'Telemetry Traces: {fast_lbl} ({fast_t:.3f}s) vs {slow_lbl} ({slow_t:.3f}s)',
        margin=dict(l=40, r=40, t=80, b=40),
        legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="center", x=0.5),
        uirevision='telemetry'
    )

    fig.update_yaxes(title_text="Delta (s)", row=1, col=1)
    fig.update_yaxes(title_text="Speed (km/h)", row=2, col=1)
    fig.update_yaxes(title_text="Throttle (%)", row=3, col=1, secondary_y=False)
    fig.update_yaxes(title_text="Brake", row=3, col=1, secondary_y=True, showgrid=False)
    fig.update_yaxes(title_text="Gear", row=4, col=1, tickvals=[1, 2, 3, 4, 5, 6, 7, 8])
    fig.update_xaxes(title_text="Distance along track (meters)", row=4, col=1)

    return fig


def _build_dominance_fig(driver1, driver2, c1, c2, tel1, tel2, fast_data, slow_data):
    """Builds the 2D Track Dominance Map colored by mini-sectors."""
    import plotly.graph_objects as go
    fast_driver, _, fast_c, fast_t, _, fast_lbl = fast_data
    slow_driver, _, slow_c, slow_t, _, slow_lbl = slow_data

    tel1 = _downsample(tel1, max_points=3000)
    tel2 = _downsample(tel2, max_points=3000)

    num_minisectors = 50
    total_dist = max(tel1['Distance'].max(), tel2['Distance'].max())
    sector_length = total_dist / num_minisectors
    
    tel1 = tel1.copy()
    tel2 = tel2.copy()
    tel1['MiniSector'] = (tel1['Distance'] // sector_length).astype(int).clip(upper=num_minisectors)
    tel2['MiniSector'] = (tel2['Distance'] // sector_length).astype(int).clip(upper=num_minisectors)

    fast_tel = tel1 if fast_driver == driver1 else tel2

    v1_avg = tel1.groupby('MiniSector')['Speed'].mean()
    v2_avg = tel2.groupby('MiniSector')['Speed'].mean()
    winner_list = [driver1 if v1_avg.get(i, 0) > v2_avg.get(i, 0) else driver2 for i in range(num_minisectors + 1)]

    speed_deltas = {}
    for i in range(num_minisectors + 1):
        s1 = v1_avg.get(i, 0)
        s2 = v2_avg.get(i, 0)
        speed_deltas[i] = abs(s1 - s2)

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=[None], y=[None], mode='lines', line=dict(color=fast_c, width=6),
                             name=f'{fast_driver} Faster ({fast_t:.3f}s)'))
    fig.add_trace(go.Scatter(x=[None], y=[None], mode='lines', line=dict(color=slow_c, width=6),
                             name=f'{slow_driver} Faster ({slow_t:.3f}s)'))

    # Group consecutive sectors with the same winner into single traces
    # to dramatically reduce the number of traces (from 50 to typically ~8-12)
    group_start = 0
    for ms in range(1, num_minisectors + 1):
        if ms == num_minisectors or winner_list[ms] != winner_list[group_start]:
            group_end = ms
            sector_data = fast_tel[
                (fast_tel['MiniSector'] >= group_start) & (fast_tel['MiniSector'] <= group_end)
            ]
            if sector_data.empty:
                group_start = ms
                continue

            winner = winner_list[group_start]
            color = c1 if winner == driver1 else c2

            hover_texts = []
            for _, row in sector_data.iterrows():
                sec = int(row['MiniSector'])
                delta_km = speed_deltas.get(sec, 0)
                hover_texts.append(f'Sector {sec+1}<br>{winner} faster by {delta_km:.1f} km/h')

            fig.add_trace(go.Scatter(
                x=sector_data['X'], y=sector_data['Y'], mode='lines',
                line=dict(color=color, width=8), showlegend=False,
                hovertext=hover_texts, hoverinfo='text'
            ))
            group_start = ms

    _apply_base_layout(
        fig,
        title="Track Dominance Map (50 Sectors)",
        hovermode="closest",
        xaxis=dict(visible=False, scaleanchor="y", scaleratio=1), yaxis=dict(visible=False),
        legend=dict(yanchor="top", y=0.99, xanchor="left", x=0.01),
        uirevision='dominance'
    )
    return fig


def _build_strategy_fig(session, driver1, driver2, lbl1, lbl2, c1, c2):
    """Builds the Race Pace, Pits, Tyres & Weather dual-axis strategy plot."""
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    import pandas as pd

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
        for lap in laps:
            fig.add_vrect(x0=lap - 0.5, x1=lap + 0.5, fillcolor=color, opacity=0.15,
                          layer="below", line_width=0, row='all', col='all')
        if laps:
            fig.add_trace(go.Scatter(x=[None], y=[None], mode='markers',
                                     marker=dict(color=color, symbol='square', size=12, opacity=0.5),
                                     name=name, legend='legend'), row=1, col=1)

    # General Legend additions
    for drv, lbl, col in [(driver1, lbl1, c1), (driver2, lbl2, c2)]:
        fig.add_trace(go.Scatter(x=[None], y=[None], mode='lines', name=drv,
                                 line=dict(color=col, width=2), legend='legend'), row=1, col=1)
    for comp in comp_drawn:
        if comp in COMPOUND_COLORS:
            fig.add_trace(go.Scatter(x=[None], y=[None], mode='markers', name=comp,
                                     marker=dict(color=COMPOUND_COLORS[comp], size=10), legend='legend'), row=1, col=1)

    # 6. Weather & Rain Overlay
    weather_data = session.weather_data
    if not weather_data.empty and not session.laps.empty:
        try:
            lap_times = session.laps.dropna(subset=['Time']).groupby('LapNumber')['Time'].median().reset_index()
            lap_times.columns = ['LapNumber', 'Time']
            lap_times = lap_times.sort_values('Time')

            weather_sorted = weather_data.sort_values('Time')
            merged_weather = pd.merge_asof(lap_times, weather_sorted[['Time', 'TrackTemp', 'Rainfall']],
                                           on='Time', direction='nearest')

            fig.add_trace(go.Scatter(
                x=merged_weather['LapNumber'], y=merged_weather['TrackTemp'],
                mode='lines+markers', name='Track Temp (°C)',
                line=dict(color='white', width=2), marker=dict(size=4), showlegend=False
            ), row=2, col=1)

            rain_laps = merged_weather[merged_weather['Rainfall'] == True]['LapNumber'].tolist()
            for lap in rain_laps:
                fig.add_vrect(x0=lap - 0.5, x1=lap + 0.5, fillcolor="blue", opacity=0.2, layer="below",
                              line_width=0, row='all', col='all')
            if rain_laps:
                fig.add_trace(go.Scatter(x=[None], y=[None], mode='markers',
                                         marker=dict(color='blue', opacity=0.5, symbol='square', size=15), name='Rain',
                                         legend='legend'), row=1, col=1)
        except Exception:
            pass

    _apply_base_layout(
        fig,
        title="Strategy & Weather",
        legend=dict(title=dict(text="Legend"), yanchor="top", y=1, xanchor="left", x=1.02, bgcolor="rgba(0,0,0,0)"),
        uirevision='strategy'
    )
    fig.update_xaxes(title_text="Lap Number", row=2, col=1)
    fig.update_yaxes(title_text="Pace (s)", row=1, col=1, autorange="reversed")
    fig.update_yaxes(title_text="Temp (°C)", row=2, col=1)

    return fig


def _build_deg_fig(session, driver1, driver2, lbl1, lbl2, c1, c2):
    """Fuel-corrected tyre degradation analysis per stint, side-by-side."""
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    import numpy as np
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
                    showlegend=True,
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
                        showlegend=True
                    ), row=1, col=col_idx)
        except Exception:
            continue

    _apply_base_layout(
        fig,
        title='Tyre Degradation Analysis (Fuel-Corrected, ~0.06s/lap)<br><sup>+ = more degradation, - = pace improving</sup>',
        margin=dict(l=40, r=40, t=80, b=40),
        uirevision='degradation'
    )
    fig.update_yaxes(title_text='Fuel-Corrected Lap Time (s)', row=1, col=1, autorange='reversed')
    fig.update_xaxes(title_text='Stint Lap', row=1, col=1)
    fig.update_xaxes(title_text='Stint Lap', row=1, col=2)

    return fig


def _build_race_gaps_fig(session, driver1, driver2, lbl1, lbl2, c1, c2):
    """Builds the gap-between-drivers chart over race laps."""
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    import pandas as pd
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
                name=f'{lbl1} Pos', line=dict(color=c1, width=2)
            ), row=2, col=1)

        if 'Pos2' in merged.columns:
            x_vals = merged['LapNumber'].tolist()
            y_vals = merged['Pos2'].astype(float).tolist()
            if grid2 is not None and grid2 > 0:
                x_vals = [0] + x_vals
                y_vals = [float(grid2)] + y_vals

            fig.add_trace(go.Scatter(
                x=x_vals, y=y_vals, mode='lines',
                name=f'{lbl2} Pos', line=dict(color=c2, width=2)
            ), row=2, col=1)

        for drv, color, laps_df in [(driver1, c1, laps1), (driver2, c2, laps2)]:
            pit_laps = laps_df[laps_df['PitInTime'].notna()]['LapNumber'].tolist()
            for pl in pit_laps:
                fig.add_vline(x=pl, line_width=1.5, line_dash="dot", line_color=color, opacity=0.6,
                              row='all', col='all')

        sc_laps, vsc_laps, red_laps = get_track_status_events(session)
        for laps_set, color, name in [(sc_laps, 'orange', 'SC'), (vsc_laps, 'yellow', 'VSC'),
                                       (red_laps, 'red', 'Red Flag')]:
            for lap in laps_set:
                fig.add_vrect(x0=lap - 0.5, x1=lap + 0.5, fillcolor=color, opacity=0.1,
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
    import plotly.graph_objects as go
    import pandas as pd
    from data import is_race, is_qualifying
    fig = go.Figure()
    drivers_data = []

    all_drivers = []
    if getattr(session, 'results', None) is not None and not session.results.empty:
        all_drivers = session.results['Abbreviation'].dropna().tolist()
    else:
        all_drivers = session.laps['Driver'].unique().tolist()

    has_results = getattr(session, 'results', None) is not None and not session.results.empty
    _is_race = is_race(session_type)
    _is_quali = is_qualifying(session_type)

    for drv in all_drivers:
        if not isinstance(drv, str) or len(drv) != 3:
            continue
        try:
            drv_laps = session.laps.pick_drivers(drv)

            if _is_race:
                clean_laps = drv_laps.pick_wo_box().pick_track_status('1')
                laps = clean_laps[clean_laps['LapNumber'] > 1]
            else:
                laps = drv_laps.pick_wo_box()
                if not laps.empty and 'IsAccurate' in laps.columns:
                    laps = laps[laps['IsAccurate']]
                if not laps.empty:
                    fastest_lap_time = laps['LapTime'].dt.total_seconds().min()
                    if pd.notna(fastest_lap_time):
                        laps = laps[laps['LapTime'].dt.total_seconds() <= fastest_lap_time * 1.07]

            lap_times = laps['LapTime'].dt.total_seconds().dropna()
            if lap_times.empty:
                continue

            color = get_single_driver_color(drv, session)

            best_lap = get_best_lap(session, drv)
            best_time = best_lap['LapTime'].total_seconds() if best_lap is not None and pd.notna(
                best_lap['LapTime']) else lap_times.min()

            pos = 999
            if has_results:
                res_row = session.results[session.results['Abbreviation'] == drv]
                if not res_row.empty:
                    pos_val = res_row.iloc[0].get('Position')
                    pos = int(pos_val) if pd.notna(pos_val) else 999

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

    if has_results:
        drivers_data.sort(key=lambda x: (x['position'], x['fastest']))
    else:
        sort_key = 'fastest' if _is_quali else 'median'
        drivers_data.sort(key=lambda x: x[sort_key])

    for d in drivers_data:
        fig.add_trace(go.Box(
            y=d['times'], name=d['driver'],
            marker_color=d['color'], line_color=d['color'],
            boxmean=True,
            hovertemplate=f"{d['driver']}<br>Lap Time: %{{y:.3f}}s<extra></extra>"
        ))

    session_label = "Racing Laps" if _is_race else "Practice Laps" if is_practice_session(
        session_type) else "Qualifying Laps"
    _apply_base_layout(
        fig,
        title=f'Grid Pace Distribution ({session_label}, Sorted by Finishing Position)',
        showlegend=False,
        hovermode='closest',
        yaxis_title='Lap Time (s)',
        yaxis=dict(autorange='reversed'),
        uirevision='gridpace'
    )

    return fig


def is_practice_session(session_type):
    """Helper for grid pace label."""
    return any(p in session_type for p in ['Practice 1', 'Practice 2', 'Practice 3'])


def _build_pit_stops_fig(session, driver1, driver2, lbl1, lbl2, c1, c2):
    """Builds a pit stop duration comparison chart for all drivers."""
    import plotly.graph_objects as go
    import pandas as pd
    pit_data = []
    title = 'Pit Stop Durations (Time spent in pit lane)'
    hover_label = 'Stop Time'

    try:
        pit_stops = get_pit_stop_data(session.event.year, session.event.RoundNumber)
    except Exception:
        pit_stops = pd.DataFrame()

    if pit_stops is not None and not pit_stops.empty:
        for _, stop in pit_stops.iterrows():
            duration = stop.get('duration')
            if pd.isna(duration):
                continue

            duration_seconds = duration.total_seconds()
            if not 0 < duration_seconds < 120:
                continue

            drv = stop.get('driverCode') or str(stop.get('driverId', '')).upper()[:3]
            if not isinstance(drv, str) or len(drv) != 3:
                continue

            color = get_single_driver_color(drv, session)

            pit_data.append({
                'driver': drv,
                'lap': int(stop['lap']),
                'duration': duration_seconds,
                'color': color,
                'highlight': drv in [driver1, driver2]
            })

    if not pit_data:
        title = 'Pit Stop Durations (Pit Lane Time Fallback)'
        hover_label = 'Pit Lane Time'

        all_drivers = []
        if getattr(session, 'results', None) is not None and not session.results.empty:
            all_drivers = [d for d in session.results['Abbreviation'].dropna().tolist()
                           if isinstance(d, str) and len(d) == 3]

        for drv in all_drivers:
            try:
                drv_laps = session.laps.pick_drivers(drv).sort_values('LapNumber')
                pit_in = drv_laps[drv_laps['PitInTime'].notna()]

                for _, pit_lap in pit_in.iterrows():
                    pit_in_time = pit_lap['PitInTime']
                    next_lap_num = pit_lap['LapNumber'] + 1
                    next_lap = drv_laps[drv_laps['LapNumber'] == next_lap_num]

                    if not next_lap.empty and pd.notna(next_lap.iloc[0].get('PitOutTime')):
                        pit_out_time = next_lap.iloc[0]['PitOutTime']
                        duration = (pit_out_time - pit_in_time).total_seconds()
                        if 10 < duration < 120:
                            color = get_single_driver_color(drv, session)

                            pit_data.append({
                                'driver': drv,
                                'lap': int(pit_lap['LapNumber']),
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
