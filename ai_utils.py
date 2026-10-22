"""Grounded AI context and prompt helpers for normalized OpenF1 sessions."""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from data import get_driver_info, get_teammate_from_info


def build_ai_prompt(session_context, question, history=None):
    """Build a constrained, data-grounded prompt for the configured model."""
    history_text = ""
    if history:
        history_text = "\n\n=== PREVIOUS Q&A ===\n" + "\n\n".join(
            f"Q: {item['question']}\nA: {item['answer'][:1500]}"
            for item in history[-3:]
        )
    return (
        "You are an expert Formula 1 data analyst. Treat the supplied session "
        "context as the only authoritative source for this session. Driver and "
        "team identity, classification, starting grid, and timing claims must "
        "match the listed source and quality notes. Do not fill gaps from memory.\n\n"
        "Your job is to explain performance, not merely repeat the context. For "
        "comparisons, state the result first, identify where time was gained or "
        "lost, quantify the contribution of each relevant phase, then connect "
        "that pattern to supporting telemetry. Use the most specific evidence "
        "available: sector splits first, then the telemetry progress windows "
        "and speed/braking/throttle patterns. A faster lap time alone does not "
        "show where the gain occurred.\n\n"
        "Use only supported values. Distinguish observed OpenF1 data, optional "
        "Jolpica supplements, and derived estimates. Do not claim official status "
        "for a supplemental or derived value. If telemetry is absent or marked "
        "incomplete, do not infer speed, braking, throttle, gear, GPS, or lap-delta "
        "details. Treat gaps in samples as unknown, not as zero.\n\n"
        "For selected-lap comparisons, interpret the supplied cumulative time-gap "
        "changes by progress window: a shrinking gap means the primary driver "
        "gained time in that window; a growing gap means they lost time. Relate "
        "gain/loss windows to sampled speed and braking evidence. Group adjacent "
        "windows into a coherent braking/cornering phase when the evidence supports "
        "it. Call a phase cornering or braking-related only when telemetry supports "
        "it (for example, braking samples and a speed reduction relative to "
        "adjacent windows); otherwise describe it "
        "as a lap-progress window. Do not invent corner numbers, track locations, "
        "or causal explanations from approximate integrated distance. Mention "
        "sampling limits and qualify small or ambiguous differences.\n\n"
        "Keep lap performance separate from race outcome: a fastest lap does not "
        "make its driver the race winner, and finishing position is not evidence "
        "of who was faster on the selected laps. Never add result claims unless "
        "they appear in the classification data.\n\n"
        "Compare lap and sector times only where both values are available. Note "
        "when pit-out laps or laps marked by a race-control heuristic affect a "
        "comparison. Describe tyre degradation as an estimate. Pit lane duration "
        "and stationary service duration are different measurements. State missing "
        "data plainly. Do not copy earlier answers as evidence: recalculate claims "
        "from the current session data. Answer with a concise but substantive "
        "engineering explanation and bold key metrics.\n\n"
        f"=== SESSION DATA ===\n{session_context}{history_text}\n\n"
        f"=== USER QUESTION ===\n{question}"
    )


def _fmt_seconds(value):
    try:
        value = float(value)
        return f"{value:.3f}s" if math.isfinite(value) else "N/A"
    except (TypeError, ValueError):
        return "N/A"


def _get_field_summary(session):
    lines = ["=== FULL FIELD CLASSIFICATION ==="]
    if session.results.empty:
        return "\n".join(lines + ["Classification unavailable."])
    pits = session.pits.groupby("abbreviation").size().to_dict() if not session.pits.empty else {}
    for row in session.results.sort_values("position", na_position="last").to_dict("records"):
        abbr = row.get("abbreviation") or "?"
        pos = row.get("position")
        place = f"P{int(pos)}" if pd.notna(pos) else str(row.get("status") or "Unclassified")
        gap_value = row.get("gap")
        if pos and pos > 1 and isinstance(gap_value, (int, float)):
            gap = f"+{_fmt_seconds(gap_value)}"
        elif pos and pos > 1 and isinstance(gap_value, str) and gap_value.strip():
            gap = f"gap {gap_value.strip()}"
        else:
            gap = ""
        pit_count = int(pits.get(abbr, 0))
        stop_text = f" | {pit_count} pit visits" if pit_count else ""
        lines.append(f"{place}: {abbr} ({row.get('team_name') or 'team unavailable'}) {gap}{stop_text}")
    source = ", ".join(sorted(set(session.results.get("source", pd.Series(dtype=str)).dropna().astype(str))))
    if source:
        lines.append(f"Classification source: {source}.")
    return "\n".join(lines)


def _get_starting_grid(session):
    lines = ["=== STARTING GRID ==="]
    if session.grid.empty:
        # Jolpica result supplements may carry the grid when the OpenF1 grid
        # endpoint has not published one.
        if not session.results.empty and "grid_position" in session.results:
            grid = session.results.dropna(subset=["grid_position"])
        else:
            grid = pd.DataFrame()
    else:
        grid = session.grid
    if grid.empty:
        return "\n".join(lines + ["Starting grid unavailable; no grid was published in the loaded sources."])
    for row in grid.sort_values("grid_position", na_position="last").to_dict("records"):
        pos = row.get("grid_position")
        lines.append(f"P{int(pos) if pd.notna(pos) else '—'}: {row.get('abbreviation') or '?'}")
    sources = sorted(set(grid.get("source", pd.Series(dtype=str)).dropna().astype(str)))
    lines.append(f"Grid source: {', '.join(sources) if sources else 'not recorded'}.")
    return "\n".join(lines)


def _get_field_tyre_strategy(session):
    lines = ["=== FIELD TYRE STRATEGY ==="]
    if session.stints.empty:
        return "\n".join(lines + ["Stint/compound data unavailable."])
    for driver, group in session.stints.groupby("abbreviation", sort=False):
        details = []
        for row in group.sort_values("stint_number", na_position="last").to_dict("records"):
            start, end = row.get("lap_start"), row.get("lap_end")
            life = row.get("tyre_age_at_start")
            lap_text = f"L{int(start) if pd.notna(start) else '?'}–L{int(end) if pd.notna(end) else '?'}"
            age_text = f", starting tyre age {int(life)}" if pd.notna(life) else ""
            details.append(f"{row.get('compound') or 'UNKNOWN'} ({lap_text}{age_text})")
        if details:
            lines.append(f"{driver}: {', '.join(details)}")
    return "\n".join(lines)


def _get_teammate_benchmark(session, driver_abbr):
    info = get_driver_info(session)
    teammate = get_teammate_from_info(driver_abbr, info)
    if not teammate:
        return f"No teammate could be identified for {driver_abbr} from the session driver metadata."
    rows = session.results[session.results["abbreviation"] == teammate] if not session.results.empty else pd.DataFrame()
    laps = session.laps[session.laps["abbreviation"] == teammate] if not session.laps.empty else pd.DataFrame()
    if rows.empty and laps.empty:
        return f"Teammate {teammate} has no classification or lap data."
    bits = [f"Teammate benchmark for {teammate}"]
    if not rows.empty:
        result = rows.iloc[0]
        position = result.get("position")
        bits.append(f"classification {f'P{int(position)}' if pd.notna(position) else result.get('status') or 'unknown'}")
    if not laps.empty:
        times = pd.to_numeric(laps["lap_duration"], errors="coerce").dropna()
        if not times.empty:
            bits.append(f"best timed lap {_fmt_seconds(times.min())}")
            clean = laps[(~laps["pit_out"].fillna(False)) & (~laps["pit_in"].fillna(False))]
            clean_times = pd.to_numeric(clean["lap_duration"], errors="coerce").dropna()
            if not clean_times.empty:
                bits.append(f"median recorded lap {_fmt_seconds(clean_times.median())}")
    return ", ".join(bits) + "."


def _get_session_narrative(session):
    if session.messages.empty:
        return ""
    lines = ["=== SESSION NARRATIVE ==="]
    messages = session.messages.dropna(subset=["message"]).tail(60)
    for row in messages.to_dict("records"):
        message = str(row.get("message") or "").strip()
        if not message:
            continue
        stamp = row.get("timestamp")
        when = f"[{stamp.isoformat()}] " if pd.notna(stamp) else ""
        category = row.get("category") or row.get("flag") or "event"
        lines.append(f"{when}{category}: {message}")
    if len(lines) == 1:
        return ""
    lines.append("Source: OpenF1 race-control messages; timing-to-lap status mapping is heuristic where noted.")
    return "\n".join(lines)


def _weather_summary(session):
    if session.weather.empty:
        return ""
    lines = ["=== WEATHER SAMPLES ==="]
    step = max(1, len(session.weather) // 10)
    for row in session.weather.iloc[::step].to_dict("records"):
        stamp = row.get("timestamp")
        parts = []
        for column, label, suffix in (("track_temperature", "track", "°C"), ("air_temperature", "air", "°C"), ("rainfall", "rain", ""), ("wind_speed", "wind", "m/s")):
            value = row.get(column)
            if pd.notna(value):
                parts.append(f"{label} {value}{suffix}")
        if parts:
            lines.append(f"{stamp.isoformat() if pd.notna(stamp) else 'time unavailable'}: {', '.join(parts)}")
    return "\n".join(lines) if len(lines) > 1 else ""


def _lap_summary(lap, driver):
    if lap is None:
        return f"{driver}: selected lap unavailable."
    parts = [f"{driver} L{lap.get('lap_number')}: {_fmt_seconds(lap.get('lap_duration'))}"]
    for column, label in (("duration_sector_1", "S1"), ("duration_sector_2", "S2"), ("duration_sector_3", "S3")):
        if pd.notna(lap.get(column)):
            parts.append(f"{label} {_fmt_seconds(lap.get(column))}")
    for column, label in (("compound", "tyre"), ("tyre_age", "tyre age"), ("track_status", "track status")):
        value = lap.get(column)
        if value is not None and pd.notna(value):
            parts.append(f"{label} {value}")
    if bool(lap.get("pit_out")):
        parts.append("pit-out lap")
    if bool(lap.get("pit_in")):
        parts.append("pit-in lap")
    return ", ".join(parts)


def _get_lap_time_comparison(driver1, driver2, lap1, lap2):
    """Calculate lap and sector deltas from the selected timing records."""
    lines = ["Timing comparison (driver 1 elapsed time minus driver 2 elapsed time; negative means driver 1 was faster)."]
    for field, label in (
        ("lap_duration", "Total lap"),
        ("duration_sector_1", "Sector 1"),
        ("duration_sector_2", "Sector 2"),
        ("duration_sector_3", "Sector 3"),
    ):
        first = pd.to_numeric(pd.Series([lap1.get(field) if lap1 is not None else None]), errors="coerce").iloc[0]
        second = pd.to_numeric(pd.Series([lap2.get(field) if lap2 is not None else None]), errors="coerce").iloc[0]
        if pd.isna(first) or pd.isna(second):
            lines.append(f"{label}: unavailable for at least one driver.")
            continue
        delta = float(first - second)
        outcome = f"{driver1} gained" if delta < 0 else f"{driver1} lost" if delta > 0 else "tied"
        lines.append(
            f"{label}: {driver1} {_fmt_seconds(first)} vs {driver2} {_fmt_seconds(second)}; "
            f"{outcome} {_fmt_seconds(abs(delta))}."
        )
    return "\n".join(lines)


def _trace_summary(trace, driver, lap_number):
    if trace is None or trace.empty or "Speed" not in trace:
        return f"{driver} lap {lap_number}: no usable selected-lap telemetry trace."
    speed = pd.to_numeric(trace["Speed"], errors="coerce").dropna()
    if speed.empty:
        return f"{driver} lap {lap_number}: no usable selected-lap speed samples."
    parts = [f"{driver} lap {lap_number}: {len(speed)} speed samples, max {speed.max():.0f} km/h, mean {speed.mean():.1f} km/h"]
    for column, label, predicate in (("Throttle", "full throttle samples", lambda values: values >= 99), ("Brake", "braking samples", lambda values: values > 0)):
        if column in trace:
            values = pd.to_numeric(trace[column], errors="coerce").dropna()
            if not values.empty:
                parts.append(f"{label} {predicate(values).mean() * 100:.1f}%")
    if "nGear" in trace:
        gears = pd.to_numeric(trace["nGear"], errors="coerce").dropna()
        if not gears.empty:
            parts.append(f"gear range {int(gears.min())}–{int(gears.max())}")
    quality = trace.attrs.get("quality", {})
    source = quality.get("source")
    if source:
        parts.append(f"trace source {source}")
    if not quality.get("has_position", False):
        parts.append("position samples incomplete")
    return ", ".join(parts)


def _get_trace_comparison_windows(driver1, driver2, tel1, tel2, window_count=20):
    """Summarize time-gap changes and telemetry by normalized lap-progress window."""
    def _prepare(trace):
        required = {"Distance", "Time", "Speed"}
        if trace is None or trace.empty or not required.issubset(trace.columns):
            return None
        frame = trace.loc[:, [column for column in ("Distance", "Time", "Speed", "Brake", "Throttle") if column in trace]].copy()
        frame["Distance"] = pd.to_numeric(frame["Distance"], errors="coerce")
        frame["TimeSeconds"] = pd.to_timedelta(frame["Time"], errors="coerce").dt.total_seconds()
        frame["Speed"] = pd.to_numeric(frame["Speed"], errors="coerce")
        if "Brake" in frame:
            frame["Brake"] = pd.to_numeric(frame["Brake"], errors="coerce")
        if "Throttle" in frame:
            frame["Throttle"] = pd.to_numeric(frame["Throttle"], errors="coerce")
        frame = frame.replace([np.inf, -np.inf], np.nan).dropna(subset=["Distance", "TimeSeconds", "Speed"])
        frame = frame.sort_values("Distance").drop_duplicates("Distance", keep="first")
        if len(frame) < 6:
            return None
        start = float(frame["Distance"].iloc[0])
        span = float(frame["Distance"].iloc[-1] - start)
        if span <= 0:
            return None
        frame["Progress"] = (frame["Distance"] - start) / span
        frame["TimeSeconds"] -= float(frame["TimeSeconds"].iloc[0])
        return frame

    first, second = _prepare(tel1), _prepare(tel2)
    lines = ["Telemetry comparison windows (derived from sampled car data; progress and distance are approximate)."]
    if first is None or second is None:
        return "\n".join(lines + ["Insufficient aligned speed/time samples to calculate progress-window time gains."])

    boundaries = np.linspace(0.0, 1.0, window_count + 1)
    gap_at_boundary = []
    for progress in boundaries:
        time1 = np.interp(progress, first["Progress"], first["TimeSeconds"])
        time2 = np.interp(progress, second["Progress"], second["TimeSeconds"])
        gap_at_boundary.append(float(time1 - time2))

    for index, (start, end) in enumerate(zip(boundaries[:-1], boundaries[1:])):
        gap_change = gap_at_boundary[index + 1] - gap_at_boundary[index]
        start_distance = float(np.interp(start, first["Progress"], first["Distance"] - first["Distance"].iloc[0]))
        end_distance = float(np.interp(end, first["Progress"], first["Distance"] - first["Distance"].iloc[0]))
        parts = [
            f"{start:.0%}–{end:.0%} lap progress (reference-derived distance about {start_distance:.0f}–{end_distance:.0f} m):",
            f"{driver1} {'gained' if gap_change < 0 else 'lost'} {_fmt_seconds(abs(gap_change))} vs {driver2}",
        ]
        for driver, frame in ((driver1, first), (driver2, second)):
            mask = (frame["Progress"] >= start) & (
                (frame["Progress"] < end) | ((end == 1.0) & (frame["Progress"] <= end))
            )
            window = frame.loc[mask]
            if window.empty:
                continue
            parts.append(f"{driver} mean speed {window['Speed'].mean():.0f} km/h")
            if "Brake" in window:
                brake = window["Brake"].dropna()
                if not brake.empty:
                    parts.append(f"brake active {brake.gt(0).mean() * 100:.0f}% of samples")
            if "Throttle" in window:
                throttle = window["Throttle"].dropna()
                if not throttle.empty:
                    parts.append(f"full throttle {throttle.ge(99).mean() * 100:.0f}% of samples")
        lines.append("; ".join(parts) + ".")
    lines.append(
        f"Cumulative gap is {driver1} elapsed time minus {driver2} elapsed time; "
        "negative means the primary driver is ahead. Window gains are changes "
        "in that gap, not official sector timing."
    )
    return "\n".join(lines)


def _get_dashboard_telemetry_context(driver1, driver2, lap1, lap2, tel1=None, tel2=None, lap_label="selected laps"):
    lines = ["=== SELECTED LAP AND TELEMETRY CONTEXT ===", f"Selected dashboard laps: {lap_label}."]
    lines.append(_lap_summary(lap1, driver1))
    lines.append(_lap_summary(lap2, driver2))
    lines.append(_get_lap_time_comparison(driver1, driver2, lap1, lap2))
    if tel1 is None or tel2 is None:
        lines.append("No complete pair of telemetry traces is available. Do not infer a lap delta or telemetry advantage.")
        return "\n".join(lines)
    lines.append(_trace_summary(tel1, driver1, lap1.get("lap_number")))
    lines.append(_trace_summary(tel2, driver2, lap2.get("lap_number")))
    lines.append(_get_trace_comparison_windows(driver1, driver2, tel1, tel2))
    quality1 = tel1.attrs.get("quality", {})
    quality2 = tel2.attrs.get("quality", {})
    if quality1.get("has_position") and quality2.get("has_position"):
        lines.append("Both traces include aligned OpenF1 location samples; map coordinates are approximate and session-specific.")
    else:
        lines.append(
            "At least one trace lacks complete location alignment. No GPS or "
            "track-position advantage is asserted; progress windows use the "
            "approximate distance integrated from car speed."
        )
    return "\n".join(lines)


def _gather_session_context(session, session_type, driver1, driver2, selected_lap_context=None):
    """Summarize validated bundle data and optional selected-lap traces."""
    lines = [
        "=== DRIVER AND TEAM ASSIGNMENTS ===",
        "Source: OpenF1 driver metadata for this session.",
    ]
    for row in session.drivers.to_dict("records"):
        lines.append(f"{row.get('abbreviation')} ({row.get('full_name')}) → {row.get('team_name') or 'team unavailable'}; car {row.get('driver_number')}.")
    lines.extend([
        f"Session: {session.ref.year} {session.ref.event_name}, {session_type}.",
        f"Session source: OpenF1 session key {session.ref.session_key}; historical archive, session end {session.ref.date_end or 'unavailable'}.",
        _get_field_summary(session), _get_starting_grid(session), _get_field_tyre_strategy(session),
        _get_teammate_benchmark(session, driver1), _get_teammate_benchmark(session, driver2),
    ])
    if not session.pits.empty:
        lines.append("=== PIT VISITS ===")
        for row in session.pits.sort_values(["lap_number", "abbreviation"]).to_dict("records"):
            duration = row.get("stop_duration")
            lane = row.get("lane_duration")
            note = f"stationary service {_fmt_seconds(duration)}" if pd.notna(duration) else f"pit-lane total {_fmt_seconds(lane)}" if pd.notna(lane) else "duration unavailable"
            lines.append(f"{row.get('abbreviation')} lap {row.get('lap_number')}: {note}; source {row.get('source')}.")
    if not session.laps.empty:
        lines.append("=== COMPARISON LAP RECORDS ===")
        for driver in (driver1, driver2):
            driver_laps = session.laps[session.laps["abbreviation"] == driver].copy()
            valid = driver_laps.dropna(subset=["lap_duration"])
            clean = valid[(~valid["pit_out"].fillna(False)) & (~valid["pit_in"].fillna(False))]
            lines.append(f"{driver}: {len(valid)} valid timed laps, {len(clean)} laps not marked pit-in/out; best {_fmt_seconds(valid['lap_duration'].min()) if not valid.empty else 'N/A'}, clean median {_fmt_seconds(clean['lap_duration'].median()) if not clean.empty else 'N/A'}.")
        if selected_lap_context:
            lines.append(_get_dashboard_telemetry_context(
                driver1, driver2, selected_lap_context.get("lap1"), selected_lap_context.get("lap2"),
                selected_lap_context.get("tel1"), selected_lap_context.get("tel2"),
                selected_lap_context.get("label", "selected laps"),
            ))
    else:
        lines.append("Lap timing is unavailable; do not infer lap or sector performance.")
    narrative = _get_session_narrative(session)
    weather = _weather_summary(session)
    if narrative:
        lines.append(narrative)
    if weather:
        lines.append(weather)
    notes = session.quality.get("notes", [])
    lines.append("=== DATA QUALITY AND PROVENANCE ===")
    lines.append("Endpoint states: " + ", ".join(
        f"{name}={details.get('state', 'unknown')} ({details.get('source', 'source unavailable')})"
        for name, details in session.quality.get("endpoints", {}).items()
    ))
    for note in notes:
        lines.append(f"Limit: {note}")
    lines.append("Race-control lap status is heuristic unless the lap record explicitly identifies its source. Results/grid and optional Jolpica supplements are labeled by source. Missing fields remain unknown.")
    return "\n".join(line for line in lines if line)
