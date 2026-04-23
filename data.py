import os
import shutil
import threading
import time
import logging
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
import pandas as pd

# Suppress FastF1 and other noisy libraries at the module level
logging.getLogger('fastf1').setLevel(logging.WARNING)
logging.getLogger('urllib3').setLevel(logging.WARNING)

try:
    import fcntl
except ImportError:  # pragma: no cover - non-POSIX fallback
    fcntl = None

_SESSION_PRELOAD_EXECUTOR = ThreadPoolExecutor(max_workers=4)
_SESSION_PRELOAD_FUTURES = {}
_SESSION_PRELOAD_LOCK = threading.Lock()
_GRANULAR_LOAD_LOCK = threading.Lock()
_MAX_TRACKED_PRELOAD_FUTURES = 12
_CACHE_DIR = 'f1_cache'
_CACHE_SETUP_LOCK = threading.Lock()
_CACHE_READY = False
_CACHE_PRUNE_LOCKFILE = os.path.join(_CACHE_DIR, '.cache-prune.lock')
_CACHE_PRUNE_STAMP = os.path.join(_CACHE_DIR, '.cache-prune.stamp')
LOG_SESSION_LOADING = os.getenv('LOG_SESSION_LOADING') == '1'
SESSION_CACHE_MAXSIZE = 4
SESSION_SUMMARY_CACHE_MAXSIZE = 12
EVENT_SCHEDULE_CACHE_MAXSIZE = 20
EVENT_SESSIONS_CACHE_MAXSIZE = 64



# --- SESSION TYPE HELPERS ---
def is_qualifying(session_type):
    """Check if a session type is any form of qualifying."""
    return any(q in session_type for q in ['Qualifying', 'Shootout'])


def is_race(session_type):
    """Check if a session type is a race or sprint race."""
    return session_type in ['Race', 'Sprint']


def is_practice(session_type):
    """Check if a session type is any form of practice."""
    return any(p in session_type for p in ['Practice', 'FP'])


def setup_cache():
    """Enable FastF1 disk cache once per process."""
    global _CACHE_READY
    if _CACHE_READY:
        return

    with _CACHE_SETUP_LOCK:
        if _CACHE_READY:
            return
        import fastf1
        if not os.path.exists(_CACHE_DIR):
            os.makedirs(_CACHE_DIR)
        fastf1.Cache.enable_cache(_CACHE_DIR)
        _CACHE_READY = True


def _ensure_cache_ready():
    """Ensure FastF1 cache is enabled before any data calls."""
    if not _CACHE_READY:
        setup_cache()


@lru_cache(maxsize=EVENT_SCHEDULE_CACHE_MAXSIZE)
def get_event_schedule_cached(year):
    """LRU-cached event schedule. Historical years never change, current year rarely."""
    _ensure_cache_ready()
    import fastf1
    return fastf1.get_event_schedule(year)


@lru_cache(maxsize=EVENT_SESSIONS_CACHE_MAXSIZE)
def get_event_sessions_cached(year, race):
    """LRU-cached session names for a specific event."""
    _ensure_cache_ready()
    import fastf1

    event = fastf1.get_event(int(year), str(race))
    sessions = []
    for idx in range(1, 6):
        session_name = event.get(f'Session{idx}')
        if pd.notna(session_name) and session_name:
            sessions.append(str(session_name))
    return tuple(sessions)


@lru_cache(maxsize=SESSION_CACHE_MAXSIZE)
def _load_session_granular_cached(year, race, session_name, laps=True, telemetry=False, weather=False, messages=False):
    """LRU-cached session loader with granular control.
    Uses the same keys but allows loading specific data streams.
    Note: FastF1 handles repeated .load() calls efficiently if data is already loaded.
    """
    _ensure_cache_ready()
    import fastf1
    
    # We use a lock here because lru_cache might allow multiple threads 
    # to enter the function for the same missing key simultaneously.
    with _GRANULAR_LOAD_LOCK:
        session = fastf1.get_session(int(year), str(race), str(session_name))
        
        # Selective Loading: Only load what we need
        session.load(
            laps=bool(laps), 
            telemetry=bool(telemetry), 
            weather=bool(weather), 
            messages=bool(messages)
        )
    return session


@lru_cache(maxsize=3)
def _load_session_cached(year, race, session_name):
    """Backward compatibility for full loading."""
    return _load_session_granular_cached(year, race, session_name, 
                                        laps=True, telemetry=True, weather=True, messages=True)


@lru_cache(maxsize=SESSION_SUMMARY_CACHE_MAXSIZE)
def _load_session_summary_cached(year, race, session_name, include_laps):
    """LRU-cached lightweight session loader for sidebar data and labels."""
    _ensure_cache_ready()
    import fastf1
    session = fastf1.get_session(year, race, session_name)
    session.load(laps=bool(include_laps), telemetry=False, weather=False, messages=bool(include_laps))
    return session


def _session_cache_key(year, race, session_name):
    return int(year), str(race), str(session_name)


def _session_preload_key(year, race, session_name, laps, telemetry, weather, messages):
    return (
        int(year), str(race), str(session_name),
        bool(laps), bool(telemetry), bool(weather), bool(messages)
    )


def preload_session(year, race, session_name, laps=True, telemetry=False, weather=False, messages=False):
    """Start loading a session profile in the background."""
    if not all([year, race, session_name]):
        return None

    key = _session_preload_key(year, race, session_name, laps, telemetry, weather, messages)
    with _SESSION_PRELOAD_LOCK:
        if len(_SESSION_PRELOAD_FUTURES) > _MAX_TRACKED_PRELOAD_FUTURES:
            done_keys = [k for k, fut in _SESSION_PRELOAD_FUTURES.items() if fut.done()]
            for old_key in done_keys[: len(_SESSION_PRELOAD_FUTURES) - _MAX_TRACKED_PRELOAD_FUTURES]:
                _SESSION_PRELOAD_FUTURES.pop(old_key, None)
        future = _SESSION_PRELOAD_FUTURES.get(key)
        # If no future or previous failed, start requested profile preload.
        if future is None or (future.done() and future.exception() is not None):
            future = _SESSION_PRELOAD_EXECUTOR.submit(
                _load_session_granular_cached, key[0], key[1], key[2], key[3], key[4], key[5], key[6]
            )
            _SESSION_PRELOAD_FUTURES[key] = future
            if LOG_SESSION_LOADING:
                logging.info(
                    "[session] preload started "
                    f"year={key[0]} race={key[1]} session={key[2]} "
                    f"laps={key[3]} telemetry={key[4]} weather={key[5]} messages={key[6]}"
                )
        elif LOG_SESSION_LOADING:
            logging.info(
                "[session] preload reused "
                f"year={key[0]} race={key[1]} session={key[2]} "
                f"laps={key[3]} telemetry={key[4]} weather={key[5]} messages={key[6]}"
            )
        return future


def load_session_with_preload(year, race, session_name, laps=True, telemetry=False, weather=False, messages=False):
    """Return a session with specific data streams, reusing preloaded object when possible."""
    key = _session_cache_key(year, race, session_name)
    preload_key = _session_preload_key(year, race, session_name, laps, telemetry, weather, messages)
    with _SESSION_PRELOAD_LOCK:
        exact_future = _SESSION_PRELOAD_FUTURES.get(preload_key)

    # If matching preload is in-flight, reuse it directly.
    if exact_future is not None:
        if LOG_SESSION_LOADING:
            logging.info(
                "[session] waiting on exact preload "
                f"year={key[0]} race={key[1]} session={key[2]} "
                f"laps={bool(laps)} telemetry={bool(telemetry)} weather={bool(weather)} messages={bool(messages)}"
            )
        return exact_future.result()

    if bool(laps):
        preload_session(*key, bool(laps), bool(telemetry), bool(weather), bool(messages))

    if LOG_SESSION_LOADING:
        logging.info(
            "[session] granular load "
            f"year={key[0]} race={key[1]} session={key[2]} "
            f"laps={bool(laps)} telemetry={bool(telemetry)} weather={bool(weather)} messages={bool(messages)}"
        )
    return _load_session_granular_cached(key[0], key[1], key[2], laps, telemetry, weather, messages)


def load_session_summary(year, race, session_name, include_laps=False):
    """Return a lightweight session object without telemetry/weather/messages.
    
    If include_laps=True, it loads laps and messages (for leaderboard/AI).
    """
    return _load_session_summary_cached(int(year), str(race), str(session_name), bool(include_laps))


@lru_cache(maxsize=16)
def _load_drivers_fast(year, race, session_name):
    """Fast cache to get driver info ordered by session results or fastest laps."""
    try:
        session = load_session_summary(year, race, session_name, include_laps=False)
        return get_driver_info(session)
    except Exception as e:
        logging.error(f"Error in _load_drivers_fast: {e}")
        return []


def get_track_status_events(session):
    """Returns (sc_laps, vsc_laps, red_laps) sets extracted from session laps."""
    sc_laps, vsc_laps, red_laps = set(), set(), set()
    try:
        all_laps = session.laps
        sc_laps.update(
            all_laps[all_laps['TrackStatus'].astype(str).str.contains('4', na=False)]['LapNumber'].dropna().tolist())
        vsc_laps.update(
            all_laps[all_laps['TrackStatus'].astype(str).str.contains('6', na=False)]['LapNumber'].dropna().tolist())
        red_laps.update(
            all_laps[all_laps['TrackStatus'].astype(str).str.contains('5', na=False)]['LapNumber'].dropna().tolist())
    except Exception:
        pass
    return sc_laps, vsc_laps, red_laps


def get_driver_info(session):
    """Returns a list of dicts with driver abbreviation, full name, team, and color."""
    drivers = []
    if getattr(session, 'results', None) is None or session.results.empty:
        return drivers

    for _, row in session.results.iterrows():
        abbr = row.get('Abbreviation', '')
        if not isinstance(abbr, str) or len(abbr) != 3:
            continue

        full_name = f"{row.get('FirstName', '')} {row.get('LastName', '')}".strip()
        team = row.get('TeamName', '')

        color = row.get('TeamColor', '')
        if pd.isna(color) or not color:
            try:
                import fastf1.plotting
                color = fastf1.plotting.get_team_color(team, session=session)
            except Exception:
                color = 'ffffff'
        if not str(color).startswith('#'):
            color = f"#{color}"

        drivers.append({
            'abbr': abbr,
            'name': full_name if full_name else abbr,
            'team': team if isinstance(team, str) else '',
            'color': color
        })
    return drivers


def get_teammate_from_info(driver_abbr, driver_info):
    """Return the teammate abbreviation from preloaded driver info."""
    driver_team = None
    for d in driver_info:
        if d['abbr'] == driver_abbr:
            driver_team = d['team']
            break
    if not driver_team:
        return None
    for d in driver_info:
        if d['team'] == driver_team and d['abbr'] != driver_abbr:
            return d['abbr']
    return None


def get_best_lap(session, driver_abbr):
    """
    Returns the 'official' best lap object for a driver.
    For Qualifying/Shootout, it prioritizes Q3 > Q2 > Q1 times from session.results.
    For other sessions (Practice, Race), it uses pick_fastest().
    """
    try:
        if not hasattr(session, 'laps') or session.laps.empty:
            return None

        # Determine if this is a qualifying session
        session_name = getattr(session, 'name', '')
        is_qualy = any(q in session_name for q in ['Qualifying', 'Shootout'])

        # If qualy, try to match official leaderboard time from results
        if is_qualy and getattr(session, 'results', None) is not None and not session.results.empty:
            res = session.results[session.results['Abbreviation'] == driver_abbr]
            if not res.empty:
                row = res.iloc[0]
                best_time = None
                for col in ['Q3', 'Q2', 'Q1', 'SQ3', 'SQ2', 'SQ1']:
                    if col in row.index and pd.notna(row[col]):
                        best_time = row[col]
                        break
                
                if best_time is not None:
                    drv_laps = session.laps.pick_drivers(driver_abbr)
                    drv_laps = drv_laps[pd.notna(drv_laps['LapTime'])]
                    if not drv_laps.empty:
                        # Match within 50ms — timing sources can differ by a few milliseconds
                        diffs = (drv_laps['LapTime'] - best_time).abs()
                        if diffs.min() <= pd.Timedelta('0.05s'):
                            return drv_laps.loc[diffs.idxmin()]

        # Fallback to literal fastest lap
        return session.laps.pick_drivers(driver_abbr).pick_fastest()
    except Exception:
        try:
            return session.laps.pick_drivers(driver_abbr).pick_fastest()
        except Exception:
            return None


def get_single_driver_color(driver_abbr, session):
    """Fetch a single driver's team color with fallback."""
    try:
        import fastf1.plotting
        color = fastf1.plotting.get_driver_color(driver_abbr, session)
        if not color.startswith('#'):
            color = f'#{color}'
        return color
    except (KeyError, ValueError):
        return '#ffffff'


@lru_cache(maxsize=16)
def _compute_labels_colors(year, race, session_type, d1, d2):
    """LRU-cached driver labels (with finishing position) and team colors.

    Separated from session loading so that different data-stream
    combinations (telemetry vs. weather) share a single cache entry.
    """
    session = load_session_summary(year, race, session_type, include_laps=False)

    from graphs import _get_driver_colors
    c1, c2 = _get_driver_colors(d1, d2, session)
    try:
        if session.results is not None and not session.results.empty:
            res1 = session.results[session.results['Abbreviation'] == d1]
            p1 = res1['Position'].values[0] if not res1.empty else None
            lbl1 = f"{d1} (P{int(p1)})" if pd.notna(p1) else d1

            res2 = session.results[session.results['Abbreviation'] == d2]
            p2 = res2['Position'].values[0] if not res2.empty else None
            lbl2 = f"{d2} (P{int(p2)})" if pd.notna(p2) else d2
        else:
            lbl1, lbl2 = d1, d2
    except (IndexError, KeyError):
        lbl1, lbl2 = d1, d2

    return lbl1, lbl2, c1, c2


def get_shared_data(params, laps=True, telemetry=False, weather=False, messages=False):
    """Loads session with granular control and computes shared labels/colors."""
    year, race, session_type = params['year'], params['race'], params['session_type']
    d1, d2 = params['driver1'], params['driver2']
    session = load_session_with_preload(
        year, race, session_type,
        laps=laps, telemetry=telemetry, weather=weather, messages=messages
    )
    lbl1, lbl2, c1, c2 = _compute_labels_colors(year, race, session_type, d1, d2)
    return session, d1, d2, lbl1, lbl2, c1, c2


@lru_cache(maxsize=10)
def get_pit_stop_data(year, round_number):
    """Load official Ergast pit-stop durations for a race weekend.
    
    Falls back gracefully if the Ergast API is unavailable (deprecated).
    """
    try:
        from fastf1.ergast import Ergast
        ergast = Ergast(result_type='pandas', auto_cast=True)
        result = ergast.get_pit_stops(season=int(year), round=int(round_number))
        if not result.content:
            return pd.DataFrame()
        return result.content[0].copy()
    except Exception:
        # Ergast API may be offline (deprecated) — return empty to trigger fallback
        return pd.DataFrame()


def _cache_size_bytes(cache_path):
    total_size = 0
    for root, _, files in os.walk(cache_path):
        for filename in files:
            total_size += os.path.getsize(os.path.join(root, filename))
    return total_size


def maybe_prune_cache(max_size_gb=2.0, min_interval_seconds=3600):
    """Production-safe cache pruning with a best-effort cross-worker file lock."""
    import fastf1

    os.makedirs(_CACHE_DIR, exist_ok=True)
    now = time.time()

    if os.path.exists(_CACHE_PRUNE_STAMP):
        try:
            if now - os.path.getmtime(_CACHE_PRUNE_STAMP) < min_interval_seconds:
                return
        except OSError:
            pass

    lock_handle = None
    try:
        lock_handle = open(_CACHE_PRUNE_LOCKFILE, 'a+', encoding='utf-8')
        if fcntl is not None:
            try:
                fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                return

        if os.path.exists(_CACHE_PRUNE_STAMP):
            try:
                if now - os.path.getmtime(_CACHE_PRUNE_STAMP) < min_interval_seconds:
                    return
            except OSError:
                pass

        total_size = _cache_size_bytes(_CACHE_DIR)
        if total_size > max_size_gb * 1024 ** 3:
            logging.warning(f"[cache] pruning FastF1 cache at {total_size / 1024 ** 3:.2f} GB")
            shutil.rmtree(_CACHE_DIR, ignore_errors=True)
            os.makedirs(_CACHE_DIR, exist_ok=True)
            fastf1.Cache.enable_cache(_CACHE_DIR)

        with open(_CACHE_PRUNE_STAMP, 'w', encoding='utf-8') as stamp:
            stamp.write(str(int(now)))
    finally:
        if lock_handle is not None and fcntl is not None:
            try:
                fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass
        if lock_handle is not None:
            lock_handle.close()


def clear_old_cache(max_size_gb=2.0):
    """Backward-compatible cache pruning entry point."""
    maybe_prune_cache(max_size_gb=max_size_gb, min_interval_seconds=0)


# Initialize cache on module import
setup_cache()