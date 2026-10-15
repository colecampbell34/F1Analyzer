"""Pure helpers for concise tyre-stint and pit-decision context."""
import math

import pandas as pd


def _compound(value):
    if value is None or pd.isna(value):
        return 'UNKNOWN'
    text = str(value).strip().upper()
    return text or 'UNKNOWN'


def _number(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _driver_laps(session, driver):
    """Return one driver's lap data in chronological order, or an empty frame."""
    try:
        laps = session.laps.pick_drivers(driver).copy()
    except Exception:
        return pd.DataFrame()
    if laps.empty or 'LapNumber' not in laps.columns:
        return pd.DataFrame()
    laps['LapNumber'] = pd.to_numeric(laps['LapNumber'], errors='coerce')
    laps = laps.dropna(subset=['LapNumber']).sort_values('LapNumber').reset_index(drop=True)
    return laps


def build_driver_stints(session, driver):
    """Return compact compound ranges for one driver without changing session data."""
    laps = _driver_laps(session, driver)
    if laps.empty:
        return []

    stints = []
    current = None
    for _, lap in laps.iterrows():
        lap_number = int(lap['LapNumber'])
        compound = _compound(lap.get('Compound'))
        stint_number = _number(lap.get('Stint'))
        key = (stint_number, compound)
        if current is None:
            current = {
                'compound': compound,
                'stint': stint_number,
                'start_lap': lap_number,
                'end_lap': lap_number,
            }
            continue
        # Stint identifiers are authoritative when supplied. Compound changes
        # and discontinuous lap numbers remain useful fallbacks for archives.
        same_stint = key == (current['stint'], current['compound'])
        contiguous = lap_number <= current['end_lap'] + 1
        if same_stint and contiguous:
            current['end_lap'] = lap_number
            continue
        stints.append(current)
        current = {
            'compound': compound,
            'stint': stint_number,
            'start_lap': lap_number,
            'end_lap': lap_number,
        }
    if current is not None:
        stints.append(current)
    return stints


def _is_pit_transition(current_lap, next_lap):
    """Detect a real service transition between adjacent completed laps.

    ``FreshTyre`` describes the set of tyres, not a per-lap transition. Some
    FastF1 feeds retain it for every lap in a stint, so it must never be used
    as a stand-alone pit-stop signal.
    """
    current_stint = _number(current_lap.get('Stint'))
    next_stint = _number(next_lap.get('Stint'))
    if current_stint is not None and next_stint is not None and next_stint > current_stint:
        return True
    current_compound = _compound(current_lap.get('Compound'))
    next_compound = _compound(next_lap.get('Compound'))
    if 'UNKNOWN' not in (current_compound, next_compound) and current_compound != next_compound:
        return True
    for lap, field in ((current_lap, 'PitInTime'), (next_lap, 'PitOutTime')):
        value = lap.get(field)
        if value is not None and not pd.isna(value):
            return True
    return False


def build_driver_pit_impacts(session, driver):
    """Return factual pit/compound changes with position context where available."""
    laps = _driver_laps(session, driver)
    if len(laps) < 2:
        return []

    events = []
    for index in range(len(laps) - 1):
        current = laps.iloc[index]
        following = laps.iloc[index + 1]
        if not _is_pit_transition(current, following):
            continue
        before = _number(current.get('Position'))
        after = _number(following.get('Position'))
        events.append({
            'pit_lap': int(current['LapNumber']),
            'from_compound': _compound(current.get('Compound')),
            'to_compound': _compound(following.get('Compound')),
            'position_before': int(before) if before is not None else None,
            'position_after': int(after) if after is not None else None,
        })
    return events
