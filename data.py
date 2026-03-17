import os
import shutil
import fastf1
from functools import lru_cache

# --- 1. SETUP F1 CACHE ---
def setup_cache():
    cache_dir = 'f1_cache'
    if not os.path.exists(cache_dir):
        os.makedirs(cache_dir)
    fastf1.Cache.enable_cache(cache_dir)

# --- SESSION CACHE ---
@lru_cache(maxsize=4)
def _load_session_cached(year, race, session_name, load_telemetry=True):
    """LRU-cached session loader to avoid redundant parsing."""
    session = fastf1.get_session(year, race, session_name)
    session.load(telemetry=load_telemetry, weather=load_telemetry, messages=False)
    return session


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


