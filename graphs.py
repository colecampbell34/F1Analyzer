import plotly.graph_objects as go
from plotly.subplots import make_subplots
import fastf1
import fastf1.plotting
import fastf1.utils
import pandas as pd

def _get_driver_colors(driver1, driver2, session):
    """Fetches driver colors and handles teammate color collisions."""
    try:
        c1 = fastf1.plotting.get_driver_color(driver1, session)
        c2 = fastf1.plotting.get_driver_color(driver2, session)
    except Exception:
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
        legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="center", x=0.5)
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
    """Builds the 2D Track Dominance Map colored by mini-sectors."""
    fast_driver, fast_tel, fast_c, fast_t, _, fast_lbl = fast_data
    slow_driver, _, slow_c, slow_t, _, slow_lbl = slow_data

    num_minisectors = 20
    sector_length = max(tel1['Distance'].max(), tel2['Distance'].max()) / num_minisectors
    tel1['MiniSector'] = (tel1['Distance'] // sector_length).astype(int)
    tel2['MiniSector'] = (tel2['Distance'] // sector_length).astype(int)

    v1_avg = tel1.groupby('MiniSector')['Speed'].mean()
    v2_avg = tel2.groupby('MiniSector')['Speed'].mean()
    winner_list = [driver1 if v1_avg.get(i, 0) > v2_avg.get(i, 0) else driver2 for i in range(num_minisectors + 1)]

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=[None], y=[None], mode='lines', line=dict(color=fast_c, width=6),
                             name=f'{fast_lbl} Faster ({fast_t:.3f}s)'))
    fig.add_trace(go.Scatter(x=[None], y=[None], mode='lines', line=dict(color=slow_c, width=6),
                             name=f'{slow_lbl} Faster ({slow_t:.3f}s)'))

    for ms in range(num_minisectors):
        sector_data = fast_tel[fast_tel['MiniSector'] == ms]
        if sector_data.empty: continue

        next_sector = fast_tel[fast_tel['MiniSector'] == ms + 1]
        if not next_sector.empty: sector_data = pd.concat([sector_data, next_sector.iloc[[0]]])

        winner = winner_list[ms]
        color = c1 if winner == driver1 else c2

        fig.add_trace(go.Scatter(
            x=sector_data['X'], y=sector_data['Y'], mode='lines',
            line=dict(color=color, width=8), showlegend=False, hoverinfo='skip'
        ))

    fig.update_layout(
        title="2D High-Res Track Dominance Map", template='plotly_dark',
        xaxis=dict(visible=False, scaleanchor="y", scaleratio=1), yaxis=dict(visible=False),
        margin=dict(l=40, r=40, t=60, b=40), legend=dict(yanchor="top", y=0.99, xanchor="left", x=0.01)
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
        row_heights=[0.75, 0.25], subplot_titles=("(SC/Pit Laps Removed from Racing Laps)", "Track Temperature (°C)")
    )

    comp_colors = {'SOFT': '#ff3333', 'MEDIUM': '#ffff00', 'HARD': '#ffffff', 'INTERMEDIATE': '#00ff00',
                   'WET': '#0099ff'}
    comp_drawn = set()

    # 4. Plot Pace & Tyres
    for lap_data, drv, lbl, col, unf in [(all_laps1, driver1, lbl1, c1, unf_1), (all_laps2, driver2, lbl2, c2, unf_2)]:
        if 'Compound' in lap_data.columns and 'Stint' in lap_data.columns:
            max_stint = lap_data['Stint'].max()

            for stint in lap_data['Stint'].dropna().unique():
                stint_subset = lap_data[lap_data['Stint'] == stint].sort_values(by='LapNumber')

                if stint_subset.empty: continue

                comp = stint_subset['Compound'].iloc[0]
                comp_drawn.add(comp)

                # 1. Draw the Pace Line & Markers for this stint
                fig.add_trace(go.Scatter(
                    x=stint_subset['LapNumber'],
                    y=stint_subset['LapTime_Sec'],
                    mode='lines+markers',
                    name=f'{drv} {comp}',
                    line=dict(color=col, width=2),
                    marker=dict(
                        color=comp_colors.get(comp, 'grey'),
                        size=10,
                        symbol='circle',
                        line=dict(width=0)
                    ),
                    showlegend=False
                ), row=1, col=1)

                # 2. Draw the Vertical "Pit Window" Line
                if stint < max_stint:
                    last_lap = stint_subset['LapNumber'].max()
                    fig.add_vline(
                        x=last_lap,
                        line_width=1.5,
                        line_dash="dot",
                        line_color=col,
                        opacity=0.6,
                        row='all',
                        col='all'
                    )

    # 5. Overlay SC/VSC/Red Flag lines
    sc_laps, vsc_laps, red_laps = set(), set(), set()
    all_laps = session.laps
    sc_laps.update(all_laps[all_laps['TrackStatus'].astype(str).str.contains('4', na=False)]['LapNumber'].dropna().tolist())
    vsc_laps.update(all_laps[all_laps['TrackStatus'].astype(str).str.contains('6', na=False)]['LapNumber'].dropna().tolist())
    red_laps.update(all_laps[all_laps['TrackStatus'].astype(str).str.contains('5', na=False)]['LapNumber'].dropna().tolist())

    lines = [(sc_laps, 'orange', 'SC / YF'), (vsc_laps, 'yellow', 'VSC'), (red_laps, 'red', 'Red Flag')]
    for laps, color, name in lines:
        for lap in laps:
            fig.add_vline(x=lap, line_width=2, line_dash="dash", line_color=color, opacity=0.5, row='all',
                          col='all')
        if laps:
            fig.add_trace(go.Scatter(x=[None], y=[None], mode='lines', line=dict(color=color, dash='dash', width=2),
                                     name=name, legend='legend'), row=1, col=1)

    # General Legend additions
    for drv, lbl, col in [(driver1, lbl1, c1), (driver2, lbl2, c2)]:
        fig.add_trace(
            go.Scatter(x=[None], y=[None], mode='lines', name=lbl,
                       line=dict(color=col, width=2),
                       legend='legend'), row=1, col=1)
    for comp in comp_drawn:
        if comp in comp_colors:
            fig.add_trace(go.Scatter(x=[None], y=[None], mode='markers', name=comp,
                                     marker=dict(color=comp_colors[comp], size=10),
                                     legend='legend'), row=1, col=1)

    # 6. Weather & Rain Overlay (Parses all session laps to span the entire race)
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

        # Plot the Track Temp line on Row 2
        fig.add_trace(go.Scatter(
            x=lap_nums, y=track_temps, mode='lines+markers', name='Track Temp (°C)',
            line=dict(color='white', width=2), marker=dict(size=4), showlegend=False
        ), row=2, col=1)

        # Draw Rain highlighting
        for lap in rain_laps:
            fig.add_vrect(x0=lap - 0.5, x1=lap + 0.5, fillcolor="blue", opacity=0.2, layer="below", line_width=0,
                          row='all', col='all')

        if rain_laps:
            fig.add_trace(go.Scatter(x=[None], y=[None], mode='markers',
                                     marker=dict(color='blue', opacity=0.5, symbol='square', size=15), name='Rain',
                                     legend='legend'), row=1, col=1)

    fig.update_layout(
        title="Strategy & Weather", template='plotly_dark', hovermode='x unified', margin=dict(l=40, r=40, t=60, b=40),
        legend=dict(title=dict(text="Legend"), yanchor="top", y=1, xanchor="left", x=1.02, bgcolor="rgba(0,0,0,0)")
    )
    fig.update_xaxes(title_text="Lap Number", row=2, col=1)
    fig.update_yaxes(title_text="Pace (s)", row=1, col=1)
    fig.update_yaxes(title_text="Temp (°C)", row=2, col=1)

    return fig

