"""Race, strategy, degradation, and race-gap graph builders."""
import numpy as np
import pandas as pd
import plotly.graph_objects as go

from data import get_track_status_events
from graph_shared import COMPOUND_COLORS, _collapse_lap_ranges
from graphs_common import _add_driver_legend_entries
from ui_utils import _apply_base_layout


def _driver_laps(session, driver):
    if session is None or session.laps.empty:
        return pd.DataFrame()
    return session.laps[session.laps["abbreviation"] == driver].copy()


def _timed_laps(laps, *, clean=False, racing_only=False):
    if laps.empty:
        return laps
    frame = laps.copy()
    frame["lap_duration"] = pd.to_numeric(frame["lap_duration"], errors="coerce")
    frame = frame.dropna(subset=["lap_duration"])
    if clean and "is_pit_out_lap" in frame:
        pit_out = frame["is_pit_out_lap"].map(lambda value: False if pd.isna(value) else bool(value))
        frame = frame[~pit_out]
    if clean and "pit_in" in frame:
        pit_in = frame["pit_in"].map(lambda value: False if pd.isna(value) else bool(value))
        frame = frame[~pit_in]
    if racing_only:
        frame = frame[frame["lap_number"] > 1]
    return frame.sort_values("lap_number", kind="stable")


def _remove_lap_time_outliers(laps):
    """Drop isolated pace outliers within each tyre stint using an IQR fence."""
    if laps.empty or len(laps) < 5:
        return laps
    groups = laps.groupby("stint_number", dropna=False, sort=False) if "stint_number" in laps else [(None, laps)]
    keep_indexes = []
    for _, group in groups:
        values = pd.to_numeric(group["lap_duration"], errors="coerce")
        if len(group) < 5 or values.notna().sum() < 5:
            keep_indexes.extend(group.index[values.notna()].tolist())
            continue
        lower_quartile, upper_quartile = values.quantile([0.25, 0.75])
        spread = upper_quartile - lower_quartile
        if pd.isna(spread):
            keep = values.notna()
        elif spread <= 1e-9:
            keep = values == values.median()
        else:
            keep = values.between(lower_quartile - 1.5 * spread, upper_quartile + 1.5 * spread)
        keep_indexes.extend(group.index[keep.fillna(False)].tolist())
    return laps.loc[keep_indexes].sort_values("lap_number", kind="stable")


def _strategy_laps(session, driver):
    laps = _timed_laps(_driver_laps(session, driver), clean=True, racing_only=True)
    if laps.empty:
        return laps
    safety_laps, vsc_laps, red_laps, _yellow_laps = get_track_status_events(session)
    interrupted = safety_laps | vsc_laps | red_laps
    if interrupted:
        laps = laps[~pd.to_numeric(laps["lap_number"], errors="coerce").isin(interrupted)]
    pit_records = getattr(session, "pits", pd.DataFrame())
    if not pit_records.empty:
        pit_laps = pd.to_numeric(
            pit_records.loc[pit_records["abbreviation"] == driver, "lap_number"], errors="coerce",
        ).dropna().unique()
        if len(pit_laps):
            laps = laps[~pd.to_numeric(laps["lap_number"], errors="coerce").isin(pit_laps)]
    # One-lap stints cannot establish their own distribution fence. Apply a
    # conservative driver-wide ceiling first to catch gross timing anomalies
    # such as a multi-minute lap, without excluding slower wet-weather pace.
    durations = pd.to_numeric(laps["lap_duration"], errors="coerce")
    if not durations.empty:
        global_ceiling = durations.median() * 1.25
        laps = laps[durations <= global_ceiling]
    return _remove_lap_time_outliers(laps)


def _compound_name(value):
    name = str(value or "").strip().upper()
    return "UNAVAILABLE" if name in {"", "UNKNOWN", "NONE", "NAN", "NULL"} else name


def _pit_laps(session, driver):
    pits = getattr(session, "pits", pd.DataFrame())
    if pits.empty:
        return []
    return sorted(pd.to_numeric(pits.loc[pits["abbreviation"] == driver, "lap_number"], errors="coerce").dropna().astype(int).unique().tolist())


def _add_status_regions(fig, session):
    sc_laps, vsc_laps, red_laps, _yellow_laps = get_track_status_events(session)
    for lap_set, color in ((sc_laps, "orange"), (vsc_laps, "yellow"), (red_laps, "red")):
        for start_lap, end_lap in _collapse_lap_ranges(lap_set):
            fig.add_vrect(x0=start_lap - 0.5, x1=end_lap + 0.5, fillcolor=color, opacity=0.14, layer="below", line_width=0, row="all", col="all")
    return bool(sc_laps or vsc_laps or red_laps)


def _add_status_legend(fig):
    for name, color in (("SC", "orange"), ("VSC", "yellow"), ("Red flag", "red")):
        fig.add_trace(go.Scatter(
            x=[None], y=[None], mode="markers", name=name,
            marker=dict(color=color, symbol="square", size=9),
            hoverinfo="skip", showlegend=True,
        ), row=1, col=1)


def _build_strategy_fig(session, driver1, driver2, lbl1, lbl2, c1, c2):
    """Plot stint pace, pit changes, and available weather samples."""
    from plotly.subplots import make_subplots

    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.05,
                        row_heights=[0.75, 0.25], subplot_titles=("", "Track temperature (°C)"))
    compound_drawn = set()
    for driver, label, color in ((driver1, lbl1, c1), (driver2, lbl2, c2)):
        laps = _strategy_laps(session, driver)
        if not laps.empty:
            if "stint_number" in laps and "compound" in laps:
                for stint in laps["stint_number"].dropna().unique():
                    stint_laps = laps[laps["stint_number"] == stint]
                    if stint_laps.empty:
                        continue
                    compound = _compound_name(stint_laps.iloc[0].get("compound"))
                    compound_drawn.add(compound)
                    fig.add_trace(go.Scatter(
                        x=stint_laps["lap_number"], y=stint_laps["lap_duration"],
                        mode="lines+markers", name=f"{driver} {compound}",
                        line=dict(color=color, width=2),
                        marker=dict(color=COMPOUND_COLORS.get(compound, "#737980"), size=8),
                        showlegend=False,
                        hovertemplate=f"{driver} · {compound}<br>Lap %{{x}} · %{{y:.3f}}s<extra></extra>",
                    ), row=1, col=1)
        for pit_lap in _pit_laps(session, driver):
            fig.add_vline(x=pit_lap, line_width=1.5, line_dash="dot", line_color=color, opacity=0.65, row="all", col="all")

    has_status = _add_status_regions(fig, session)
    _add_driver_legend_entries(fig, [(driver1, c1), (driver2, c2)], row=1, col=1)
    _add_status_legend(fig)
    for compound in compound_drawn:
        if compound in COMPOUND_COLORS:
            fig.add_trace(go.Scatter(x=[None], y=[None], mode="markers", name=compound,
                                     marker=dict(color=COMPOUND_COLORS[compound], size=9),
                                     showlegend=False, legend="legend"), row=1, col=1)

    weather = getattr(session, "weather", pd.DataFrame())
    laps = session.laps.dropna(subset=["date_start", "lap_duration", "lap_number"]).copy() if session is not None and not session.laps.empty else pd.DataFrame()
    if not weather.empty and not laps.empty and "timestamp" in weather:
        laps["lap_end_time"] = laps["date_start"] + pd.to_timedelta(laps["lap_duration"], unit="s", errors="coerce")
        weather_sorted = weather.dropna(subset=["timestamp"]).sort_values("timestamp")
        lap_ends = (
            laps[["lap_number", "lap_end_time"]]
            .dropna()
            .groupby("lap_number", as_index=False, sort=True)["lap_end_time"]
            .median()
            .sort_values("lap_end_time")
        )
        if "track_temperature" in weather_sorted:
            temp = weather_sorted[["timestamp", "track_temperature"]].dropna(subset=["track_temperature"])
            if not temp.empty and not lap_ends.empty:
                aligned = pd.merge_asof(lap_ends, temp, left_on="lap_end_time", right_on="timestamp", direction="nearest")
                aligned = aligned.sort_values("lap_number", kind="stable")
                aligned["track_temperature"] = aligned["track_temperature"].rolling(window=3, center=True, min_periods=1).median()
                fig.add_trace(go.Scatter(
                    x=aligned["lap_number"], y=aligned["track_temperature"], mode="lines",
                    name="Track temp", line=dict(color="white", width=2.5, shape="spline", smoothing=0.5), showlegend=False,
                ), row=2, col=1)
        if "rainfall" in weather_sorted:
            rain = weather_sorted[weather_sorted["rainfall"].fillna(False).astype(bool)]
            if not rain.empty:
                rain_laps = []
                for lap in laps.itertuples():
                    if ((rain["timestamp"] >= lap.date_start) & (rain["timestamp"] <= lap.lap_end_time)).any():
                        rain_laps.append(int(lap.lap_number))
                for lap_number in sorted(set(rain_laps)):
                    fig.add_vrect(x0=lap_number - 0.5, x1=lap_number + 0.5, fillcolor="blue", opacity=0.18, layer="below", line_width=0, row="all", col="all")

    if not has_status:
        messages_state = session.quality.get("endpoints", {}).get("race_control", {}).get("state")
        note = "Race-control intervals are unavailable." if messages_state == "unavailable" else "No mapped SC/VSC/red-flag interval was found."
        fig.add_annotation(text=note, x=0.01, y=0.98, xref="paper", yref="paper", xanchor="left", yanchor="top", showarrow=False, font=dict(size=10, color="#9ba0a6"))

    _apply_base_layout(fig, title="Strategy & Weather", legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="center", x=0.5, font=dict(size=10)), uirevision="strategy")
    fig.update_xaxes(title_text="Lap number", row=2, col=1)
    fig.update_yaxes(title_text="Lap time (s)", row=1, col=1, autorange="reversed")
    fig.update_yaxes(title_text="Track temp (°C)", row=2, col=1)
    return fig


def _build_deg_fig(session, driver1, driver2, lbl1, lbl2, c1, c2):
    """Estimate within-stint pace change after the existing fuel correction."""
    from plotly.subplots import make_subplots

    fuel_correction = 0.06
    fig = make_subplots(rows=1, cols=2, shared_yaxes=True, subplot_titles=(lbl1, lbl2), horizontal_spacing=0.05)
    for column, (driver, color) in enumerate(((driver1, c1), (driver2, c2)), 1):
        laps = _strategy_laps(session, driver)
        if laps.empty or "stint_number" not in laps:
            continue
        for stint in sorted(laps["stint_number"].dropna().unique()):
            stint_laps = laps[laps["stint_number"] == stint].sort_values("lap_number").copy()
            # Short stints produce noisy, misleading degradation slopes.
            if len(stint_laps) < 6:
                continue
            compound = _compound_name(stint_laps.iloc[0].get("compound"))
            stint_start = stint_laps["lap_number"].iloc[0]
            stint_laps["stint_lap"] = stint_laps["lap_number"] - stint_start + 1
            stint_laps["corrected_time"] = stint_laps["lap_duration"] + fuel_correction * stint_laps["stint_lap"]
            marker_color = COMPOUND_COLORS.get(compound, "#737980")
            fig.add_trace(go.Scatter(
                x=stint_laps["stint_lap"], y=stint_laps["corrected_time"], mode="lines+markers",
                name=f"{driver} {compound} stint {int(stint)}", marker=dict(color=marker_color, size=7),
                line=dict(color=marker_color, width=1.5), showlegend=False,
                hovertemplate=f"{driver} · stint {int(stint)} ({compound})<br>Stint lap %{{x}}<br>Fuel-corrected estimate: %{{y:.3f}}s<extra></extra>",
            ), row=1, col=column)
            if len(stint_laps) >= 3:
                slope, intercept = np.polyfit(stint_laps["stint_lap"].astype(float), stint_laps["corrected_time"].astype(float), 1)
                x_fit = [stint_laps["stint_lap"].min(), stint_laps["stint_lap"].max()]
                fig.add_trace(go.Scatter(x=x_fit, y=[slope * x + intercept for x in x_fit], mode="lines",
                                         line=dict(dash="dash", color=marker_color, width=2),
                                         name=f"{driver} {compound} {slope:+.3f}s/lap", showlegend=False), row=1, col=column)
    _apply_base_layout(fig, title="Tyre Degradation Estimate (Fuel-Corrected)<br><sup>Relative trend; the 0.06 s/lap fuel correction is an estimate.</sup>", margin=dict(l=40, r=40, t=80, b=40), showlegend=False, uirevision="degradation")
    fig.update_yaxes(title_text="Fuel-corrected lap time (s)", row=1, col=1, autorange="reversed")
    fig.update_xaxes(title_text="Stint lap", row=1, col=1)
    fig.update_xaxes(title_text="Stint lap", row=1, col=2)
    return fig


def _gap_value(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return np.nan


def _build_race_gaps_fig(session, driver1, driver2, lbl1, lbl2, c1, c2):
    """Plot observed intervals where available, otherwise a labeled estimate."""
    from plotly.subplots import make_subplots

    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.08, row_heights=[0.7, 0.3])
    laps1, laps2 = _driver_laps(session, driver1), _driver_laps(session, driver2)
    if laps1.empty or laps2.empty:
        fig.add_annotation(text="Race lap timing is unavailable for one selected driver.", showarrow=False, x=0.5, y=0.5, xref="paper", yref="paper")
        _apply_base_layout(fig, title="Race Gap & Position Analysis", uirevision="gaps")
        return fig
    columns = ["lap_number", "lap_duration", "position", "gap_to_leader"]
    merged = pd.merge(
        laps1[[column for column in columns if column in laps1]].rename(columns={"lap_duration": "lap_time_1", "position": "position_1", "gap_to_leader": "leader_gap_1"}),
        laps2[[column for column in columns if column in laps2]].rename(columns={"lap_duration": "lap_time_2", "position": "position_2", "gap_to_leader": "leader_gap_2"}),
        on="lap_number", how="outer", suffixes=("_1", "_2"),
    ).sort_values("lap_number")
    gap_label = "Gap to leader difference (s)"
    has_observed_gap = False
    gap_start_note = ""
    if {"leader_gap_1", "leader_gap_2"}.issubset(merged.columns):
        first = merged["leader_gap_1"].map(_gap_value)
        second = merged["leader_gap_2"].map(_gap_value)
        observed = first - second
        has_observed_gap = bool(np.isfinite(observed.to_numpy(dtype=float)).any())
        if has_observed_gap:
            merged["gap"] = observed
            gap_label = "Observed relative gap to leader (s)"
    if not has_observed_gap:
        merged["cum_1"] = pd.to_numeric(merged.get("lap_time_1"), errors="coerce").cumsum()
        merged["cum_2"] = pd.to_numeric(merged.get("lap_time_2"), errors="coerce").cumsum()
        merged["gap"] = merged["cum_1"] - merged["cum_2"]
        gap_label = "Derived cumulative lap-time gap (s)"
    finite = merged[np.isfinite(pd.to_numeric(merged["gap"], errors="coerce"))]
    if not finite.empty:
        gap_x = finite["lap_number"].tolist()
        gap_y = finite["gap"].tolist()
        first_observed_lap = min(gap_x)
        if first_observed_lap > 1:
            # Start the relative-gap trace at the race start. The source does
            # not publish leader intervals for every opening lap, so use a
            # neutral zero baseline until its first observed sample.
            gap_x.insert(0, 0)
            gap_y.insert(0, 0.0)
            gap_start_note = " Opening lap intervals are unavailable; trace starts at a neutral grid baseline."
        fig.add_trace(go.Scatter(x=gap_x, y=gap_y, mode="lines", fill="tozeroy",
                                 line=dict(color="white", width=2), fillcolor="rgba(255,255,255,0.1)", showlegend=False,
                                 hovertemplate="Lap %{x}<br>Relative gap: %{y:.3f}s<extra></extra>"), row=1, col=1)
        fig.add_hline(y=0, line_dash="dash", line_color="grey", opacity=0.5, row=1, col=1)
    result_frame = session.results if session is not None else pd.DataFrame()
    grid = dict(zip(result_frame.get("abbreviation", []), result_frame.get("grid_position", []))) if not result_frame.empty else {}
    for driver, color, column in ((driver1, c1, "position_1"), (driver2, c2, "position_2")):
        if column not in merged:
            continue
        positions = pd.to_numeric(merged[column], errors="coerce")
        x_values, y_values = merged["lap_number"].tolist(), positions.tolist()
        grid_position = pd.to_numeric(grid.get(driver), errors="coerce")
        if pd.notna(grid_position) and grid_position > 0:
            x_values.insert(0, 0)
            y_values.insert(0, float(grid_position))
        fig.add_trace(go.Scatter(x=x_values, y=y_values, mode="lines+markers", name=driver,
                                 line=dict(color=color, width=2), marker=dict(color=color, size=5), showlegend=False,
                                 connectgaps=True,
                                 hovertemplate="Grid / lap %{x}<br>Position: P%{y}<extra></extra>"), row=2, col=1)
    for driver, color in ((driver1, c1), (driver2, c2)):
        for pit_lap in _pit_laps(session, driver):
            fig.add_vline(x=pit_lap, line_width=1.5, line_dash="dot", line_color=color, opacity=0.6, row="all", col="all")
    _add_status_regions(fig, session)
    _add_status_legend(fig)
    max_lap = float(merged["lap_number"].max()) if not merged.empty else 1.0
    _apply_base_layout(
        fig, title=f"Race Gap & Position Analysis<br><sup>{gap_label}; pit and race-control context shown when published.{gap_start_note}</sup>",
        margin=dict(l=40, r=18, t=70, b=40), showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="right", x=1, font=dict(size=9)),
        uirevision="gaps",
    )
    fig.update_yaxes(title_text="Relative gap (s)", row=1, col=1)
    fig.update_yaxes(title_text="Position", row=2, col=1, autorange="reversed", tickvals=list(range(1, 21)))
    fig.update_xaxes(title_text="Lap number", range=[0, max_lap + 0.5], row=2, col=1)
    return fig
