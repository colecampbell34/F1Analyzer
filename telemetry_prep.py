"""Selected-lap preparation for OpenF1 traces and browser replay."""
from __future__ import annotations

from collections import OrderedDict
from concurrent.futures import Future
from datetime import date
import hashlib
import json
import logging
import os
import threading

import numpy as np
import pandas as pd

from callbacks_shared import _has_valid_lap, _pick_driver_lap
from data import load_session_with_preload, get_best_lap, resolve_driver_color, _distinct_comparison_colors
from session_data import ProviderError, get_selected_lap_trace


_CACHE_SCHEMA_VERSION = 3
try:
    _CACHE_MAXSIZE = max(2, min(24, int(os.getenv("TELEMETRY_PREP_CACHE_MAXSIZE", "8"))))
except ValueError:
    _CACHE_MAXSIZE = 8
_CACHE: OrderedDict[str, tuple[float, dict]] = OrderedDict()
_CACHE_LOCK = threading.RLock()
_PREPARATION_FUTURES: dict[str, Future] = {}
_PREPARATION_FUTURES_LOCK = threading.Lock()


def _trace_is_valid(trace: pd.DataFrame) -> bool:
    return trace is not None and not trace.empty and {"Time", "Distance", "Speed"}.issubset(trace.columns) and len(trace.dropna(subset=["Time", "Distance", "Speed"])) >= 6


def _has_position_data(trace: pd.DataFrame) -> bool:
    return trace is not None and not trace.empty and {"X", "Y", "Distance", "Time"}.issubset(trace.columns) and len(trace.dropna(subset=["X", "Y", "Distance", "Time"])) >= 12


def _cache_key(cache_args: tuple) -> str:
    raw = json.dumps([_CACHE_SCHEMA_VERSION, *cache_args], separators=(",", ":"), ensure_ascii=True)
    return "f1-analyzer:openf1-lap-comparison:v3:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _ttl_seconds(year: int) -> int:
    current = int(os.getenv("OPENF1_TELEMETRY_CURRENT_TTL_SECONDS", "21600"))
    historic = int(os.getenv("OPENF1_TELEMETRY_HISTORICAL_TTL_SECONDS", "2592000"))
    return max(300, min(31_536_000, current if year >= date.today().year else historic))


def _lap_wire(lap: pd.Series) -> dict:
    result = {}
    for key, value in lap.items():
        if isinstance(value, (list, dict)):
            result[str(key)] = value
        elif value is None or pd.isna(value):
            result[str(key)] = None
        elif isinstance(value, (pd.Timestamp,)):
            result[str(key)] = value.isoformat()
        elif isinstance(value, (bool, int, float, str)):
            result[str(key)] = value
        elif isinstance(value, np.generic):
            result[str(key)] = value.item()
        else:
            result[str(key)] = str(value)
    return result


def _trace_wire(trace: pd.DataFrame) -> dict:
    columns = [column for column in ("Time", "Distance", "Speed", "Throttle", "Brake", "nGear", "RPM", "DRS", "X", "Y") if column in trace]
    max_points = max(300, min(6000, int(os.getenv("OPENF1_TELEMETRY_MAX_POINTS", "3600"))))
    clipped = trace.loc[:, columns].copy()
    if len(clipped) > max_points:
        step = max(1, len(clipped) // max_points)
        clipped = clipped.iloc[::step].copy()
        if clipped.index[-1] != trace.index[-1]:
            clipped = pd.concat([clipped, trace.loc[[trace.index[-1]], columns]])
    values = {}
    for column in columns:
        if column == "Time":
            series = pd.to_timedelta(clipped[column], errors="coerce").dt.total_seconds()
        else:
            series = pd.to_numeric(clipped[column], errors="coerce")
        values[column] = [None if pd.isna(value) else float(value) for value in series]
    quality = trace.attrs.get("quality", {})
    return {"columns": columns, "values": values, "quality": quality}


def _trace_from_wire(payload: dict) -> pd.DataFrame:
    columns = payload.get("columns") if isinstance(payload, dict) else None
    values = payload.get("values") if isinstance(payload, dict) else None
    if not isinstance(columns, list) or not isinstance(values, dict):
        raise ValueError("invalid selected-lap telemetry cache")
    allowed = [name for name in columns if name in {"Time", "Distance", "Speed", "Throttle", "Brake", "nGear", "RPM", "DRS", "X", "Y"}]
    frame = pd.DataFrame({name: values.get(name, []) for name in allowed})
    if "Time" in frame:
        frame["Time"] = pd.to_timedelta(frame["Time"], unit="s", errors="coerce")
    for name in ("Distance", "Speed", "Throttle", "Brake", "nGear", "RPM", "DRS", "X", "Y"):
        if name not in frame:
            frame[name] = np.nan
        else:
            frame[name] = pd.to_numeric(frame[name], errors="coerce")
    frame.attrs["quality"] = payload.get("quality", {})
    if not _trace_is_valid(frame):
        raise ValueError("cached trace is missing usable speed samples")
    return frame


def _payload_to_wire(payload: dict) -> dict:
    return {
        "schema": _CACHE_SCHEMA_VERSION,
        "d1": payload["d1"], "d2": payload["d2"],
        "lbl1": payload["lbl1"], "lbl2": payload["lbl2"],
        "c1": payload["c1"], "c2": payload["c2"],
        "lap1": _lap_wire(payload["lap1"]), "lap2": _lap_wire(payload["lap2"]),
        "tel1": _trace_wire(payload["tel1"]), "tel2": _trace_wire(payload["tel2"]),
        "circuit_corners": payload.get("circuit_corners", []),
    }


def _payload_from_wire(payload: dict) -> dict:
    if not isinstance(payload, dict) or payload.get("schema") != _CACHE_SCHEMA_VERSION:
        raise ValueError("unknown selected-lap cache schema")
    required = ("d1", "d2", "lbl1", "lbl2", "c1", "c2", "lap1", "lap2", "tel1", "tel2")
    if not all(name in payload for name in required):
        raise ValueError("incomplete selected-lap cache")
    return {
        "session": None,
        "d1": str(payload["d1"]), "d2": str(payload["d2"]),
        "lbl1": str(payload["lbl1"]), "lbl2": str(payload["lbl2"]),
        "c1": str(payload["c1"]), "c2": str(payload["c2"]),
        "lap1": pd.Series(payload["lap1"]), "lap2": pd.Series(payload["lap2"]),
        "tel1": _trace_from_wire(payload["tel1"]), "tel2": _trace_from_wire(payload["tel2"]),
        "circuit_corners": payload.get("circuit_corners", []),
    }


def _copy_payload(payload: dict, *, drop_xy_time=False) -> dict:
    copy = dict(payload)
    copy["lap1"] = payload["lap1"].copy()
    copy["lap2"] = payload["lap2"].copy()
    for name in ("tel1", "tel2"):
        trace = payload[name].copy(deep=True)
        trace.attrs["quality"] = dict(payload[name].attrs.get("quality", {}))
        if drop_xy_time:
            if {"X", "Y", "Distance", "Time"}.issubset(trace.columns):
                trace = trace.dropna(subset=["X", "Y", "Distance", "Time"]).copy()
                trace.attrs["quality"] = dict(payload[name].attrs.get("quality", {}))
            else:
                trace = trace.iloc[0:0].copy()
        copy[name] = trace
    copy["circuit_corners"] = list(payload.get("circuit_corners") or [])
    return copy


def _lap_number(lap) -> int | None:
    try:
        value = lap.get("lap_number")
        return int(value) if pd.notna(value) else None
    except (TypeError, ValueError, AttributeError):
        return None


def _lap_candidates(session, driver) -> pd.DataFrame:
    laps = session.laps[session.laps["abbreviation"] == driver].copy()
    laps["lap_duration"] = pd.to_numeric(laps["lap_duration"], errors="coerce")
    return laps.dropna(subset=["lap_duration"]).sort_values("lap_duration", kind="stable")


def _selected_trace(session, driver, lap, mode) -> tuple[pd.Series, pd.DataFrame, bool]:
    lap = lap.copy()
    try:
        trace = get_selected_lap_trace(session.ref, lap, with_position=True)
        if not _trace_is_valid(trace):
            raise ProviderError("No usable speed trace was returned.", kind="incomplete", endpoint="car_data")
        return lap, trace, False
    except ProviderError as first_error:
        if mode != "fastest":
            raise
        excluded_number = _lap_number(lap)
        for _, candidate in _lap_candidates(session, driver).iterrows():
            if _lap_number(candidate) == excluded_number:
                continue
            try:
                # Car-only probes keep fallback request volume low. Retrieve
                # position samples only after a candidate has usable speed.
                candidate_trace = get_selected_lap_trace(session.ref, candidate, with_position=False)
                if _trace_is_valid(candidate_trace):
                    trace = get_selected_lap_trace(session.ref, candidate, with_position=True)
                    return candidate.copy(), trace, True
            except ProviderError:
                continue
        raise ProviderError(f"{driver}: no usable speed trace after checking valid laps.", kind="incomplete", endpoint="car_data") from first_error


def _label(driver, result_frame):
    rows = result_frame[result_frame["abbreviation"] == driver] if not result_frame.empty else pd.DataFrame()
    if rows.empty:
        return driver
    position = pd.to_numeric(rows.iloc[0].get("position"), errors="coerce")
    return f"{driver} (P{int(position)})" if pd.notna(position) else driver


def _build_comparison(cache_args: tuple) -> dict:
    year, race, session_type, driver1, driver2, d1_mode, d2_mode, d1_lap_num, d2_lap_num = cache_args
    session = load_session_with_preload(year, race, session_type, laps=True, telemetry=True, results=True)
    lap1 = _pick_driver_lap(session, driver1, d1_mode, d1_lap_num, get_best_lap)
    lap2 = _pick_driver_lap(session, driver2, d2_mode, d2_lap_num, get_best_lap)
    if not _has_valid_lap(lap1, pd):
        raise ProviderError(f"{driver1} has no valid timed lap in this session.", kind="incomplete", endpoint="laps")
    if not _has_valid_lap(lap2, pd):
        raise ProviderError(f"{driver2} has no valid timed lap in this session.", kind="incomplete", endpoint="laps")
    lap1, tel1, fallback1 = _selected_trace(session, driver1, lap1, d1_mode)
    lap2, tel2, fallback2 = _selected_trace(session, driver2, lap2, d2_mode)
    c1, c2 = _distinct_comparison_colors(resolve_driver_color(driver1, session), resolve_driver_color(driver2, session))
    lbl1, lbl2 = _label(driver1, session.results), _label(driver2, session.results)
    if fallback1:
        lbl1 = f"{lbl1} · telemetry L{_lap_number(lap1)}"
    if fallback2:
        lbl2 = f"{lbl2} · telemetry L{_lap_number(lap2)}"
    return {
        "session": None, "d1": driver1, "d2": driver2,
        "lbl1": lbl1, "lbl2": lbl2, "c1": c1, "c2": c2,
        "lap1": lap1, "lap2": lap2, "tel1": tel1, "tel2": tel2,
        # MultiViewer corners are available through the bundle, but their
        # frame has not passed a circuit-wide alignment check. Keep markers
        # heuristic until that evidence exists.
        "circuit_corners": [],
    }


def _local_get(key: str):
    with _CACHE_LOCK:
        item = _CACHE.get(key)
        if not item:
            return None
        expires, wire = item
        if expires <= pd.Timestamp.now(tz="UTC").timestamp():
            _CACHE.pop(key, None)
            return None
        _CACHE.move_to_end(key)
        return wire


def _local_set(key: str, wire: dict, ttl_seconds: int):
    with _CACHE_LOCK:
        _CACHE[key] = (pd.Timestamp.now(tz="UTC").timestamp() + ttl_seconds, wire)
        _CACHE.move_to_end(key)
        while len(_CACHE) > _CACHE_MAXSIZE:
            _CACHE.popitem(last=False)


def _shared_payload(key: str, cache_args: tuple) -> dict:
    from shared_cache import acquire_lock, get_json, is_configured, release_lock, set_json, wait_for_json

    shared_enabled = is_configured()
    lock_key = f"{key}:load-lock"
    lock_acquired = False
    if shared_enabled:
        wire = get_json(key)
        if wire is not None:
            try:
                return _payload_from_wire(wire)
            except (KeyError, TypeError, ValueError) as exc:
                logging.warning("[shared-cache] Ignoring invalid OpenF1 telemetry payload: %s", type(exc).__name__)
        lock_state = acquire_lock(lock_key, ttl_seconds=45)
        lock_acquired = lock_state is True
        if lock_state is False:
            wire = wait_for_json(key, float(os.getenv("OPENF1_TELEMETRY_LOCK_WAIT_SECONDS", "18")))
            if wire is not None:
                try:
                    return _payload_from_wire(wire)
                except (KeyError, TypeError, ValueError) as exc:
                    logging.warning("[shared-cache] Ignoring invalid waited OpenF1 payload: %s", type(exc).__name__)
    try:
        payload = _build_comparison(cache_args)
        wire = _payload_to_wire(payload)
        if shared_enabled:
            set_json(key, wire, _ttl_seconds(cache_args[0]))
        return _payload_from_wire(wire)
    finally:
        if lock_acquired:
            release_lock(lock_key)


def _normalize_lap_number(value):
    if value in (None, "", "fastest"):
        return None
    return int(value)


def prepare_selected_lap_comparison(
    params, d1_mode="fastest", d2_mode="fastest", d1_lap_num=None,
    d2_lap_num=None, drop_xy_time=False, require_position=False,
):
    """Return a cache-safe pair of selected, normalized telemetry traces."""
    cache_args = (
        int(params["year"]), str(params["race"]), str(params["session_type"]),
        str(params["driver1"]), str(params["driver2"]),
        str(d1_mode or "fastest"), str(d2_mode or "fastest"),
        _normalize_lap_number(d1_lap_num), _normalize_lap_number(d2_lap_num),
    )
    key = _cache_key(cache_args)
    wire = _local_get(key)
    if wire is not None:
        payload = _payload_from_wire(wire)
    else:
        with _PREPARATION_FUTURES_LOCK:
            future = _PREPARATION_FUTURES.get(key)
            leader = future is None
            if leader:
                future = Future()
                _PREPARATION_FUTURES[key] = future
        if leader:
            try:
                payload = _shared_payload(key, cache_args)
                wire = _payload_to_wire(payload)
                _local_set(key, wire, _ttl_seconds(cache_args[0]))
                future.set_result(wire)
            except BaseException as exc:
                future.set_exception(exc)
                raise
            finally:
                with _PREPARATION_FUTURES_LOCK:
                    if _PREPARATION_FUTURES.get(key) is future:
                        _PREPARATION_FUTURES.pop(key, None)
        else:
            wire = future.result()
        payload = _payload_from_wire(wire)

    comparison = _copy_payload(payload, drop_xy_time=drop_xy_time)
    if require_position and not (_has_position_data(comparison["tel1"]) and _has_position_data(comparison["tel2"])):
        raise ProviderError("Track-position samples are unavailable for one selected lap; speed telemetry remains usable.", kind="incomplete", endpoint="location")
    return comparison


def get_selected_lap_cache_stats():
    with _CACHE_LOCK:
        local = {"currsize": len(_CACHE), "maxsize": _CACHE_MAXSIZE}
    from shared_cache import get_stats
    return {"local": local, "shared": get_stats()}
