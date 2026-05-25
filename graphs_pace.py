"""Grid pace graph builders and lap filtering helpers."""
import pandas as pd
import plotly.graph_objects as go

from data import get_single_driver_color, is_practice
from ui_utils import _apply_base_layout


def _coerce_bool_series(series):
    """Normalize FastF1 boolean-like values that may arrive as bools, numbers, or strings."""
    if series is None:
        return pd.Series(dtype=bool)

    def _to_bool(value):
        if pd.isna(value):
            return False
        if isinstance(value, str):
            return value.strip().lower() not in ('', '0', 'false', 'f', 'no', 'n', 'none', 'nan')
        return bool(value)

    return series.map(_to_bool).astype(bool)


def _is_dry_session_from_weather(weather_data):
    if weather_data is None or weather_data.empty or 'Rainfall' not in weather_data.columns:
        return True
    rainfall = _coerce_bool_series(weather_data['Rainfall'])
    return rainfall.mean() < 0.02 if not rainfall.empty else True


def _clean_pace_laps(laps):
    clean = laps.dropna(subset=['LapTime']).copy()
    if 'IsAccurate' in clean.columns:
        clean = clean[_coerce_bool_series(clean['IsAccurate'])]
    return clean


def _lap_time_seconds(laps):
    if laps is None or laps.empty or 'LapTime' not in laps.columns:
        return pd.Series(dtype=float)
    return laps['LapTime'].dt.total_seconds().dropna()


def _filter_lap_times_107(lap_times, session_fastest, enabled=True):
    if not enabled or lap_times.empty or pd.isna(session_fastest):
        return lap_times
    return lap_times[lap_times <= float(session_fastest) * 1.07]


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
    # Calculate the 107% cutoff from the same clean lap population shown by the chart.
    if _is_race:
        session_laps_for_cutoff = session.laps.pick_wo_box().pick_track_status('1')
        session_laps_for_cutoff = session_laps_for_cutoff[session_laps_for_cutoff['LapNumber'] > 1]
    else:
        session_laps_for_cutoff = session.laps.pick_quicklaps()
    session_lap_seconds = _lap_time_seconds(_clean_pace_laps(session_laps_for_cutoff))
    session_fastest = session_lap_seconds.min() if not session_lap_seconds.empty else float('nan')
    is_dry_session = _is_dry_session_from_weather(getattr(session, 'weather_data', None))

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

            laps = _clean_pace_laps(laps)
            if laps.empty:
                continue

            lap_times = _lap_time_seconds(laps)
            lap_times = _filter_lap_times_107(lap_times, session_fastest, enabled=is_dry_session)

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
        title=f'Grid Pace Distribution ({session_label})',
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
