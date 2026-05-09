"""Small UX helpers for modes, glossary text, and comparison shortcuts."""
import math


VALID_EXPERIENCE_MODES = {"beginner", "intermediate", "engineer"}
DEFAULT_EXPERIENCE_MODE = "beginner"

EXPERIENCE_MODE_LABELS = {
    "beginner": "Beginner",
    "intermediate": "Intermediate",
    "engineer": "Engineer",
}

GLOSSARY = {
    "delta": "Time gap between two laps or drivers. Negative usually means the selected driver is ahead.",
    "telemetry": "Car data such as speed, throttle, brake, gear, RPM, position, and time.",
    "stint": "A run on one tyre set between pit stops.",
    "tyre_life": "How many laps a tyre set has completed. Older tyres normally lose grip.",
    "undercut": "Pitting earlier to use fresh tyres and gain time before a rival stops.",
    "overcut": "Staying out longer and gaining time before stopping later.",
    "vsc": "Virtual Safety Car, a controlled slow period that changes gaps and strategy.",
    "drs": "Drag Reduction System, which opens the rear wing in allowed zones to improve straight-line speed.",
    "degradation": "Lap-time loss as tyres age or overheat.",
    "dominance": "Track-map colouring that shows where one compared driver is faster than the other.",
}


def normalize_experience_mode(value, default=DEFAULT_EXPERIENCE_MODE):
    """Return a valid experience mode, falling back to beginner."""
    value = str(value or "").strip().lower()
    return value if value in VALID_EXPERIENCE_MODES else default


def get_glossary_definition(term):
    """Return a glossary definition for a term or an empty string."""
    return GLOSSARY.get(str(term or "").strip().lower(), "")


def empty_state_text(session_type=None, mode=DEFAULT_EXPERIENCE_MODE):
    """Return a concise empty-state instruction tuned to the active mode."""
    mode = normalize_experience_mode(mode)
    session_label = f" {session_type}" if session_type else ""
    if mode == "beginner":
        return (
            f"Pick a year, Grand Prix,{session_label} and two drivers, then update the dashboard. "
            "Start with Top 2 or Teammates if you are not sure who to compare."
        )
    if mode == "intermediate":
        return (
            "Select a session and driver pair, then update. Shortcuts can quickly choose common comparisons."
        )
    return (
        "Select a session and two drivers, then update the dashboard. First telemetry loads may take up to a minute."
    )


def _abbrs_from_driver_info(driver_info):
    return [
        d.get("abbr")
        for d in (driver_info or [])
        if isinstance(d, dict) and isinstance(d.get("abbr"), str) and len(d.get("abbr")) == 3
    ]


def _teammate_for(driver, driver_info):
    team = None
    for item in driver_info or []:
        if item.get("abbr") == driver:
            team = item.get("team")
            break
    if not team:
        return None
    for item in driver_info or []:
        if item.get("team") == team and item.get("abbr") != driver:
            return item.get("abbr")
    return None


def _results_order(results):
    import pandas as pd

    if results is None or getattr(results, "empty", True):
        return []
    try:
        df = results.copy()
        df["Position_Num"] = pd.to_numeric(df["Position"], errors="coerce")
        df = df.sort_values("Position_Num")
        return [
            row.get("Abbreviation")
            for _, row in df.iterrows()
            if isinstance(row.get("Abbreviation"), str) and len(row.get("Abbreviation")) == 3
        ]
    except Exception:
        return []


def _closest_classified_pair(results):
    import pandas as pd

    if results is None or getattr(results, "empty", True):
        return None
    try:
        df = results.copy()
        df["Position_Num"] = pd.to_numeric(df["Position"], errors="coerce")
        df = df.dropna(subset=["Position_Num"]).sort_values("Position_Num")
        candidates = []
        for _, row in df.iterrows():
            abbr = row.get("Abbreviation")
            raw_time = row.get("Time")
            if not isinstance(abbr, str) or len(abbr) != 3:
                continue
            if pd.isna(raw_time) or not hasattr(raw_time, "total_seconds"):
                continue
            candidates.append((abbr, float(raw_time.total_seconds())))
        if len(candidates) < 2:
            return None
        best_pair = None
        best_gap = math.inf
        for left, right in zip(candidates, candidates[1:]):
            gap = abs(right[1] - left[1])
            if gap < best_gap:
                best_gap = gap
                best_pair = (left[0], right[0])
        return best_pair
    except Exception:
        return None


def get_comparison_shortcut_pair(shortcut, driver_info, current_driver1=None, current_driver2=None, results=None):
    """Resolve a shortcut id to a safe pair of driver abbreviations."""
    shortcut = str(shortcut or "").strip().lower()
    abbrs = _results_order(results) or _abbrs_from_driver_info(driver_info)
    if len(abbrs) < 2:
        return None, None

    if shortcut == "teammates":
        primary = current_driver1 if current_driver1 in abbrs else abbrs[0]
        mate = _teammate_for(primary, driver_info)
        if mate:
            return primary, mate
        if current_driver2 in abbrs:
            mate = _teammate_for(current_driver2, driver_info)
            if mate:
                return current_driver2, mate

    if shortcut == "podium":
        podium = abbrs[:3]
        if len(podium) >= 2:
            return podium[0], podium[1]

    if shortcut == "closest":
        pair = _closest_classified_pair(results)
        if pair:
            return pair

    return abbrs[0], abbrs[1]
