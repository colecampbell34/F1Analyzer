import os
import time
import logging
import json
from contextlib import contextmanager
from urllib.parse import parse_qs, urlencode

import dash
from ux_helpers import VALID_EXPERIENCE_MODES, normalize_experience_mode

# Max AI Q&A exchanges kept in browser session storage.
MAX_AI_HISTORY = 20

VALID_TABS = {
    'tab-telemetry', 'tab-trackmap', 'tab-strategy',
    'tab-race', 'tab-gridpace', 'tab-ai'
}
VALID_LAP_MODES = {'fastest', 'specific'}
VALID_TRACKMAP_MODES = {'dominance', 'braking', 'speed'}

CALLBACK_TIMING_THRESHOLD_MS = float(os.getenv('CALLBACK_TIMING_THRESHOLD_MS', '400'))
LOG_ALL_CALLBACKS = os.getenv('LOG_ALL_CALLBACKS') == '1'


def _missing_required_fields(field_map):
    """Return labels for required fields that are empty."""
    return [label for label, value in field_map.items() if value in (None, '')]


def _has_valid_lap(lap, pd):
    """Return True when lap exists and contains a valid lap time."""
    return not (getattr(lap, "empty", True) or (pd.isna(lap.get("LapTime")) if lap is not None else True))


def _pick_driver_lap(session, driver, mode, lap_num, get_best_lap):
    """Return specific lap when requested, otherwise driver fastest lap."""
    drv_laps = session.laps.pick_drivers(driver)
    if mode == 'specific' and lap_num is not None:
        specific = drv_laps[drv_laps['LapNumber'] == int(lap_num)]
        if not specific.empty:
            return specific.iloc[0]
        available = sorted(
            int(lap)
            for lap in drv_laps['LapNumber'].dropna().unique().tolist()
        )
        if available:
            raise ValueError(
                f"{driver} lap {int(lap_num)} is not available. "
                f"Available laps: {available[0]}-{available[-1]}."
            )
        raise ValueError(f"{driver} has no available laps for this session.")
    return get_best_lap(session, driver)


def _trim_history(history):
    """Enforce max history length by dropping oldest entries."""
    if len(history) > MAX_AI_HISTORY:
        return history[-MAX_AI_HISTORY:]
    return history


def _figure_cache_key(params, namespace, *parts):
    """Return a stable key for a rendered figure already held by the browser."""
    if not params:
        return None
    payload = {
        'namespace': namespace,
        'year': params.get('year'),
        'race': params.get('race'),
        'session_type': params.get('session_type'),
        'driver1': params.get('driver1'),
        'driver2': params.get('driver2'),
        'parts': parts,
    }
    return json.dumps(payload, sort_keys=True, separators=(',', ':'), default=str)


def _parse_url_state(url_search):
    query_params = parse_qs((url_search or '').lstrip('?'))
    state = {
        'race': (query_params.get('race') or [None])[0],
        'session_type': (query_params.get('session') or [None])[0],
        'driver1': (query_params.get('driver1') or [None])[0],
        'driver2': (query_params.get('driver2') or [None])[0],
        'tab': (query_params.get('tab') or [None])[0]
    }

    raw_year = (query_params.get('year') or [None])[0]
    try:
        state['year'] = int(raw_year) if raw_year is not None else None
    except (TypeError, ValueError):
        state['year'] = None

    if state['tab'] not in VALID_TABS:
        state['tab'] = None

    for key in ('d1_lap_mode', 'd2_lap_mode'):
        value = (query_params.get(key) or [None])[0]
        state[key] = value if value in VALID_LAP_MODES else None

    for key in ('d1_lap', 'd2_lap'):
        raw_lap = (query_params.get(key) or [None])[0]
        try:
            lap_num = int(raw_lap) if raw_lap not in (None, '') else None
            state[key] = lap_num if lap_num and lap_num > 0 else None
        except (TypeError, ValueError):
            state[key] = None

    trackmap_mode = (query_params.get('trackmap') or [None])[0]
    state['trackmap_mode'] = trackmap_mode if trackmap_mode in VALID_TRACKMAP_MODES else None
    mode = (query_params.get('mode') or [None])[0]
    state['mode'] = normalize_experience_mode(mode) if mode in VALID_EXPERIENCE_MODES else None

    return state


def _build_url_search(params, active_tab, ui_state=None):
    query = {
        'year': params.get('year'),
        'race': params.get('race'),
        'session': params.get('session_type'),
        'driver1': params.get('driver1'),
        'driver2': params.get('driver2'),
    }
    if active_tab in VALID_TABS:
        query['tab'] = active_tab
    ui_state = ui_state or {}
    for key in ('d1_lap_mode', 'd2_lap_mode'):
        if ui_state.get(key) == 'specific':
            query[key] = 'specific'
    for key in ('d1_lap', 'd2_lap'):
        if ui_state.get(key):
            query[key] = int(ui_state[key])
    if ui_state.get('trackmap_mode') in VALID_TRACKMAP_MODES:
        query['trackmap'] = ui_state['trackmap_mode']
    if ui_state.get('mode') in VALID_EXPERIENCE_MODES:
        query['mode'] = ui_state['mode']

    clean_query = {key: value for key, value in query.items() if value not in (None, '')}
    return f"?{urlencode(clean_query)}" if clean_query else ""


@contextmanager
def _timed_callback(name, **fields):
    start = time.perf_counter()
    try:
        yield
    finally:
        elapsed_ms = (time.perf_counter() - start) * 1000
        if LOG_ALL_CALLBACKS or elapsed_ms >= CALLBACK_TIMING_THRESHOLD_MS:
            trigger = getattr(dash.ctx, 'triggered_id', None)
            field_text = ' '.join(
                f"{key}={value}" for key, value in fields.items()
                if value not in (None, '')
            )
            logging.info(
                f"[timing] callback={name} trigger={trigger} ms={elapsed_ms:.1f}"
                f"{(' ' + field_text) if field_text else ''}"
            )
        try:
            from perf_monitor import record_callback_timing
            record_callback_timing(
                name,
                elapsed_ms,
                fields=fields,
                trigger=getattr(dash.ctx, 'triggered_id', None)
            )
        except Exception:
            pass
