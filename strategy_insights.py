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
    """Describe stint transitions using the same stint records as the plan."""
    stints = build_driver_stints(session, driver)
    laps = _driver_laps(session, driver)
    provider_stints = getattr(session, "stints", pd.DataFrame())
    has_provider_stints = (
        not provider_stints.empty
        and "abbreviation" in provider_stints
        and not provider_stints.loc[provider_stints["abbreviation"] == driver].empty
    )
    source = "openf1.stints" if has_provider_stints else "laps.stint_transition"
    events = []
    for previous, following in zip(stints, stints[1:]):
        pit_lap = _number(previous.get("end_lap"))
        next_start = _number(following.get("start_lap"))
        if pit_lap is None or next_start is None or next_start <= pit_lap:
            continue
        events.append(_pit_impact(
            laps, int(pit_lap), previous.get("compound"), following.get("compound"),
            source=source,
        ))
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
