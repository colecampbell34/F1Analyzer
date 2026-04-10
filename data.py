import os
import shutil
import threading
import fastf1
import fastf1.plotting
import fastf1.req
import pandas as pd
import gzip
import builtins
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from fastf1.ergast import Ergast

_SESSION_PRELOAD_EXECUTOR = ThreadPoolExecutor(max_workers=2)
_SESSION_PRELOAD_FUTURES = {}
_SESSION_PRELOAD_LOCK = threading.Lock()

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

# Inject the compressed open into FastF1's caching module
fastf1.req.open = _compressed_cache_open


# --- 1. SETUP F1 CACHE ---
def setup_cache():
    cache_dir = 'f1_cache'
    if not os.path.exists(cache_dir):
        os.makedirs(cache_dir)
    fastf1.Cache.enable_cache(cache_dir)


# --- 1b. EVENT SCHEDULE CACHE ---
@lru_cache(maxsize=20)
def get_event_schedule_cached(year):
    """LRU-cached event schedule. Historical years never change, current year rarely."""
    return fastf1.get_event_schedule(year)


# --- 2. SESSION CACHE (always loads full data) ---
@lru_cache(maxsize=8)
def _load_session_cached(year, race, session_name):
    """LRU-cached session loader. Always loads full telemetry/weather/messages."""
    session = fastf1.get_session(year, race, session_name)
    session.load(telemetry=True, weather=True, messages=True)
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


def get_session_preload_status(year, race, session_name):
    """Return a simple state dict for the requested session preload."""
    if not all([year, race, session_name]):
        return {'state': 'idle', 'message': ''}

    key = _session_cache_key(year, race, session_name)
    with _SESSION_PRELOAD_LOCK:
        future = _SESSION_PRELOAD_FUTURES.get(key)

    if future is None:
        return {'state': 'idle', 'message': ''}
    if not future.done():
        return {'state': 'loading', 'message': ''}

    error = future.exception()
    if error is not None:
        return {'state': 'error', 'message': str(error)}

    return {'state': 'ready', 'message': ''}


def load_session_with_preload(year, race, session_name):
    """Return a session, reusing any in-flight background preload when possible."""
    future = preload_session(year, race, session_name)
    if future is not None:
        return future.result()
    return _load_session_cached(year, race, session_name)

@lru_cache(maxsize=16)
def _load_drivers_fast(year, race, session_name):
    """Fast cache to get driver info without loading laps/telemetry."""
    session = fastf1.get_session(year, race, session_name)
    try:
        session.load(telemetry=False, laps=False, weather=False, messages=False)
        return get_driver_info(session)
    except Exception:
        # Fallback if fastf1 complains
        return []


# --- 3. TRACK STATUS UTILITY ---
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


# --- 4. DRIVER INFO UTILITY ---
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


def get_teammate(driver_abbr, session):
    """Given a driver abbreviation, returns the abbreviation of their teammate (or None)."""
    return get_teammate_from_info(driver_abbr, get_driver_info(session))


@lru_cache(maxsize=32)
def get_pit_stop_data(year, round_number):
    """Load official Ergast pit-stop durations for a race weekend."""
    ergast = Ergast(result_type='pandas', auto_cast=True)
    result = ergast.get_pit_stops(season=int(year), round=int(round_number))
    if not result.content:
        return pd.DataFrame()
    return result.content[0].copy()


# --- 6. CACHE MANAGEMENT ---
def clear_old_cache(max_size_gb=1.0):
    cache_path = "f1_cache"

    if not os.path.exists(cache_path):
        os.makedirs(cache_path)
        fastf1.Cache.enable_cache(cache_path)
        return

    total_size = 0
    for root, _, files in os.walk(cache_path):
        for f in files:
            fp = os.path.join(root, f)
            total_size += os.path.getsize(fp)

    if total_size > max_size_gb * 1024 ** 3:
        print("***Cache limit reached! Clearing cache...")
        shutil.rmtree(cache_path)
        os.makedirs(cache_path)
        fastf1.Cache.enable_cache(cache_path)
