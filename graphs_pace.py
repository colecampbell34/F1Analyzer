"""Field pace distribution from normalized session and lap records."""
import pandas as pd
import plotly.graph_objects as go

from data import get_single_driver_color, get_track_status_events, is_practice
from ui_utils import _apply_base_layout


def _coerce_bool_series(series):
    if series is None:
        return pd.Series(dtype=bool)
    return series.map(lambda value: False if pd.isna(value) else str(value).strip().casefold() not in {"", "0", "false", "f", "no", "n", "none", "nan"} if isinstance(value, str) else bool(value)).astype(bool)


def _is_dry_session_from_weather(weather_data):
    if weather_data is None or weather_data.empty or "rainfall" not in weather_data.columns:
        return True
    rainfall = _coerce_bool_series(weather_data["rainfall"])
    return rainfall.mean() < 0.02 if not rainfall.empty else True


def _clean_pace_laps(laps):
    if laps is None or laps.empty or "lap_duration" not in laps.columns:
        return pd.DataFrame()
    clean = laps[pd.to_numeric(laps["lap_duration"], errors="coerce").notna()].copy()
    if "is_pit_out_lap" in clean:
        clean = clean[~_coerce_bool_series(clean["is_pit_out_lap"])]
    if "pit_in" in clean:
        clean = clean[~_coerce_bool_series(clean["pit_in"])]
    return clean


def _lap_time_seconds(laps):
    if laps is None or laps.empty or "lap_duration" not in laps.columns:
        return pd.Series(dtype=float)
    return pd.to_numeric(laps["lap_duration"], errors="coerce").dropna()


def _filter_lap_times_107(lap_times, session_fastest, enabled=True):
    if not enabled or lap_times.empty or pd.isna(session_fastest):
        return lap_times
    return lap_times[lap_times <= float(session_fastest) * 1.07]


def _remove_lap_time_outliers(lap_times):
    """Remove isolated slow or fast laps with a per-driver IQR fence."""
    times = pd.to_numeric(lap_times, errors="coerce").dropna()
    if len(times) < 5:
        return times
    lower_quartile, upper_quartile = times.quantile([0.25, 0.75])
    spread = upper_quartile - lower_quartile
    median_ceiling = times.median() * 1.25
    if pd.isna(spread) or spread <= 1e-9:
        statistical = times if pd.isna(spread) else times[times == times.median()]
    else:
        statistical = times[times.between(lower_quartile - 1.5 * spread, upper_quartile + 1.5 * spread)]
    # A wide, mixed-condition distribution can inflate the IQR enough to keep
    # obviously invalid laps. The generous 25% ceiling removes gross timing
    # anomalies while retaining plausible wet/neutralized pace variation.
    return statistical[statistical <= median_ceiling]


def _exclude_race_context_laps(session, laps):
    """Exclude laps covered by published neutralization or pit evidence."""
    if laps.empty:
        return laps
    safety_laps, vsc_laps, red_laps, _yellow_laps = get_track_status_events(session)
    excluded = safety_laps | vsc_laps | red_laps
    frame = laps.copy()
    lap_numbers = pd.to_numeric(frame["lap_number"], errors="coerce")
    frame = frame[~lap_numbers.isin(excluded)]
    pit_records = getattr(session, "pits", pd.DataFrame())
    if not pit_records.empty and {"abbreviation", "lap_number"}.issubset(frame.columns) and "abbreviation" in pit_records:
        pit_rows = pit_records[["abbreviation", "lap_number"]].copy()
        pit_rows["lap_number"] = pd.to_numeric(pit_rows["lap_number"], errors="coerce")
        pit_rows = pit_rows.dropna(subset=["lap_number"])
        pit_pairs = set(zip(pit_rows["abbreviation"], pit_rows["lap_number"]))
        keep = [
            (row.abbreviation, float(row.lap_number)) not in pit_pairs
            for row in frame[["abbreviation", "lap_number"]].itertuples(index=False)
        ]
        frame = frame.loc[keep]
    return frame


def _build_grid_pace_fig(session, session_type):
    """Build a pace distribution while labeling source limitations."""
    from data import is_race, is_qualifying

    fig = go.Figure()
    drivers_data = []
    result_frame = session.results.copy() if session is not None else pd.DataFrame()
    has_results = not result_frame.empty and "position" in result_frame
    if has_results:
        result_frame["position_num"] = pd.to_numeric(result_frame["position"], errors="coerce")
        result_frame = result_frame.sort_values("position_num", na_position="last", kind="stable")
        ordered_drivers = [code for code in result_frame["abbreviation"].dropna().tolist() if isinstance(code, str) and len(code) == 3]
    else:
        ordered_drivers = session.drivers["abbreviation"].dropna().tolist() if session is not None and not session.drivers.empty else []
    result_positions = dict(zip(result_frame.get("abbreviation", []), result_frame.get("position_num", []))) if has_results else {}

    race_session = is_race(session_type)
    qualifying_session = is_qualifying(session_type)
    all_laps = session.laps.copy(deep=True) if session is not None else pd.DataFrame()
    if race_session:
        session_population = all_laps[all_laps["lap_number"] > 1] if not all_laps.empty else all_laps
    else:
        session_population = all_laps
    session_population = _clean_pace_laps(session_population)
    if race_session:
        session_population = _exclude_race_context_laps(session, session_population)
    session_seconds = _lap_time_seconds(session_population)
    session_fastest = session_seconds.min() if not session_seconds.empty else float("nan")
    is_dry_session = _is_dry_session_from_weather(getattr(session, "weather", None))

    for driver in ordered_drivers:
        if not isinstance(driver, str) or len(driver) != 3 or all_laps.empty:
            continue
        driver_laps = all_laps[all_laps["abbreviation"] == driver].copy()
        if race_session:
            driver_laps = driver_laps[driver_laps["lap_number"] > 1]
        driver_laps = _clean_pace_laps(driver_laps)
        if race_session:
            driver_laps = _exclude_race_context_laps(session, driver_laps)
        lap_times = _filter_lap_times_107(_lap_time_seconds(driver_laps), session_fastest, enabled=is_dry_session)
        lap_times = _remove_lap_time_outliers(lap_times)
        if lap_times.empty:
            continue
        drivers_data.append({
            "driver": driver, "times": lap_times.tolist(), "fastest": float(lap_times.min()),
            "median": float(lap_times.median()), "color": get_single_driver_color(driver, session),
            "position": pd.to_numeric(result_positions.get(driver), errors="coerce"),
        })

    if not drivers_data:
        fig.add_annotation(text="No valid lap durations are available for this session.", showarrow=False, x=0.5, y=0.5, xref="paper", yref="paper")
    else:
        if not has_results or is_practice(session_type) or "shootout" in str(session_type).casefold():
            sort_key = "median" if race_session else "fastest"
            drivers_data.sort(key=lambda item: item[sort_key])
            category_array = [item["driver"] for item in drivers_data]
        else:
            category_array = ordered_drivers
        for item in drivers_data:
            fig.add_trace(go.Box(
                y=item["times"], name=item["driver"], marker_color=item["color"],
                line_color=item["color"], boxmean=True,
                hovertemplate=f"{item['driver']}<br>Lap time: %{{y:.3f}}s<extra></extra>",
            ))
        fig.update_layout(xaxis=dict(categoryorder="array", categoryarray=category_array))

    session_label = "Racing Laps" if race_session else "Practice Laps" if is_practice(session_type) else "Qualifying Laps" if qualifying_session else "Session Laps"
    subtitle = "Pit, out, mapped SC/VSC/red-flag, and statistical outlier laps excluded; deleted-lap status is unavailable in the source."
    _apply_base_layout(
        fig, title=f"Grid Pace Distribution ({session_label})<br><sup>{subtitle}</sup>",
        showlegend=False, hovermode="closest", yaxis_title="Lap Time (s)",
        yaxis=dict(autorange="reversed"), uirevision="gridpace",
    )
    return fig
