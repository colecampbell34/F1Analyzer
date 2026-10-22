"""Pure helpers for normalized tyre-stint and pit-decision context."""
import math

import pandas as pd


def _compound(value):
    if value is None or pd.isna(value):
        return "UNAVAILABLE"
    text = str(value).strip().upper()
    return "UNAVAILABLE" if text in {"", "UNKNOWN", "NONE", "NAN", "NULL"} else text


def _number(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _driver_laps(session, driver):
    if session is None or session.laps.empty:
        return pd.DataFrame()
    laps = session.laps[session.laps["abbreviation"] == driver].copy(deep=True)
    laps["lap_number"] = pd.to_numeric(laps["lap_number"], errors="coerce")
    return laps.dropna(subset=["lap_number"]).sort_values("lap_number", kind="stable").reset_index(drop=True)


def build_driver_stints(session, driver):
    """Return provider stint records, with per-lap intervals as a fallback."""
    stints = getattr(session, "stints", pd.DataFrame())
    if not stints.empty:
        rows = stints[stints["abbreviation"] == driver].sort_values("stint_number", na_position="last", kind="stable")
        return [{
            "compound": _compound(row.get("compound")),
            "stint": _number(row.get("stint_number")),
            "start_lap": _number(row.get("lap_start")),
            "end_lap": _number(row.get("lap_end")),
            "tyre_age_at_start": _number(row.get("tyre_age_at_start")),
        } for _, row in rows.iterrows()]

    laps = _driver_laps(session, driver)
    if laps.empty:
        return []
    result, current = [], None
    for _, lap in laps.iterrows():
        lap_number = int(lap["lap_number"])
        compound = _compound(lap.get("compound"))
        stint_number = _number(lap.get("stint_number"))
        key = (stint_number, compound)
        if current is None:
            current = {"compound": compound, "stint": stint_number, "start_lap": lap_number, "end_lap": lap_number, "tyre_age_at_start": None}
        elif key == (current["stint"], current["compound"]) and lap_number <= current["end_lap"] + 1:
            current["end_lap"] = lap_number
        else:
            result.append(current)
            current = {"compound": compound, "stint": stint_number, "start_lap": lap_number, "end_lap": lap_number, "tyre_age_at_start": None}
    if current is not None:
        result.append(current)
    return result


def build_driver_pit_impacts(session, driver):
    """Join pit events to adjacent tyre stints and lap positions."""
    pit_records = getattr(session, "pits", pd.DataFrame())
    driver_pits = pit_records[pit_records["abbreviation"] == driver].copy() if not pit_records.empty else pd.DataFrame()
    stints = build_driver_stints(session, driver)
    laps = _driver_laps(session, driver)
    events = []
    if driver_pits.empty:
        # A compound/stint transition is still useful context when a pit
        # record was not published; keep its provenance explicit.
        for previous, following in zip(stints, stints[1:]):
            start_lap = _number(following.get("start_lap"))
            if start_lap is None:
                continue
            event_lap = int(start_lap) - 1
            events.append(_pit_impact(laps, event_lap, previous.get("compound"), following.get("compound"), source="stint_transition"))
        return events

    for _, pit in driver_pits.iterrows():
        pit_lap = _number(pit.get("lap_number"))
        if pit_lap is None:
            continue
        before_stint = next((item for item in reversed(stints) if _number(item.get("end_lap")) is not None and _number(item.get("end_lap")) < pit_lap), None)
        after_stint = next((item for item in stints if _number(item.get("start_lap")) is not None and _number(item.get("start_lap")) >= pit_lap), None)
        from_compound = before_stint.get("compound") if before_stint else "UNKNOWN"
        to_compound = after_stint.get("compound") if after_stint else from_compound
        events.append(_pit_impact(laps, int(pit_lap), from_compound, to_compound, source="openf1.pit"))
    return events


def _pit_impact(laps, pit_lap, from_compound, to_compound, *, source):
    before_row = laps[laps["lap_number"] == pit_lap] if not laps.empty else pd.DataFrame()
    after_row = laps[laps["lap_number"] == pit_lap + 1] if not laps.empty else pd.DataFrame()
    before = _number(before_row.iloc[-1].get("position")) if not before_row.empty else None
    after = _number(after_row.iloc[0].get("position")) if not after_row.empty else None
    return {
        "pit_lap": int(pit_lap), "from_compound": _compound(from_compound),
        "to_compound": _compound(to_compound),
        "position_before": int(before) if before is not None else None,
        "position_after": int(after) if after is not None else None,
        "source": source,
    }
