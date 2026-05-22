"""Shared selected-lap telemetry preparation for dashboard callbacks."""
import os
from functools import lru_cache

import pandas as pd

from callbacks_shared import _has_valid_lap, _pick_driver_lap
from data import get_best_lap, get_shared_data

try:
    TELEMETRY_PREP_CACHE_MAXSIZE = int(os.getenv('TELEMETRY_PREP_CACHE_MAXSIZE', '8'))
except ValueError:
    TELEMETRY_PREP_CACHE_MAXSIZE = 8
TELEMETRY_PREP_CACHE_MAXSIZE = max(2, min(24, TELEMETRY_PREP_CACHE_MAXSIZE))


def _telemetry_with_distance(lap, drop_xy_time=False, session=None):
    try:
        tel = lap.get_telemetry().add_distance()
    except Exception as exc:
        message = str(exc).lower()
        if session is None or ('load' not in message and 'loaded' not in message):
            raise
        session.load(laps=True, telemetry=True, weather=False, messages=False)
        tel = lap.get_telemetry().add_distance()
    if drop_xy_time:
        tel = tel.dropna(subset=['X', 'Y', 'Distance', 'Time'])
    if not tel.empty:
        tel = tel.copy()
        tel['Distance'] -= tel['Distance'].min()
    return tel


def _copy_comparison_payload(payload, drop_xy_time=False):
    comparison = dict(payload)
    for key in ('tel1', 'tel2'):
        tel = comparison[key].copy()
        if drop_xy_time:
            tel = tel.dropna(subset=['X', 'Y', 'Distance', 'Time']).copy()
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
):
    """Load shared session data, pick requested laps, and return normalized telemetry."""
    payload = _prepare_selected_lap_comparison_cached(
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
    return _copy_comparison_payload(payload, drop_xy_time=drop_xy_time)


def get_selected_lap_cache_stats():
    return _prepare_selected_lap_comparison_cached.cache_info()._asdict()
