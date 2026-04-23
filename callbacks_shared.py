import os
import time
import logging
from contextlib import contextmanager
from urllib.parse import parse_qs, urlencode

import dash

# Max AI Q&A exchanges kept in browser session storage.
MAX_AI_HISTORY = 20

VALID_TABS = {
    'tab-telemetry', 'tab-trackmap', 'tab-strategy',
    'tab-race', 'tab-gridpace', 'tab-ai'
}

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
    return get_best_lap(session, driver)


def _trim_history(history):
    """Enforce max history length by dropping oldest entries."""
    if len(history) > MAX_AI_HISTORY:
        return history[-MAX_AI_HISTORY:]
    return history


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

    return state


def _build_url_search(params, active_tab):
    query = {
        'year': params.get('year'),
        'race': params.get('race'),
        'session': params.get('session_type'),
        'driver1': params.get('driver1'),
        'driver2': params.get('driver2'),
    }
    if active_tab in VALID_TABS:
        query['tab'] = active_tab

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
