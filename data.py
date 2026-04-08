import os
import shutil
import fastf1
import fastf1.plotting
import fastf1.req
import pandas as pd
import gzip
import builtins
from functools import lru_cache

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


# --- 2. SESSION CACHE (always loads full data) ---
@lru_cache(maxsize=4)
def _load_session_cached(year, race, session_name):
    """LRU-cached session loader. Always loads full telemetry/weather/messages."""
    session = fastf1.get_session(year, race, session_name)
    session.load(telemetry=True, weather=True, messages=True)
    return session


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
def get_teammate(driver_abbr, session):
    """Given a driver abbreviation, returns the abbreviation of their teammate (or None)."""
    info = get_driver_info(session)
    driver_team = None
    for d in info:
        if d['abbr'] == driver_abbr:
            driver_team = d['team']
            break
    if not driver_team:
        return None
    for d in info:
        if d['team'] == driver_team and d['abbr'] != driver_abbr:
            return d['abbr']
    return None


# --- 6. CACHE MANAGEMENT ---
def clear_old_cache(max_size_gb=2.0):
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
