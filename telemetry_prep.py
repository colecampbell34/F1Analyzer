"""Shared selected-lap telemetry preparation for dashboard callbacks."""
import os
import threading
from concurrent.futures import Future
from functools import lru_cache

import pandas as pd

from callbacks_shared import _has_valid_lap, _pick_driver_lap
from data import get_best_lap, get_shared_data

try:
    TELEMETRY_PREP_CACHE_MAXSIZE = int(os.getenv('TELEMETRY_PREP_CACHE_MAXSIZE', '8'))
except ValueError:
    TELEMETRY_PREP_CACHE_MAXSIZE = 8
TELEMETRY_PREP_CACHE_MAXSIZE = max(2, min(24, TELEMETRY_PREP_CACHE_MAXSIZE))
_PREPARATION_FUTURES = {}
_PREPARATION_FUTURES_LOCK = threading.Lock()


def _has_position_data(telemetry):
    """Return whether a telemetry frame can support a circuit-position view."""
    required = ('X', 'Y', 'Distance', 'Time')
    if telemetry is None or telemetry.empty or not all(column in telemetry.columns for column in required):
        return False
    return len(telemetry.dropna(subset=list(required))) >= 12


def _validate_trace_data(telemetry):
    """Reject empty/partial car traces before graph code raises a KeyError."""
    required = ('Time', 'Distance', 'Speed', 'Throttle', 'Brake', 'nGear')
    if telemetry is None or telemetry.empty or not all(column in telemetry.columns for column in required):
        return False
    return len(telemetry.dropna(subset=['Time', 'Distance', 'Speed'])) >= 12


def _telemetry_with_distance(lap, drop_xy_time=False, session=None):
    """Return the richest usable trace for one lap.

    ``get_telemetry`` merges car and position channels. On some historical
    laps the position channel is incomplete even though car data is present.
    In that case the speed/throttle/gear analysis should still work; position
    specific views can check ``_has_position_data`` and explain the limitation.
    """
    try:
        tel = lap.get_telemetry().add_distance()
    except Exception as exc:
        try:
            # FastF1 recommends car data where a merged position trace is not
            # required. It is lighter and survives sessions with partial GPS.
            tel = lap.get_car_data().add_distance()
        except Exception as car_exc:
            raise ValueError("Telemetry data is not available for this selected lap.") from car_exc
        if not _validate_trace_data(tel):
            raise ValueError("Telemetry data is incomplete for this selected lap.") from exc

    if not _validate_trace_data(tel):
        raise ValueError("Telemetry data is incomplete for this selected lap.")

    if drop_xy_time:
        required_cols = ['X', 'Y', 'Distance', 'Time']
        if all(col in tel.columns for col in required_cols):
            tel = tel.dropna(subset=required_cols)
        else:
            tel = pd.DataFrame(columns=tel.columns)

    if not tel.empty:
        tel = tel.copy()
        if 'Distance' in tel.columns:
            tel['Distance'] -= tel['Distance'].min()
    return tel


def _copy_comparison_payload(payload, drop_xy_time=False):
    comparison = dict(payload)
    for key in ('tel1', 'tel2'):
        tel = comparison[key].copy()
        if drop_xy_time:
            position_cols = ['X', 'Y', 'Distance', 'Time']
            if all(column in tel.columns for column in position_cols):
                tel = tel.dropna(subset=position_cols).copy()
            else:
                tel = tel.iloc[0:0].copy()
            if not tel.empty:
                tel['Distance'] -= tel['Distance'].min()
        comparison[key] = tel
    return comparison


def _normalize_lap_number(value):
    if value in (None, '', 'fastest'):
        return None
    return int(value)


@lru_cache(maxsize=TELEMETRY_PREP_CACHE_MAXSIZE)
def _prepare_selected_lap_comparison_cached(
    year,
    race,
    session_type,
    driver1,
    driver2,
    d1_mode='fastest',
    d2_mode='fastest',
    d1_lap_num=None,
    d2_lap_num=None,
):
    """Load shared session data, pick requested laps, and cache full telemetry frames."""
    params = {
        'year': year,
        'race': race,
        'session_type': session_type,
        'driver1': driver1,
        'driver2': driver2,
    }
    session, d1, d2, lbl1, lbl2, c1, c2 = get_shared_data(params, laps=True, telemetry=True)
    lap1 = _pick_driver_lap(session, d1, d1_mode, d1_lap_num, get_best_lap)
    lap2 = _pick_driver_lap(session, d2, d2_mode, d2_lap_num, get_best_lap)

    if not _has_valid_lap(lap1, pd):
        raise ValueError(f"{d1} did not set a valid lap.")
    if not _has_valid_lap(lap2, pd):
        raise ValueError(f"{d2} did not set a valid lap.")

    tel1 = _telemetry_with_distance(lap1, drop_xy_time=False, session=session)
    tel2 = _telemetry_with_distance(lap2, drop_xy_time=False, session=session)

    return {
        'session': session,
        'd1': d1,
        'd2': d2,
        'lbl1': lbl1,
        'lbl2': lbl2,
        'c1': c1,
        'c2': c2,
        'lap1': lap1,
        'lap2': lap2,
        'tel1': tel1,
        'tel2': tel2,
    }


def prepare_selected_lap_comparison(
    params,
    d1_mode='fastest',
    d2_mode='fastest',
    d1_lap_num=None,
    d2_lap_num=None,
    drop_xy_time=False,
    require_position=False,
):
    """Load shared session data, pick requested laps, and return normalized telemetry."""
    cache_args = (
        int(params['year']),
        str(params['race']),
        str(params['session_type']),
        str(params['driver1']),
        str(params['driver2']),
        str(d1_mode or 'fastest'),
        str(d2_mode or 'fastest'),
        _normalize_lap_number(d1_lap_num),
        _normalize_lap_number(d2_lap_num),
    )
    with _PREPARATION_FUTURES_LOCK:
        future = _PREPARATION_FUTURES.get(cache_args)
        leader = future is None
        if leader:
            future = Future()
            _PREPARATION_FUTURES[cache_args] = future

    if leader:
        try:
            payload = _prepare_selected_lap_comparison_cached(*cache_args)
        except BaseException as exc:
            future.set_exception(exc)
            raise
        else:
            future.set_result(payload)
        finally:
            with _PREPARATION_FUTURES_LOCK:
                if _PREPARATION_FUTURES.get(cache_args) is future:
                    _PREPARATION_FUTURES.pop(cache_args, None)
    else:
        payload = future.result()

    comparison = _copy_comparison_payload(payload, drop_xy_time=drop_xy_time)
    if require_position and not (
        _has_position_data(comparison['tel1']) and _has_position_data(comparison['tel2'])
    ):
        raise ValueError(
            "Track-position data is unavailable for one of the selected laps. "
            "Try each driver's fastest lap or use the telemetry trace instead."
        )
    return comparison


def get_selected_lap_cache_stats():
    return _prepare_selected_lap_comparison_cached.cache_info()._asdict()
