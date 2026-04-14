import plotly.graph_objects as go
from plotly.subplots import make_subplots
import fastf1
import fastf1.plotting
import fastf1.utils
import pandas as pd
import numpy as np
from data import get_pit_stop_data, get_track_status_events, get_best_lap


def _downsample(df, max_points=2000):
    """Downsample a DataFrame to max_points rows via even spacing. Visually identical at chart resolution."""
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


def _get_driver_colors(driver1, driver2, session):
    """Fetches driver colors and handles teammate color collisions."""
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
    fast_driver, fast_tel, fast_c, fast_t, fast_lap, fast_lbl = fast_data
    slow_driver, slow_tel, slow_c, slow_t, slow_lap, slow_lbl = slow_data

    delta_time, ref_tel, comp_tel = fastf1.utils.delta_time(fast_lap, slow_lap)

    # Downsample for faster transfer over Replit bandwidth
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

    fig.update_layout(
        title=f'Telemetry Traces: {fast_lbl} ({fast_t:.3f}s) vs {slow_lbl} ({slow_t:.3f}s)',
        template='plotly_dark', hovermode='x unified', margin=dict(l=40, r=40, t=80, b=40),
        legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="center", x=0.5),
        uirevision='telemetry'
    )

    fig.update_yaxes(title_text="Delta (s)", row=1, col=1)
    fig.update_yaxes(title_text="Speed (km/h)", row=2, col=1)
    fig.update_yaxes(title_text="Throttle (%)", row=3, col=1, secondary_y=False)
    fig.update_yaxes(title_text="Brake", row=3, col=1, secondary_y=True, showgrid=False,
                     categoryorder='array', categoryarray=[False, True])
    fig.update_yaxes(title_text="Gear", row=4, col=1, tickvals=[1, 2, 3, 4, 5, 6, 7, 8])
    fig.update_xaxes(title_text="Distance along track (meters)", row=4, col=1)

    return fig


def _build_dominance_fig(driver1, driver2, c1, c2, tel1, tel2, fast_data, slow_data):
    """Builds the 2D Track Dominance Map colored by mini-sectors (50 sectors for high resolution)."""
    fast_driver, _, fast_c, fast_t, _, fast_lbl = fast_data
    slow_driver, _, slow_c, slow_t, _, slow_lbl = slow_data

    num_minisectors = 50
    total_dist = max(tel1['Distance'].max(), tel2['Distance'].max())
    sector_length = total_dist / num_minisectors
    
    tel1 = tel1.copy()
    tel2 = tel2.copy()
    tel1['MiniSector'] = (tel1['Distance'] // sector_length).astype(int).clip(upper=num_minisectors)
    tel2['MiniSector'] = (tel2['Distance'] // sector_length).astype(int).clip(upper=num_minisectors)

    # Use the local copied tel DataFrames which contain 'MiniSector'
    fast_tel = tel1 if fast_driver == driver1 else tel2
    slow_tel = tel2 if fast_driver == driver1 else tel1

    v1_avg = tel1.groupby('MiniSector')['Speed'].mean()
    v2_avg = tel2.groupby('MiniSector')['Speed'].mean()
    winner_list = [driver1 if v1_avg.get(i, 0) > v2_avg.get(i, 0) else driver2 for i in range(num_minisectors + 1)]

    # Compute speed deltas per sector for hover tooltips
    speed_deltas = {}
    for i in range(num_minisectors + 1):
        s1 = v1_avg.get(i, 0)
        s2 = v2_avg.get(i, 0)
        speed_deltas[i] = abs(s1 - s2)

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=[None], y=[None], mode='lines', line=dict(color=fast_c, width=6),
                             name=f'{fast_lbl} Faster ({fast_t:.3f}s)'))
    fig.add_trace(go.Scatter(x=[None], y=[None], mode='lines', line=dict(color=slow_c, width=6),
                             name=f'{slow_lbl} Faster ({slow_t:.3f}s)'))

    for ms in range(num_minisectors):
        sector_data = fast_tel[fast_tel['MiniSector'] == ms]
        if sector_data.empty:
            continue

        next_sector = fast_tel[fast_tel['MiniSector'] == ms + 1]
        if not next_sector.empty:
            sector_data = pd.concat([sector_data, next_sector.iloc[[0]]])

        winner = winner_list[ms]
        color = c1 if winner == driver1 else c2
        delta_km = speed_deltas.get(ms, 0)

        fig.add_trace(go.Scatter(
            x=sector_data['X'], y=sector_data['Y'], mode='lines',
            line=dict(color=color, width=8), showlegend=False,
            hovertemplate=f'Sector {ms+1}<br>{winner} faster by {delta_km:.1f} km/h<extra></extra>'
        ))

    fig.update_layout(
        title="High-Resolution Track Dominance Map (50 Sectors)", template='plotly_dark',
        xaxis=dict(visible=False, scaleanchor="y", scaleratio=1), yaxis=dict(visible=False),
        margin=dict(l=40, r=40, t=60, b=40), legend=dict(yanchor="top", y=0.99, xanchor="left", x=0.01),
        uirevision='dominance'
    )
    return fig


def _build_strategy_fig(session, driver1, driver2, lbl1, lbl2, c1, c2):
    """Builds the Race Pace, Pits, Tyres & Weather dual-axis strategy plot."""
    # 1. Fetch unfiltered laps
    unf_1 = session.laps.pick_drivers(driver1).reset_index(drop=True)
    unf_2 = session.laps.pick_drivers(driver2).reset_index(drop=True)

    # 2. Apply Filters (Racing laps only)
    all_laps1 = unf_1.pick_wo_box().pick_track_status('1').loc[unf_1['LapNumber'] > 1].reset_index(drop=True)
    all_laps2 = unf_2.pick_wo_box().pick_track_status('1').loc[unf_2['LapNumber'] > 1].reset_index(drop=True)

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
            max_stint = lap_data['Stint'].max()

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

                if stint < max_stint:
                    last_lap = stint_subset['LapNumber'].max()
                    fig.add_vline(x=last_lap, line_width=1.5, line_dash="dot", line_color=col, opacity=0.6,
                                  row='all', col='all')

    # 5. Overlay SC/VSC/Red Flag lines
    sc_laps, vsc_laps, red_laps = get_track_status_events(session)

    lines = [(sc_laps, 'orange', 'SC / YF'), (vsc_laps, 'yellow', 'VSC'), (red_laps, 'red', 'Red Flag')]
    for laps, color, name in lines:
        for lap in laps:
            fig.add_vline(x=lap, line_width=2, line_dash="dash", line_color=color, opacity=0.5, row='all', col='all')
        if laps:
            fig.add_trace(go.Scatter(x=[None], y=[None], mode='lines', line=dict(color=color, dash='dash', width=2),
                                     name=name, legend='legend'), row=1, col=1)

    # General Legend additions
    for drv, lbl, col in [(driver1, lbl1, c1), (driver2, lbl2, c2)]:
        fig.add_trace(go.Scatter(x=[None], y=[None], mode='lines', name=lbl,
                                 line=dict(color=col, width=2), legend='legend'), row=1, col=1)
    for comp in comp_drawn:
        if comp in COMPOUND_COLORS:
            fig.add_trace(go.Scatter(x=[None], y=[None], mode='markers', name=comp,
                                     marker=dict(color=COMPOUND_COLORS[comp], size=10), legend='legend'), row=1, col=1)

    # 6. Weather & Rain Overlay
    weather_data = session.weather_data
    if not weather_data.empty and not session.laps.empty:
        track_temps, lap_nums, rain_laps = [], [], set()
        lap_times = session.laps.dropna(subset=['Time']).groupby('LapNumber')['Time'].median()

        for lap_num, lap_time in lap_times.items():
            idx = (weather_data['Time'] - lap_time).abs().idxmin()
            track_temps.append(weather_data.loc[idx, 'TrackTemp'])
            lap_nums.append(lap_num)
            if weather_data.loc[idx, 'Rainfall']:
                rain_laps.add(lap_num)

        fig.add_trace(go.Scatter(
            x=lap_nums, y=track_temps, mode='lines+markers', name='Track Temp (°C)',
            line=dict(color='white', width=2), marker=dict(size=4), showlegend=False
        ), row=2, col=1)

        for lap in rain_laps:
            fig.add_vrect(x0=lap - 0.5, x1=lap + 0.5, fillcolor="blue", opacity=0.2, layer="below", line_width=0,
                          row='all', col='all')
        if rain_laps:
            fig.add_trace(go.Scatter(x=[None], y=[None], mode='markers',
                                     marker=dict(color='blue', opacity=0.5, symbol='square', size=15), name='Rain',
                                     legend='legend'), row=1, col=1)

    fig.update_layout(
        title="Strategy & Weather", template='plotly_dark', hovermode='x unified',
        margin=dict(l=40, r=40, t=60, b=40),
        legend=dict(title=dict(text="Legend"), yanchor="top", y=1, xanchor="left", x=1.02, bgcolor="rgba(0,0,0,0)"),
        uirevision='strategy'
    )
    fig.update_xaxes(title_text="Lap Number", row=2, col=1)
    fig.update_yaxes(title_text="Pace (s)", row=1, col=1, autorange="reversed")
    fig.update_yaxes(title_text="Temp (°C)", row=2, col=1)

    return fig


# ===========================
# NEW CHART FUNCTIONS
# ===========================

def _build_deg_fig(session, driver1, driver2, lbl1, lbl2, c1, c2):
    """Fuel-corrected tyre degradation analysis per stint, side-by-side."""
    FUEL_CORRECTION = 0.06  # approx seconds saved per lap from fuel burn

    fig = make_subplots(rows=1, cols=2, shared_yaxes=True, subplot_titles=(lbl1, lbl2),
                        horizontal_spacing=0.05)

    for col_idx, (drv, lbl, color) in enumerate([(driver1, lbl1, c1), (driver2, lbl2, c2)], 1):
        try:
            all_laps = session.laps.pick_drivers(drv).reset_index(drop=True)
            racing_laps = all_laps.pick_wo_box().pick_track_status('1')
            racing_laps = racing_laps[racing_laps['LapNumber'] > 1].reset_index(drop=True)
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

                # Fuel correction: add time back to account for lighter car
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

                # Add regression line for deg rate
                if len(stint_data) >= 3:
                    slope, intercept = np.polyfit(
                        stint_data['StintLap'].values.astype(float),
                        stint_data['CorrectedTime'].values, 1)
                    x_fit = [stint_data['StintLap'].min(), stint_data['StintLap'].max()]
                    y_fit = [slope * x + intercept for x in x_fit]
                    fig.add_trace(go.Scatter(
                        x=x_fit, y=y_fit, mode='lines',
                        line=dict(dash='dash', color=marker_color, width=2),
                        name=f'{drv} {comp} [{slope:+.3f}s/lap]',
                        showlegend=True
                    ), row=1, col=col_idx)
        except Exception:
            continue

    fig.update_layout(
        title='Tyre Degradation Analysis (Fuel-Corrected, ~0.06s/lap)<br><sup>+ = more degradation, - = pace improving</sup>',
        template='plotly_dark', margin=dict(l=40, r=40, t=80, b=40),
        hovermode='x unified', uirevision='degradation'
    )
    fig.update_yaxes(title_text='Fuel-Corrected Lap Time (s)', row=1, col=1, autorange='reversed')
    fig.update_xaxes(title_text='Stint Lap', row=1, col=1)
    fig.update_xaxes(title_text='Stint Lap', row=1, col=2)

    return fig


def _build_race_gaps_fig(session, driver1, driver2, lbl1, lbl2, c1, c2):
    """Builds the gap-between-drivers chart over race laps."""
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

        # Gap: negative = driver1 ahead, positive = driver2 ahead
        merged['Gap'] = (merged['Time1'] - merged['Time2']).dt.total_seconds()

        # Color the gap fill
        fig.add_trace(go.Scatter(
            x=merged['LapNumber'], y=merged['Gap'], mode='lines',
            fill='tozeroy', line=dict(color='white', width=2),
            fillcolor='rgba(255,255,255,0.1)',
            name='Gap',
            hovertemplate='Lap %{x}<br>Gap: %{y:.3f}s<extra></extra>'
        ), row=1, col=1)

        # Zero line
        fig.add_hline(y=0, line_dash="dash", line_color="grey", opacity=0.5, row=1, col=1)

        # Annotations for who's ahead
        fig.add_annotation(xref="paper", yref="y domain", x=1.02, y=0.95,
                           text=f"↑ {driver2} ahead", showarrow=False, font=dict(size=11, color=c2),
                           xanchor="left", row=1, col=1)
        fig.add_annotation(xref="paper", yref="y domain", x=1.02, y=0.05,
                           text=f"↓ {driver1} ahead", showarrow=False, font=dict(size=11, color=c1),
                           xanchor="left", row=1, col=1)

        # Position traces (Row 2)
        if 'Pos1' in merged.columns:
            fig.add_trace(go.Scatter(
                x=merged['LapNumber'], y=merged['Pos1'].astype(float), mode='lines',
                name=f'{lbl1} Pos', line=dict(color=c1, width=2)
            ), row=2, col=1)
        if 'Pos2' in merged.columns:
            fig.add_trace(go.Scatter(
                x=merged['LapNumber'], y=merged['Pos2'].astype(float), mode='lines',
                name=f'{lbl2} Pos', line=dict(color=c2, width=2)
            ), row=2, col=1)

        # Pit stop markers
        for drv, color, laps_df in [(driver1, c1, laps1), (driver2, c2, laps2)]:
            pit_laps = laps_df[laps_df['PitInTime'].notna()]['LapNumber'].tolist()
            for pl in pit_laps:
                fig.add_vline(x=pl, line_width=1.5, line_dash="dot", line_color=color, opacity=0.6,
                              row='all', col='all')

        # SC/VSC/Red shading
        sc_laps, vsc_laps, red_laps = get_track_status_events(session)
        for laps_set, color, name in [(sc_laps, 'orange', 'SC'), (vsc_laps, 'yellow', 'VSC'),
                                       (red_laps, 'red', 'Red Flag')]:
            for lap in laps_set:
                fig.add_vrect(x0=lap - 0.5, x1=lap + 0.5, fillcolor=color, opacity=0.1,
                              layer="below", line_width=0, row='all', col='all')

    except Exception as e:
        fig.add_annotation(text=f"Race gap data unavailable: {e}", showarrow=False,
                           font=dict(size=16, color='#ff4444'), xref="paper", yref="paper", x=0.5, y=0.5)

    fig.update_layout(
        title='Race Gap & Position Analysis', template='plotly_dark', hovermode='x unified',
        margin=dict(l=40, r=40, t=80, b=40), uirevision='gaps'
    )
    fig.update_yaxes(title_text='Gap (seconds)', row=1, col=1)
    fig.update_yaxes(title_text='Position', row=2, col=1, autorange='reversed',
                     tickvals=list(range(1, 21)))
    fig.update_xaxes(title_text='Lap Number', row=2, col=1)

    return fig


def _build_grid_pace_fig(session, session_type):
    """Builds a box plot of lap time distributions for all drivers."""
    fig = go.Figure()
    drivers_data = []

    all_drivers = []
    if getattr(session, 'results', None) is not None and not session.results.empty:
        all_drivers = session.results['Abbreviation'].dropna().tolist()
    else:
        all_drivers = session.laps['Driver'].unique().tolist()

    has_results = getattr(session, 'results', None) is not None and not session.results.empty
    is_race = session_type in ['Race', 'Sprint']
    is_quali = any(q in session_type for q in ['Qualifying', 'Shootout'])

    for drv in all_drivers:
        if not isinstance(drv, str) or len(drv) != 3:
            continue
        try:
            drv_laps = session.laps.pick_drivers(drv)

            if is_race:
                laps = drv_laps.pick_wo_box().pick_track_status('1')
                laps = laps[laps['LapNumber'] > 1]
            elif is_quali:
                # Remove in/out laps and ensure we only have flying laps
                laps = drv_laps.pick_wo_box()
                if not laps.empty and 'IsAccurate' in laps.columns:
                    laps = laps[laps['IsAccurate']]
                # Remove outliers (laps slower than 107% of the fastest lap)
                if not laps.empty:
                    fastest_lap_time = laps['LapTime'].dt.total_seconds().min()
                    if pd.notna(fastest_lap_time):
                        laps = laps[laps['LapTime'].dt.total_seconds() <= fastest_lap_time * 1.07]
            else:
                laps = drv_laps

            lap_times = laps['LapTime'].dt.total_seconds().dropna()
            if lap_times.empty:
                continue

            color = '#ffffff'
            try:
                color = fastf1.plotting.get_driver_color(drv, session)
                if not color.startswith('#'):
                    color = f'#{color}'
            except (KeyError, ValueError):
                pass

            best_lap = get_best_lap(session, drv)
            best_time = best_lap['LapTime'].total_seconds() if best_lap is not None and pd.notna(best_lap['LapTime']) else lap_times.min()

            # Get official position
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

    # Sort: Priority 1 = Leaderboard Position, Priority 2 = Performance
    if has_results:
        drivers_data.sort(key=lambda x: x['position'])
    else:
        sort_key = 'fastest' if is_quali else 'median'
        drivers_data.sort(key=lambda x: x[sort_key])

    for d in drivers_data:
        fig.add_trace(go.Box(
            y=d['times'], name=d['driver'],
            marker_color=d['color'], line_color=d['color'],
            boxmean=True,
            hovertemplate=f"{d['driver']}<br>Lap Time: %{{y:.3f}}s<extra></extra>"
        ))

    session_label = "Racing Laps" if session_type in ['Race', 'Sprint'] else "Flying Laps"
    fig.update_layout(
        title=f'Grid Pace Distribution ({session_label}, Sorted by Finishing Position)',
        template='plotly_dark', showlegend=False,
        yaxis_title='Lap Time (s)',
        yaxis=dict(autorange='reversed'),
        margin=dict(l=40, r=40, t=60, b=40),
        uirevision='gridpace'
    )

    return fig


def _build_pit_stops_fig(session, driver1, driver2, lbl1, lbl2, c1, c2):
    """Builds a pit stop duration comparison chart for all drivers."""
    fig = go.Figure()
    pit_data = []
    title = 'Pit Stop Durations (Stationary Time, All Drivers)'
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

            color = '#ffffff'
            try:
                color = fastf1.plotting.get_driver_color(drv, session)
                if not color.startswith('#'):
                    color = f'#{color}'
            except (KeyError, ValueError):
                pass

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
                            color = '#ffffff'
                            try:
                                color = fastf1.plotting.get_driver_color(drv, session)
                                if not color.startswith('#'):
                                    color = f'#{color}'
                            except (KeyError, ValueError):
                                pass

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
        fig.add_annotation(text="No pit stop data available", showarrow=False,
                           font=dict(size=18), xref="paper", yref="paper", x=0.5, y=0.5)
        fig.update_layout(template='plotly_dark')
        return fig

    # Sort by duration
    pit_data.sort(key=lambda x: x['duration'])

    for i, p in enumerate(pit_data):
        border_width = 3 if p['highlight'] else 0
        border_color = 'white' if p['highlight'] else p['color']
        fig.add_trace(go.Bar(
            x=[f"{p['driver']} L{p['lap']}"],
            y=[p['duration']],
            marker_color=p['color'],
            marker_line_width=border_width,
            marker_line_color=border_color,
            text=f"{p['duration']:.1f}s",
            textposition='auto',
            showlegend=False,
            hovertemplate=f"{p['driver']} - Lap {p['lap']}<br>{hover_label}: {p['duration']:.1f}s<extra></extra>"
        ))

    fig.update_layout(
        title=title,
        template='plotly_dark',
        yaxis_title='Duration (s)',
        xaxis_title='Driver & Lap',
        margin=dict(l=40, r=40, t=60, b=80),
        xaxis_tickangle=-45,
        uirevision='pitstops'
    )

    return fig
