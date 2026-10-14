"""Shared selected-lap telemetry preparation for dashboard callbacks."""
import hashlib
import json
import logging
import os
import threading
from concurrent.futures import Future
from datetime import date
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
_SHARED_CACHE_SCHEMA_VERSION = 1
_SHARED_TRACE_COLUMNS = ('Time', 'Distance', 'Speed', 'Throttle', 'Brake', 'nGear', 'RPM', 'X', 'Y')


def _has_position_data(telemetry):
    """Return whether a telemetry frame can support a circuit-position view."""
    required = ('X', 'Y', 'Distance', 'Time')
    if telemetry is None or telemetry.empty or not all(column in telemetry.columns for column in required):
        return False
    return len(telemetry.dropna(subset=list(required))) >= 12


def _validate_trace_data(telemetry):
    """Return whether a trace has the minimum data for a useful speed chart.

    Brake, throttle, gear and GPS are valuable additions, but FastF1 can omit
    one or more of them for an otherwise useful historical lap.  Treating
    those optional channels as mandatory made the entire Telemetry tab fail.
    """
    required = ('Time', 'Distance', 'Speed')
    if telemetry is None or telemetry.empty or not all(column in telemetry.columns for column in required):
        return False
    return len(telemetry.dropna(subset=list(required))) >= 6


def _normalize_trace_data(telemetry):
    """Make optional chart channels explicit without inventing telemetry."""
    tel = telemetry.copy()
    tel['Time'] = pd.to_timedelta(tel['Time'], errors='coerce')
    for column in ('Distance', 'Speed', 'Throttle', 'Brake', 'nGear', 'RPM', 'X', 'Y'):
        if column in tel.columns:
            tel[column] = pd.to_numeric(tel[column], errors='coerce')
    tel = tel.dropna(subset=['Time', 'Distance', 'Speed']).copy()
    for column in ('Throttle', 'Brake', 'nGear', 'RPM'):
        if column not in tel.columns:
            tel[column] = float('nan')
    return tel


def _telemetry_with_distance(lap, drop_xy_time=False, session=None):
    """Return the richest usable trace for one lap.

    ``get_telemetry`` merges car and position channels. On some historical
    laps the position channel is incomplete even though car data is present.
    In that case the speed/throttle/gear analysis should still work; position
    specific views can check ``_has_position_data`` and explain the limitation.
    """
    merged_error = None
    try:
        tel = lap.get_telemetry().add_distance()
    except Exception as exc:
        merged_error = exc
        tel = None

    if not _validate_trace_data(tel):
        try:
            # FastF1 recommends car data where a merged position trace is not
            # required. It is lighter and survives sessions with partial GPS.
            tel = lap.get_car_data().add_distance()
        except Exception as car_exc:
            raise ValueError("No usable speed trace is available for this selected lap.") from car_exc

    if not _validate_trace_data(tel):
        raise ValueError("No usable speed trace is available for this selected lap.") from merged_error

    tel = _normalize_trace_data(tel)

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


def _shared_cache_key(cache_args):
    encoded = json.dumps(cache_args, separators=(',', ':'), ensure_ascii=True).encode('utf-8')
    digest = hashlib.sha256(encoded).hexdigest()
    return f'f1-analyzer:lap-comparison:v{_SHARED_CACHE_SCHEMA_VERSION}:{digest}'


def _shared_cache_ttl_seconds(year):
    """Keep live-season timing fresher than immutable historical sessions."""
    try:
        current_ttl = int(os.getenv('SHARED_TELEMETRY_CURRENT_TTL_SECONDS', '21600'))
        historical_ttl = int(os.getenv('SHARED_TELEMETRY_HISTORICAL_TTL_SECONDS', '2592000'))
    except ValueError:
        current_ttl, historical_ttl = 21600, 2592000
    return max(300, min(31_536_000, current_ttl if int(year) >= date.today().year else historical_ttl))


def _trace_to_shared_wire(telemetry):
    """Serialize a bounded, JSON-safe trace without using unsafe pickle data."""
    max_points = max(300, min(6000, int(os.getenv('SHARED_TELEMETRY_MAX_POINTS', '3600'))))
    trace = telemetry.loc[:, [column for column in _SHARED_TRACE_COLUMNS if column in telemetry.columns]].copy()
    if len(trace) > max_points:
        step = max(1, len(trace) // max_points)
        trace = trace.iloc[::step].copy()
        if trace.index[-1] != telemetry.index[-1]:
            trace = pd.concat([trace, telemetry.loc[[telemetry.index[-1]], trace.columns]])

    values = {}
    for column in trace.columns:
        if column == 'Time':
            series = pd.to_timedelta(trace[column], errors='coerce').dt.total_seconds()
        else:
            series = pd.to_numeric(trace[column], errors='coerce')
        values[column] = [None if pd.isna(value) else float(value) for value in series]
    return {'columns': list(trace.columns), 'values': values}


def _trace_from_shared_wire(payload):
    if not isinstance(payload, dict):
        raise ValueError('invalid shared telemetry trace')
    columns = payload.get('columns')
    values = payload.get('values')
    if not isinstance(columns, list) or not isinstance(values, dict):
        raise ValueError('invalid shared telemetry schema')
    allowed = [column for column in columns if column in _SHARED_TRACE_COLUMNS]
    frame = pd.DataFrame({column: values.get(column, []) for column in allowed})
    if 'Time' in frame.columns:
        frame['Time'] = pd.to_timedelta(frame['Time'], unit='s', errors='coerce')
    for column in ('Throttle', 'Brake', 'nGear', 'RPM'):
        if column not in frame.columns:
            frame[column] = float('nan')
    if not _validate_trace_data(frame):
        raise ValueError('shared telemetry trace has no usable speed data')
    return frame


def _lap_time_seconds(lap):
    value = lap.get('LapTime') if hasattr(lap, 'get') else None
    seconds = pd.to_timedelta(value, errors='coerce').total_seconds()
    if pd.isna(seconds) or seconds <= 0:
        raise ValueError('selected lap is missing a valid lap time')
    return float(seconds)


def _payload_to_shared_wire(payload):
    return {
        'schema': _SHARED_CACHE_SCHEMA_VERSION,
        'd1': payload['d1'],
        'd2': payload['d2'],
        'lbl1': payload['lbl1'],
        'lbl2': payload['lbl2'],
        'c1': payload['c1'],
        'c2': payload['c2'],
        'lap1_seconds': _lap_time_seconds(payload['lap1']),
        'lap2_seconds': _lap_time_seconds(payload['lap2']),
        'tel1': _trace_to_shared_wire(payload['tel1']),
        'tel2': _trace_to_shared_wire(payload['tel2']),
    }


def _payload_from_shared_wire(payload):
    if not isinstance(payload, dict) or payload.get('schema') != _SHARED_CACHE_SCHEMA_VERSION:
        raise ValueError('unknown shared telemetry payload')
    required = ('d1', 'd2', 'lbl1', 'lbl2', 'c1', 'c2', 'lap1_seconds', 'lap2_seconds', 'tel1', 'tel2')
    if not all(key in payload for key in required):
        raise ValueError('incomplete shared telemetry payload')
    return {
        # Circuit metadata is optional in the track-map builder. Cached traces
        # avoid a FastF1 session load; it will use its documented heuristic for
        # turn markers when circuit metadata is not locally available.
        'session': None,
        'd1': str(payload['d1']),
        'd2': str(payload['d2']),
        'lbl1': str(payload['lbl1']),
        'lbl2': str(payload['lbl2']),
        'c1': str(payload['c1']),
        'c2': str(payload['c2']),
        'lap1': pd.Series({'LapTime': pd.to_timedelta(float(payload['lap1_seconds']), unit='s')}),
        'lap2': pd.Series({'LapTime': pd.to_timedelta(float(payload['lap2_seconds']), unit='s')}),
        'tel1': _trace_from_shared_wire(payload['tel1']),
        'tel2': _trace_from_shared_wire(payload['tel2']),
    }


def _copy_comparison_payload(payload, drop_xy_time=False):
    comparison = dict(payload)
    for key in ('lap1', 'lap2'):
        lap = comparison.get(key)
        if hasattr(lap, 'copy'):
            comparison[key] = lap.copy()
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


def _shared_cache_wait_seconds():
    try:
        value = float(os.getenv('SHARED_TELEMETRY_LOCK_WAIT_SECONDS', '12'))
    except ValueError:
        value = 12.0
    return max(0.0, min(25.0, value))


def _load_selected_lap_payload(cache_args):
    """Read a prepared comparison from Redis or build and publish it once.

    The process-local LRU remains the fastest layer. Redis covers the gap
    between separate Vercel instances, while a short lock keeps simultaneous
    cold requests from multiplying FastF1 downloads.
    """
    from shared_cache import (
        acquire_lock,
        get_json,
        is_configured,
        release_lock,
        set_json,
        wait_for_json,
    )

    key = _shared_cache_key(cache_args)
    lock_key = f'{key}:load-lock'
    shared_enabled = is_configured()
    lock_acquired = False
    try:
        if shared_enabled:
            wire = get_json(key)
            if wire is not None:
                try:
                    return _payload_from_shared_wire(wire)
                except (TypeError, ValueError, KeyError) as exc:
                    # The schema is versioned, so an old/corrupt value should
                    # simply fall through to a fresh FastF1 preparation.
                    logging.warning('[shared-cache] Ignoring telemetry payload: %s', exc)

            lock_state = acquire_lock(lock_key)
            lock_acquired = lock_state is True
            if lock_state is False:
                wire = wait_for_json(key, _shared_cache_wait_seconds())
                if wire is not None:
                    try:
                        return _payload_from_shared_wire(wire)
                    except (TypeError, ValueError, KeyError) as exc:
                        logging.warning('[shared-cache] Ignoring waited telemetry payload: %s', exc)

        payload = _prepare_selected_lap_comparison_cached(*cache_args)
        if shared_enabled:
            try:
                set_json(key, _payload_to_shared_wire(payload), _shared_cache_ttl_seconds(cache_args[0]))
            except (TypeError, ValueError, KeyError) as exc:
                logging.warning('[shared-cache] Telemetry payload was not stored: %s', exc)
        return payload
    finally:
        if lock_acquired:
            release_lock(lock_key)


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
            payload = _load_selected_lap_payload(cache_args)
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
    stats = {'local': _prepare_selected_lap_comparison_cached.cache_info()._asdict()}
    try:
        from shared_cache import get_stats
        stats['shared'] = get_stats()
    except Exception:
        # Diagnostics must never make a data callback fail.
        pass
    return stats
