"""Race, strategy, degradation, and race-gap graph builders."""

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from data import get_track_status_events
from graph_shared import COMPOUND_COLORS, _collapse_lap_ranges
from graphs_common import _add_driver_legend_entries
from ui_utils import _apply_base_layout


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
        title='Tyre Deg Analysis (Fuel-Corrected)<br><sup>+ = more degradation, - = pace improving</sup>',
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
                        row_heights=[0.7, 0.3])
    last_lap = 1.0

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
            if not res1.empty:
                grid1 = pd.to_numeric(res1.iloc[0].get('GridPosition'), errors='coerce')
            res2 = session.results[session.results['Abbreviation'] == driver2]
            if not res2.empty:
                grid2 = pd.to_numeric(res2.iloc[0].get('GridPosition'), errors='coerce')

        last_lap = float(merged['LapNumber'].max())

        if 'Pos1' in merged.columns:
            x_vals = merged['LapNumber'].tolist()
            y_vals = merged['Pos1'].astype(float).tolist()
            if pd.notna(grid1) and grid1 > 0:
                x_vals = [0] + x_vals
                y_vals = [float(grid1)] + y_vals
            
            fig.add_trace(go.Scatter(
                x=x_vals, y=y_vals, mode='lines+markers',
                name=f'{lbl1} Pos', line=dict(color=c1, width=2),
                marker=dict(color=c1, size=5), showlegend=False,
                hovertemplate='Grid / lap %{x}<br>Position: P%{y}<extra></extra>',
            ), row=2, col=1)

        if 'Pos2' in merged.columns:
            x_vals = merged['LapNumber'].tolist()
            y_vals = merged['Pos2'].astype(float).tolist()
            if pd.notna(grid2) and grid2 > 0:
                x_vals = [0] + x_vals
                y_vals = [float(grid2)] + y_vals

            fig.add_trace(go.Scatter(
                x=x_vals, y=y_vals, mode='lines+markers',
                name=f'{lbl2} Pos', line=dict(color=c2, width=2),
                marker=dict(color=c2, size=5), showlegend=False,
                hovertemplate='Grid / lap %{x}<br>Position: P%{y}<extra></extra>',
            ), row=2, col=1)

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
        margin=dict(l=40, r=18, t=70, b=40),
        showlegend=False,
        uirevision='gaps'
    )
    fig.update_yaxes(title_text='Gap (seconds)', row=1, col=1)
    fig.update_yaxes(title_text='Position', row=2, col=1, autorange='reversed',
                     tickvals=list(range(1, 21)))
    fig.update_xaxes(title_text='Lap Number', range=[0, last_lap + 0.5], row=2, col=1)

    return fig
