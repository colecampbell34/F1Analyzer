"""Dashboard-facing data facade for normalized historical F1 sessions."""
from __future__ import annotations

import colorsys
from concurrent.futures import Future, ThreadPoolExecutor
from copy import deepcopy
from functools import lru_cache
import hashlib
import logging
import os
import re
import threading
import time

import pandas as pd

from runtime import is_serverless
from session_data import (
    SessionBundle,
    _classify_race_control_event,
    get_schedule as _get_schedule,
    latest_completed_race,
    load_session_bundle,
)


TEAM_COLOR_FALLBACKS = {
    "mercedes": "#00D7B6", "mclaren": "#F47600", "redbull": "#4781D7",
    "redbullracing": "#4781D7", "ferrari": "#ED1131", "alpine": "#00A1E8",
    "alpinef1team": "#00A1E8", "williams": "#1868DB", "haas": "#9C9FA2",
    "haasf1team": "#9C9FA2", "audi": "#F50537", "racingbulls": "#6C98FF",
    "rb": "#6C98FF", "rbf1team": "#6C98FF", "astonmartin": "#229971",
    "alphatauri": "#2B4562", "alfaromeo": "#900000", "sauber": "#52E252",
    "stakesauber": "#52E252", "kicksauber": "#52E252", "renault": "#FFF500",
    "tororosso": "#469BFF", "racingpoint": "#F596C8", "forceindia": "#F596C8",
}
_COLOR_PALETTE = ("#00D7B6", "#F47600", "#4781D7", "#ED1131", "#00A1E8", "#1868DB", "#9C9FA2", "#F50537", "#6C98FF", "#229971", "#B46CFF", "#FFD166")
_SECONDARY_COLORS = ("#FFD166", "#B46CFF", "#00D7B6")
_PRELOAD_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="session-preload")
_PRELOAD_LOCK = threading.RLock()
_PRELOAD_JOBS: dict[tuple, dict] = {}
_PRELOAD_FUTURES: dict[tuple, Future] = {}
_MAX_PRELOAD_JOBS = 24


def is_qualifying(session_type):
    value = str(session_type or "").casefold()
    return "qualifying" in value or "shootout" in value


def is_race(session_type):
    return str(session_type or "").casefold() in {"race", "sprint", "sprint race"}


def is_practice(session_type):
    value = str(session_type or "").casefold()
    return "practice" in value or value.startswith("fp")


def _normalize_color(value):
    if value is None or pd.isna(value):
        return None
    color = str(value).strip().removeprefix("#")
    if len(color) == 3 and all(char in "0123456789abcdefABCDEF" for char in color):
        color = "".join(char * 2 for char in color)
    if len(color) != 6 or not all(char in "0123456789abcdefABCDEF" for char in color):
        return None
    return f"#{color.upper()}"


def _team_color_key(team_name):
    return re.sub(r"[^a-z0-9]+", "", str(team_name or "").casefold())


def _stable_fallback_color(identifier):
    digest = hashlib.sha1(str(identifier or "unknown").encode("utf-8")).hexdigest()
    return _COLOR_PALETTE[int(digest[:2], 16) % len(_COLOR_PALETTE)]


def _rgb(color):
    normalized = _normalize_color(color)
    if not normalized:
        return None
    return tuple(int(normalized[index:index + 2], 16) for index in (1, 3, 5))


def _colors_similar(first, second):
    a, b = _rgb(first), _rgb(second)
    if not a or not b:
        return first == second
    if a == b:
        return True
    hsv_a = colorsys.rgb_to_hsv(*(channel / 255 for channel in a))
    hsv_b = colorsys.rgb_to_hsv(*(channel / 255 for channel in b))
    hue_gap = abs(hsv_a[0] - hsv_b[0])
    return min(hue_gap, 1 - hue_gap) <= 28 / 360 and abs(hsv_a[1] - hsv_b[1]) <= 0.48 and abs(hsv_a[2] - hsv_b[2]) <= 0.42


def _distinct_comparison_colors(primary, secondary):
    if not _colors_similar(primary, secondary):
        return primary, secondary
    candidate = next((color for color in _SECONDARY_COLORS if not _colors_similar(primary, color)), "#FFFFFF")
    return primary, candidate


def distinct_plot_colors(colors):
    resolved = []
    candidates = _SECONDARY_COLORS + _COLOR_PALETTE + ("#FFFFFF",)
    for color in colors:
        if not any(_colors_similar(color, existing) for existing in resolved):
            resolved.append(color)
        else:
            resolved.append(next((candidate for candidate in candidates if not any(_colors_similar(candidate, existing) for existing in resolved)), "#FFFFFF"))
    return resolved


def resolve_team_color(team_name, session=None, raw_color=None, fallback_identifier=None):
    normalized = _normalize_color(raw_color)
    if normalized:
        return normalized
    return TEAM_COLOR_FALLBACKS.get(_team_color_key(team_name)) or _stable_fallback_color(fallback_identifier or team_name)


def _driver_row(session: SessionBundle, driver_abbr: str):
    if session is None or session.drivers.empty:
        return None
    rows = session.drivers[session.drivers["abbreviation"] == driver_abbr]
    return rows.iloc[0] if not rows.empty else None


def resolve_driver_color(driver_abbr, session):
    row = _driver_row(session, driver_abbr)
    return resolve_team_color(
        row.get("team_name") if row is not None else "",
        raw_color=row.get("team_colour") if row is not None else None,
        fallback_identifier=driver_abbr,
    )


def get_single_driver_color(driver_abbr, session):
    return resolve_driver_color(driver_abbr, session)


def background_preload_enabled():
    configured = os.getenv("ENABLE_BACKGROUND_PRELOAD")
    if configured is not None:
        return str(configured).strip().casefold() in {"1", "true", "yes", "on"}
    return not is_serverless()


@lru_cache(maxsize=12)
def get_event_schedule_cached(year):
    return tuple(_get_schedule(int(year)))


def get_event_schedule(year):
    return [dict(event) for event in get_event_schedule_cached(int(year))]


def get_latest_race_session_default(now=None, first_year=2023):
    latest = latest_completed_race(now=now)
    return latest if latest and latest["year"] >= int(first_year) else None


def _profile_key(year, race, session_name, laps, telemetry, weather, messages, results, strategy, race_context, circuit):
    return (int(year), str(race), str(session_name), bool(laps), bool(telemetry), bool(weather), bool(messages), bool(results), bool(strategy), bool(race_context), bool(circuit))


def _clone_bundle(bundle: SessionBundle) -> SessionBundle:
    return SessionBundle(
        bundle.ref,
        *[frame.copy(deep=True) for frame in (
            bundle.drivers, bundle.results, bundle.grid, bundle.laps, bundle.stints,
            bundle.pits, bundle.weather, bundle.messages, bundle.positions,
            bundle.intervals, bundle.circuit_corners,
        )],
        quality=deepcopy(bundle.quality),
    )


@lru_cache(maxsize=16)
def _load_bundle_cached(year, race, session_name, laps=True, telemetry=False, weather=False, messages=False, results=True, strategy=False, race_context=False, circuit=False):
    from session_data import resolve_session_ref

    ref = resolve_session_ref(year, race, session_name)
    include_strategy = bool(strategy or weather)
    include_race = bool(race_context or messages)
    return load_session_bundle(
        ref,
        laps=bool(laps or telemetry or strategy or race_context),
        results=bool(results), strategy=include_strategy,
        race_context=include_race, circuit=bool(circuit),
    )


def _load_bundle(*args, **kwargs):
    return _clone_bundle(_load_bundle_cached(*args, **kwargs))


def _profile_from_key(key):
    return ", ".join(name for name, enabled in zip(("laps", "telemetry", "weather", "messages", "results", "strategy", "race context", "circuit"), key[3:]) if enabled) or "metadata"


def _preload_key(year, race, session_name, **kwargs):
    return _profile_key(
        year, race, session_name,
        kwargs.get("laps", True), kwargs.get("telemetry", False),
        kwargs.get("weather", False), kwargs.get("messages", False),
        kwargs.get("results", True), kwargs.get("strategy", False),
        kwargs.get("race_context", False), kwargs.get("circuit", False),
    )


def _job_view(key, job):
    return {
        "year": key[0], "race": key[1], "session": key[2],
        "profile": _profile_from_key(key[3:]), "status": job.get("status", "idle"),
        "started_at": job.get("started_at"), "finished_at": job.get("finished_at"),
        "error": job.get("error"), "mode": "on-demand" if is_serverless() else "background",
    }


def _run_preload(key):
    year, race, session_name, laps, telemetry, weather, messages, results, strategy, race_context, circuit = key
    try:
        _load_bundle(year, race, session_name, laps, telemetry, weather, messages, results, strategy, race_context, circuit)
        status, error = "ready", None
    except Exception as exc:
        status, error = "error", type(exc).__name__
        logging.warning("session_preload_failed year=%s race=%s session=%s error_type=%s", year, race, session_name, type(exc).__name__)
    with _PRELOAD_LOCK:
        job = _PRELOAD_JOBS.setdefault(key, {})
        job.update(status=status, finished_at=time.time(), error=error)
    return status


def preload_session(year, race, session_name, laps=True, telemetry=False, weather=False, messages=False, results=True, strategy=False, race_context=False, circuit=False):
    key = _preload_key(year, race, session_name, laps=laps, telemetry=telemetry, weather=weather, messages=messages, results=results, strategy=strategy, race_context=race_context, circuit=circuit)
    if not background_preload_enabled():
        return None
    with _PRELOAD_LOCK:
        existing = _PRELOAD_FUTURES.get(key)
        if existing and not existing.done():
            return existing
        _PRELOAD_JOBS[key] = {"status": "queued", "started_at": time.time(), "finished_at": None, "error": None}
        future = _PRELOAD_EXECUTOR.submit(_run_preload, key)
        _PRELOAD_FUTURES[key] = future
        while len(_PRELOAD_JOBS) > _MAX_PRELOAD_JOBS:
            oldest = next(iter(_PRELOAD_JOBS))
            if oldest in _PRELOAD_FUTURES and not _PRELOAD_FUTURES[oldest].done():
                break
            _PRELOAD_JOBS.pop(oldest, None)
            _PRELOAD_FUTURES.pop(oldest, None)
        return future


def load_session_with_preload(year, race, session_name, laps=True, telemetry=False, weather=False, messages=False, results=True, strategy=False, race_context=False, circuit=False):
    args = (int(year), str(race), str(session_name), bool(laps), bool(telemetry), bool(weather), bool(messages), bool(results), bool(strategy), bool(race_context), bool(circuit))
    session = _load_bundle(*args)
    key = args
    with _PRELOAD_LOCK:
        _PRELOAD_JOBS[key] = {"status": "ready", "started_at": time.time(), "finished_at": time.time(), "error": None}
    return session


def get_preload_status(year, race, session_name, laps=True, telemetry=False, weather=False, messages=False, results=True, strategy=False, race_context=False, circuit=False):
    key = _preload_key(year, race, session_name, laps=laps, telemetry=telemetry, weather=weather, messages=messages, results=results, strategy=strategy, race_context=race_context, circuit=circuit)
    with _PRELOAD_LOCK:
        job = _PRELOAD_JOBS.get(key)
        if not job:
            return {"status": "idle", "profile": _profile_from_key(key[3:]), "mode": "on-demand" if is_serverless() else "background"}
        return _job_view(key, job)


def get_preload_kwargs_for_tab(active_tab):
    return {
        "tab-telemetry": {"laps": True, "telemetry": True},
        "tab-trackmap": {"laps": True, "telemetry": True, "circuit": True},
        "tab-strategy": {"laps": True, "weather": True, "strategy": True},
        "tab-racepace": {"laps": True, "weather": True, "strategy": True, "race_context": True},
    }.get(active_tab, {"laps": True})


def get_preload_status_for_tab(params, active_tab):
    if not params:
        return {"status": "idle", "mode": "on-demand" if is_serverless() else "background"}
    return get_preload_status(params["year"], params["race"], params["session_type"], **get_preload_kwargs_for_tab(active_tab))


def ensure_preload_for_tab(params, active_tab):
    if not params:
        return {"status": "idle", "mode": "on-demand" if is_serverless() else "background"}
    kwargs = get_preload_kwargs_for_tab(active_tab)
    current = get_preload_status(params["year"], params["race"], params["session_type"], **kwargs)
    if background_preload_enabled() and current.get("status") == "idle":
        preload_session(params["year"], params["race"], params["session_type"], **kwargs)
    return get_preload_status_for_tab(params, active_tab)


def get_preload_registry_snapshot():
    with _PRELOAD_LOCK:
        return [_job_view(key, job) for key, job in list(_PRELOAD_JOBS.items())[-_MAX_PRELOAD_JOBS:]]


def get_cache_stats():
    from session_data import provider_stats
    from shared_cache import get_stats

    try:
        from telemetry_prep import get_selected_lap_cache_stats
        selected_lap = get_selected_lap_cache_stats()
    except Exception:
        selected_lap = {}
    return {
        "cache_size_bytes": 0,
        "session_cache": _load_bundle_cached.cache_info()._asdict(),
        "summary_cache": _load_bundle_cached.cache_info()._asdict(),
        "provider": provider_stats(),
        "selected_lap_cache": selected_lap,
        "shared_cache": get_stats(),
    }


def load_session_summary(year, race, session_name, include_laps=False):
    return load_session_with_preload(year, race, session_name, laps=bool(include_laps), telemetry=False, results=True)


@lru_cache(maxsize=32)
def _load_drivers_fast(year, race, session_name):
    try:
        return tuple(get_driver_info(load_session_summary(year, race, session_name, include_laps=False)))
    except Exception as exc:
        logging.warning("driver_metadata_load_failed year=%s race=%s session=%s error_type=%s", year, race, session_name, type(exc).__name__)
        return ()


def get_driver_info(session):
    drivers = session.drivers.copy(deep=True) if isinstance(session, SessionBundle) else pd.DataFrame()
    if drivers.empty:
        return []
    result_positions = {}
    if not session.results.empty:
        result_positions = dict(zip(session.results["driver_number"], session.results["position"]))
    if not session.laps.empty:
        fastest = session.laps.dropna(subset=["lap_duration"]).groupby("driver_number")["lap_duration"].min().to_dict()
    else:
        fastest = {}
    drivers["result_position"] = drivers["driver_number"].map(result_positions)
    drivers["fastest_lap"] = drivers["driver_number"].map(fastest)
    drivers = drivers.sort_values(["result_position", "fastest_lap", "abbreviation"], na_position="last", kind="stable")
    return [{
        "abbr": row["abbreviation"], "name": row["full_name"], "team": row["team_name"],
        "color": resolve_team_color(row["team_name"], raw_color=row["team_colour"], fallback_identifier=row["abbreviation"]),
        "driver_number": row["driver_number"],
    } for _, row in drivers.iterrows()]


def get_teammate_from_info(driver_abbr, driver_info):
    driver_team = next((row.get("team") for row in driver_info if row.get("abbr") == driver_abbr), None)
    if not driver_team:
        return None
    return next((row.get("abbr") for row in driver_info if row.get("team") == driver_team and row.get("abbr") != driver_abbr), None)


def get_best_lap(session, driver_abbr):
    if not isinstance(session, SessionBundle) or session.laps.empty:
        return None
    driver_laps = session.laps[
        (session.laps["abbreviation"] == driver_abbr)
        & pd.to_numeric(session.laps["lap_duration"], errors="coerce").notna()
    ].copy()
    if driver_laps.empty:
        return None
    if is_qualifying(session.ref.session_name) and not session.results.empty:
        result = session.results[session.results["abbreviation"] == driver_abbr]
        if not result.empty:
            row = result.iloc[0]
            best = row.get("best_lap_time")
            if best is not None and pd.notna(best):
                diffs = (driver_laps["lap_duration"].astype(float) - float(best)).abs()
                if not diffs.empty and diffs.min() <= 0.05:
                    return driver_laps.loc[diffs.idxmin()].copy()
    return driver_laps.sort_values("lap_duration", kind="stable").iloc[0].copy()


def _status_laps(bundle: SessionBundle) -> tuple[set, set, set, set]:
    """Return explicit race-control status laps without timestamp expansion."""
    safety, vsc, red, yellow = set(), set(), set(), set()
    if bundle.messages.empty:
        return safety, vsc, red, yellow
    message_records = bundle.messages.dropna(subset=["timestamp"]).sort_values("timestamp").to_dict("records")
    statuses = {"safety": safety, "vsc": vsc, "red": red, "yellow": yellow}

    for event in message_records:
        kind, action = _classify_race_control_event(event)
        if kind is None or action is None:
            continue
        explicit_lap = event.get("lap_number")
        if action in {"start", "point"} and pd.notna(explicit_lap):
            statuses[kind].add(int(explicit_lap))

    # Conflicting status records on one lap produce one plotted status.
    safety.difference_update(red)
    vsc.difference_update(red | safety)
    return safety, vsc, red, yellow


def get_track_status_events(session):
    if not isinstance(session, SessionBundle):
        return set(), set(), set(), set()
    return _status_laps(session)


def _compute_labels_colors(year, race, session_type, d1, d2):
    session = load_session_summary(year, race, session_type, include_laps=False)
    color1, color2 = _distinct_comparison_colors(resolve_driver_color(d1, session), resolve_driver_color(d2, session))

    def label(driver):
        rows = session.results[session.results["abbreviation"] == driver] if not session.results.empty else pd.DataFrame()
        position = pd.to_numeric(rows.iloc[0].get("position"), errors="coerce") if not rows.empty else None
        return f"{driver} (P{int(position)})" if position is not None and pd.notna(position) else driver

    return label(d1), label(d2), color1, color2


@lru_cache(maxsize=24)
def _cached_labels_colors(year, race, session_type, d1, d2):
    return _compute_labels_colors(year, race, session_type, d1, d2)


def get_shared_data(params, laps=True, telemetry=False, weather=False, messages=False, strategy=False, race_context=False, circuit=False):
    session = load_session_with_preload(
        params["year"], params["race"], params["session_type"],
        laps=laps, telemetry=telemetry, weather=weather, messages=messages,
        results=True, strategy=strategy, race_context=race_context, circuit=circuit,
    )
    labels = _cached_labels_colors(
        int(params["year"]), str(params["race"]), str(params["session_type"]),
        str(params["driver1"]), str(params["driver2"]),
    )
    return session, params["driver1"], params["driver2"], *labels


def session_summary_payload(year, race, session_name):
    session = load_session_summary(year, race, session_name, include_laps=False)
    return {
        "year": session.ref.year, "race": session.ref.event_name,
        "session": session.ref.session_name,
        "drivers": get_driver_info(session),
        "results": session.results[[column for column in ("abbreviation", "position", "team_name", "status", "source") if column in session.results]].to_dict("records"),
        "quality": session.quality,
    }
