import os
import shutil
import threading
import gzip
import builtins
import time
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache

try:
    import fcntl
except ImportError:  # pragma: no cover - non-POSIX fallback
    fcntl = None

_SESSION_PRELOAD_EXECUTOR = ThreadPoolExecutor(max_workers=2)
_SESSION_PRELOAD_FUTURES = {}
_SESSION_PRELOAD_LOCK = threading.Lock()
_CACHE_DIR = 'f1_cache'
_CACHE_PRUNE_LOCKFILE = os.path.join(_CACHE_DIR, '.cache-prune.lock')
_CACHE_PRUNE_STAMP = os.path.join(_CACHE_DIR, '.cache-prune.stamp')

def _compressed_cache_open(file, mode='r', buffering=-1, encoding=None, errors=None, newline=None, closefd=True, opener=None):
    """Monkey-patched open() to compress/decompress FastF1 cache files on the fly."""
    file_str = str(file)
    if file_str.endswith('.ff1pkl'):
        if 'w' in mode:
            return gzip.open(file_str, mode, compresslevel=1)
        elif 'r' in mode:
            try:
                # Check for gzip magic number
                with builtins.open(file_str, 'rb') as f:
                    magic = f.read(2)
                if magic == b'\x1f\x8b':
                    return gzip.open(file_str, mode)
                else:
                    return builtins.open(file, mode, buffering, encoding, errors, newline, closefd, opener)
            except FileNotFoundError:
                pass
    return builtins.open(file, mode, buffering, encoding, errors, newline, closefd, opener)


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


# --- 1. SETUP F1 CACHE ---
def setup_cache():
    import fastf1
    import fastf1.req
    # Inject the compressed open into FastF1's caching module
    fastf1.req.open = _compressed_cache_open

    if not os.path.exists(_CACHE_DIR):
        os.makedirs(_CACHE_DIR)
    fastf1.Cache.enable_cache(_CACHE_DIR)


# --- 1b. EVENT SCHEDULE CACHE ---
@lru_cache(maxsize=20)
def get_event_schedule_cached(year):
    """LRU-cached event schedule. Historical years never change, current year rarely."""
    import fastf1
    return fastf1.get_event_schedule(year)


@lru_cache(maxsize=64)
def get_event_sessions_cached(year, race):
    """LRU-cached session names for a specific event."""
    import fastf1
    import pandas as pd

    event = fastf1.get_event(int(year), str(race))
    sessions = []
    for idx in range(1, 6):
        session_name = event.get(f'Session{idx}')
        if pd.notna(session_name) and session_name:
            sessions.append(str(session_name))
    return tuple(sessions)


# --- 2. SESSION CACHE (always loads full data) ---
@lru_cache(maxsize=3)
def _load_session_cached(year, race, session_name):
    """LRU-cached session loader. Loads laps, weather, and messages (fast).
    Telemetry is NOT loaded here to improve initial responsiveness.
    """
    import fastf1
    session = fastf1.get_session(year, race, session_name)
    session.load(laps=True, telemetry=False, weather=True, messages=True)
    return session


def ensure_telemetry_loaded(session):
    """Ensures telemetry data is loaded for the session. Blocking if not cached."""
    if session is not None:
        session.load(telemetry=True)
    return session


@lru_cache(maxsize=6)
def _load_session_summary_cached(year, race, session_name, include_laps):
    """LRU-cached lightweight session loader for sidebar data and labels."""
    import fastf1
    session = fastf1.get_session(year, race, session_name)
    session.load(laps=bool(include_laps), telemetry=False, weather=False, messages=bool(include_laps))
    return session


def _session_cache_key(year, race, session_name):
    return int(year), str(race), str(session_name)


def preload_session(year, race, session_name):
    """Start loading a full session in the background and deduplicate requests."""
    if not all([year, race, session_name]):
        return None

    key = _session_cache_key(year, race, session_name)
    with _SESSION_PRELOAD_LOCK:
        future = _SESSION_PRELOAD_FUTURES.get(key)
        if future is None or (future.done() and future.exception() is not None):
            future = _SESSION_PRELOAD_EXECUTOR.submit(_load_session_cached, *key)
            _SESSION_PRELOAD_FUTURES[key] = future
        return future


def load_session_with_preload(year, race, session_name):
    """Return a session, reusing any in-flight background preload when possible."""
    future = preload_session(year, race, session_name)
    if future is not None:
        return future.result()
    return _load_session_cached(year, race, session_name)


def load_session_summary(year, race, session_name, include_laps=False):
    """Return a lightweight session object without telemetry/weather/messages.
    
    If include_laps=True, it loads laps and messages (for leaderboard/AI).
    """
    return _load_session_summary_cached(int(year), str(race), str(session_name), bool(include_laps))


@lru_cache(maxsize=16)
def _load_drivers_fast(year, race, session_name):
    """Fast cache to get driver info without loading laps/telemetry."""
    try:
        session = load_session_summary(year, race, session_name, include_laps=False)
        return get_driver_info(session)
    except Exception:
        # Fallback if fastf1 complains
        return []


# --- 3. TRACK STATUS UTILITY ---
def get_track_status_events(session):
    """Returns (sc_laps, vsc_laps, red_laps) sets extracted from session laps."""
    import pandas as pd
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


# --- 4. DRIVER INFO UTILITY ---
def get_driver_info(session):
    """Returns a list of dicts with driver abbreviation, full name, team, and color."""
    drivers = []
    if getattr(session, 'results', None) is None or session.results.empty:
        return drivers

    for _, row in session.results.iterrows():
        import pandas as pd
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


# --- 5. TEAMMATE LOOKUP ---
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
    import pandas as pd
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


# --- 5b. SINGLE DRIVER COLOR UTILITY ---
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


# --- 5c. SHARED DATA (session + labels + colors) ---
def get_shared_data(params):
    """Loads session and computes shared labels/colors from stored params."""
    import pandas as pd
    session = load_session_with_preload(params['year'], params['race'], params['session_type'])
    d1, d2 = params['driver1'], params['driver2']

    try:
        p1 = session.results.loc[session.results['Abbreviation'] == d1, 'Position'].values[0]
        lbl1 = f"{d1} (P{int(p1)})" if pd.notna(p1) else d1
    except (IndexError, KeyError):
        lbl1 = d1
    try:
        p2 = session.results.loc[session.results['Abbreviation'] == d2, 'Position'].values[0]
        lbl2 = f"{d2} (P{int(p2)})" if pd.notna(p2) else d2
    except (IndexError, KeyError):
        lbl2 = d2

    from graphs import _get_driver_colors
    c1, c2 = _get_driver_colors(d1, d2, session)
    return session, d1, d2, lbl1, lbl2, c1, c2


@lru_cache(maxsize=10)
def get_pit_stop_data(year, round_number):
    """Load official Ergast pit-stop durations for a race weekend.
    
    Falls back gracefully if the Ergast API is unavailable (deprecated).
    """
    try:
        from fastf1.ergast import Ergast
        import pandas as pd
        ergast = Ergast(result_type='pandas', auto_cast=True)
        result = ergast.get_pit_stops(season=int(year), round=int(round_number))
        if not result.content:
            return pd.DataFrame()
        return result.content[0].copy()
    except Exception:
        import pandas as pd
        # Ergast API may be offline (deprecated) — return empty to trigger fallback
        return pd.DataFrame()


def _cache_size_bytes(cache_path):
    total_size = 0
    for root, _, files in os.walk(cache_path):
        for filename in files:
            total_size += os.path.getsize(os.path.join(root, filename))
    return total_size


def maybe_prune_cache(max_size_gb=1.0, min_interval_seconds=3600):
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
            print(f"[cache] pruning FastF1 cache at {total_size / 1024 ** 3:.2f} GB")
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


# --- 6. CACHE MANAGEMENT ---
def clear_old_cache(max_size_gb=1.0):
    """Backward-compatible cache pruning entry point."""
    maybe_prune_cache(max_size_gb=max_size_gb, min_interval_seconds=0)
