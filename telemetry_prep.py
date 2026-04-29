"""Shared selected-lap telemetry preparation for dashboard callbacks."""
import pandas as pd

from callbacks_shared import _has_valid_lap, _pick_driver_lap
from data import get_best_lap, get_shared_data


def _telemetry_with_distance(lap, drop_xy_time=False):
    tel = lap.get_telemetry().add_distance()
    if drop_xy_time:
        tel = tel.dropna(subset=['X', 'Y', 'Distance', 'Time'])
    if not tel.empty:
        tel = tel.copy()
        tel['Distance'] -= tel['Distance'].min()
    return tel


def prepare_selected_lap_comparison(
    params,
    d1_mode='fastest',
    d2_mode='fastest',
    d1_lap_num=None,
    d2_lap_num=None,
    drop_xy_time=False,
):
    """Load shared session data, pick requested laps, and return normalized telemetry."""
    session, d1, d2, lbl1, lbl2, c1, c2 = get_shared_data(params, laps=True, telemetry=True)
    lap1 = _pick_driver_lap(session, d1, d1_mode, d1_lap_num, get_best_lap)
    lap2 = _pick_driver_lap(session, d2, d2_mode, d2_lap_num, get_best_lap)

    if not _has_valid_lap(lap1, pd):
        raise ValueError(f"{d1} did not set a valid lap.")
    if not _has_valid_lap(lap2, pd):
        raise ValueError(f"{d2} did not set a valid lap.")

    tel1 = _telemetry_with_distance(lap1, drop_xy_time=drop_xy_time)
    tel2 = _telemetry_with_distance(lap2, drop_xy_time=drop_xy_time)

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
