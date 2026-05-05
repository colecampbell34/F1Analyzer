import os
import shutil
import threading
import time
import logging
import hashlib
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
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
_SESSION_PRELOAD_JOBS = {}
_GRANULAR_LOAD_LOCK = threading.Lock()
_MAX_TRACKED_PRELOAD_FUTURES = 12
_MAX_TRACKED_PRELOAD_JOBS = 24
_PRELOAD_JOB_TTL_SECONDS = 900
_CACHE_DIR = 'f1_cache'
_CACHE_SETUP_LOCK = threading.Lock()
_CACHE_READY = False
_CACHE_PRUNE_LOCKFILE = os.path.join(_CACHE_DIR, '.cache-prune.lock')
_CACHE_PRUNE_STAMP = os.path.join(_CACHE_DIR, '.cache-prune.stamp')
LOG_SESSION_LOADING = os.getenv('LOG_SESSION_LOADING') == '1'
SESSION_CACHE_MAXSIZE = 2
SESSION_SUMMARY_CACHE_MAXSIZE = 12
EVENT_SCHEDULE_CACHE_MAXSIZE = 20
EVENT_SESSIONS_CACHE_MAXSIZE = 64

TEAM_COLOR_FALLBACKS = {
    # Current/recent canonical and feed-specific names.
    'mercedes': '#00D7B6',
    'mclaren': '#F47600',
    'redbull': '#4781D7',
    'redbullracing': '#4781D7',
    'ferrari': '#ED1131',
    'alpine': '#00A1E8',
    'alpinef1team': '#00A1E8',
    'williams': '#1868DB',
    'haas': '#9C9FA2',
    'haasf1team': '#9C9FA2',
    'audi': '#F50537',
    'racingbulls': '#6C98FF',
    'rb': '#6C98FF',
    'rbf1team': '#6C98FF',
    'astonmartin': '#229971',
    'cadillac': '#909090',
    'cadillacf1team': '#909090',
    # Older aliases still reachable in historical sessions.
    'alphatauri': '#2B4562',
    'alfaromeo': '#900000',
    'sauber': '#52E252',
    'stakesauber': '#52E252',
    'kicksauber': '#52E252',
    'renault': '#FFF500',
    'tororosso': '#469BFF',
    'racingpoint': '#F596C8',
    'forceindia': '#F596C8',
}

_COLOR_FALLBACK_PALETTE = (
    '#00D7B6', '#F47600', '#4781D7', '#ED1131', '#00A1E8',
    '#1868DB', '#9C9FA2', '#F50537', '#6C98FF', '#229971',
    '#B46CFF', '#FFD166'
)



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


def _normalize_color_value(value):
    """Return a CSS hex color or None for missing/invalid FastF1 color values."""
    if value is None or pd.isna(value):
        return None
    color = str(value).strip()
    if not color or color.lower() in ('none', 'nan'):
        return None
    if color.startswith('#'):
        color = color[1:]
    if len(color) == 3 and all(ch in '0123456789abcdefABCDEF' for ch in color):
        color = ''.join(ch * 2 for ch in color)
    if len(color) != 6 or not all(ch in '0123456789abcdefABCDEF' for ch in color):
        return None
    return f"#{color.upper()}"


def _team_color_key(team_name):
    return re.sub(r'[^a-z0-9]+', '', str(team_name or '').lower())


def _stable_fallback_color(identifier):
    digest = hashlib.sha1(str(identifier or 'unknown').encode('utf-8')).hexdigest()
    return _COLOR_FALLBACK_PALETTE[int(digest[:2], 16) % len(_COLOR_FALLBACK_PALETTE)]


def resolve_team_color(team_name, session=None, raw_color=None, fallback_identifier=None):
    """Resolve a readable team color even when live FastF1 metadata omits TeamColor."""
    raw = _normalize_color_value(raw_color)
    if raw and raw.lower() != '#ffffff':
        return raw

    team_key = _team_color_key(team_name)
    mapped = TEAM_COLOR_FALLBACKS.get(team_key)
    if mapped:
        return mapped

    if team_name:
        try:
            import fastf1.plotting
            plotted = _normalize_color_value(
                fastf1.plotting.get_team_color(str(team_name), session=session)
            )
            if plotted and plotted.lower() != '#ffffff':
                return plotted
        except Exception:
            pass

    if raw:
        return raw
    return _stable_fallback_color(fallback_identifier or team_name)


def resolve_driver_color(driver_abbr, session):
    """Resolve a driver's team color with production-safe fallbacks."""
    team = ''
    raw_color = None
    try:
        if getattr(session, 'results', None) is not None and not session.results.empty:
            row = session.results[session.results['Abbreviation'] == driver_abbr]
            if not row.empty:
                team = row.iloc[0].get('TeamName', '')
                raw_color = row.iloc[0].get('TeamColor', None)
    except Exception:
        pass

    color = resolve_team_color(team, session=session, raw_color=raw_color, fallback_identifier=driver_abbr)
    if color and color.lower() != '#ffffff':
        return color

    try:
        import fastf1.plotting
        plotted = _normalize_color_value(fastf1.plotting.get_driver_color(driver_abbr, session))
        if plotted and plotted.lower() != '#ffffff':
            return plotted
    except Exception:
        pass

    return color or _stable_fallback_color(driver_abbr)


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
    return fastf1.get_event_schedule(year, include_testing=False)


@lru_cache(maxsize=EVENT_SESSIONS_CACHE_MAXSIZE)
def get_event_sessions_cached(year, race):
    """LRU-cached session names for a specific event."""
    schedule = get_event_schedule_cached(int(year))
    event_rows = schedule[schedule['EventName'] == str(race)]
    if event_rows.empty:
        return tuple()
    event = event_rows.iloc[0]
    sessions = []
    for idx in range(1, 6):
        session_name = event.get(f'Session{idx}')
        if pd.notna(session_name) and session_name:
            sessions.append(str(session_name))
    return tuple(sessions)


def _coerce_utc_timestamp(value):
    """Return a timezone-aware UTC Timestamp or None for missing/unparseable values."""
    if value is None or pd.isna(value):
        return None
    try:
        ts = pd.Timestamp(value)
        if pd.isna(ts):
            return None
        if ts.tzinfo is None:
            return ts.tz_localize(timezone.utc)
        return ts.tz_convert(timezone.utc)
    except Exception:
        return None


def get_latest_race_session_default(now=None, first_year=2018):
    """Return the latest past race-session default as {year, race, session_type}.

    FastF1 schedules include future events, so this intentionally filters by
    session/event date before choosing the most recent Race. If a Race date is
    unavailable, EventDate is used as a conservative fallback.
    """
    now_ts = _coerce_utc_timestamp(now) or pd.Timestamp(datetime.now(timezone.utc))
    candidates = []

    for year in range(now_ts.year, int(first_year) - 1, -1):
        try:
            schedule = get_event_schedule_cached(int(year))
        except Exception:
            continue
        if schedule is None or schedule.empty:
            continue

        if 'EventFormat' in schedule.columns:
            schedule = schedule[schedule['EventFormat'] != 'testing'].copy()
        for _, event in schedule.iterrows():
            race_name = event.get('EventName')
            if not race_name:
                continue

            session_date = None
            for idx in range(1, 6):
                if event.get(f'Session{idx}') == 'Race':
                    session_date = (
                        _coerce_utc_timestamp(event.get(f'Session{idx}DateUtc'))
                        or _coerce_utc_timestamp(event.get(f'Session{idx}Date'))
                    )
                    break
            if session_date is None:
                session_date = _coerce_utc_timestamp(event.get('EventDate'))

            if session_date is not None and session_date <= now_ts:
                candidates.append((session_date, int(year), str(race_name), 'Race'))

    if not candidates:
        return None

    _, year, race, session_type = max(candidates, key=lambda item: item[0])
    logging.info("[latest_default] year=%s race=%s session=%s", year, race, session_type)
    return {'year': year, 'race': race, 'session_type': session_type}


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


def _preload_job_id(key):
    return "|".join(str(part) for part in key)


def _preload_profile(laps, telemetry, weather, messages):
    if telemetry and weather and messages:
        return "ai-context"
    if telemetry:
        return "telemetry"
    if weather:
        return "weather"
    if laps:
        return "laps"
    return "summary"


def _cleanup_preload_jobs_locked(now=None):
    now = now or time.time()
    if len(_SESSION_PRELOAD_JOBS) <= _MAX_TRACKED_PRELOAD_JOBS:
        return
    stale = [
        job_id for job_id, job in _SESSION_PRELOAD_JOBS.items()
        if now - float(job.get('updated_at', job.get('created_at', now))) > _PRELOAD_JOB_TTL_SECONDS
        and job.get('status') in ('ready', 'error')
    ]
    for job_id in stale:
        _SESSION_PRELOAD_JOBS.pop(job_id, None)
    if len(_SESSION_PRELOAD_JOBS) > _MAX_TRACKED_PRELOAD_JOBS:
        ordered = sorted(
            _SESSION_PRELOAD_JOBS.items(),
            key=lambda item: float(item[1].get('updated_at', item[1].get('created_at', 0)))
        )
        overflow = len(_SESSION_PRELOAD_JOBS) - _MAX_TRACKED_PRELOAD_JOBS
        for job_id, _ in ordered[:overflow]:
            _SESSION_PRELOAD_JOBS.pop(job_id, None)


def _ensure_preload_job_locked(key, status='queued', future=None):
    now = time.time()
    job_id = _preload_job_id(key)
    job = _SESSION_PRELOAD_JOBS.get(job_id)
    if job is None:
        job = {
            'id': job_id,
            'year': key[0],
            'race': key[1],
            'session': key[2],
            'laps': key[3],
            'telemetry': key[4],
            'weather': key[5],
            'messages': key[6],
            'profile': _preload_profile(key[3], key[4], key[5], key[6]),
            'status': status,
            'created_at': now,
            'updated_at': now,
            'error': '',
        }
        _SESSION_PRELOAD_JOBS[job_id] = job
    else:
        job['status'] = status
        job['updated_at'] = now
    if future is not None:
        job['future'] = future
    return job


def _safe_job_view(job):
    if not job:
        return {'status': 'idle'}
    clean = {
        key: value for key, value in job.items()
        if key != 'future'
    }
    return clean


def _run_preload_job(key):
    job_id = _preload_job_id(key)
    with _SESSION_PRELOAD_LOCK:
        job = _SESSION_PRELOAD_JOBS.get(job_id)
        if job is not None:
            job['status'] = 'loading'
            job['updated_at'] = time.time()
    try:
        from perf_monitor import record_session_event
        record_session_event('preload', key=job_id, status='loading')
    except Exception:
        pass

    try:
        result = _load_session_granular_cached(
            key[0], key[1], key[2], key[3], key[4], key[5], key[6]
        )
        with _SESSION_PRELOAD_LOCK:
            job = _SESSION_PRELOAD_JOBS.get(job_id)
            if job is not None:
                job['status'] = 'ready'
                job['updated_at'] = time.time()
                job['error'] = ''
        try:
            from perf_monitor import record_session_event
            record_session_event('preload', key=job_id, status='ready')
        except Exception:
            pass
        return result
    except Exception as exc:
        with _SESSION_PRELOAD_LOCK:
            job = _SESSION_PRELOAD_JOBS.get(job_id)
            if job is not None:
                job['status'] = 'error'
                job['updated_at'] = time.time()
                job['error'] = str(exc)[:240]
        try:
            from perf_monitor import record_session_event
            record_session_event('preload', key=job_id, status='error', error=exc)
        except Exception:
            pass
        raise


def preload_session(year, race, session_name, laps=True, telemetry=False, weather=False, messages=False):
    """Start loading a session profile in the background."""
    if not all([year, race, session_name]):
        return None

    key = _session_preload_key(year, race, session_name, laps, telemetry, weather, messages)
    with _SESSION_PRELOAD_LOCK:
        _cleanup_preload_jobs_locked()
        if len(_SESSION_PRELOAD_FUTURES) > _MAX_TRACKED_PRELOAD_FUTURES:
            done_keys = [k for k, fut in _SESSION_PRELOAD_FUTURES.items() if fut.done()]
            for old_key in done_keys[: len(_SESSION_PRELOAD_FUTURES) - _MAX_TRACKED_PRELOAD_FUTURES]:
                _SESSION_PRELOAD_FUTURES.pop(old_key, None)
        future = _SESSION_PRELOAD_FUTURES.get(key)
        # If no future or previous failed, start requested profile preload.
        if future is None or (future.done() and future.exception() is not None):
            _ensure_preload_job_locked(key, status='queued')
            future = _SESSION_PRELOAD_EXECUTOR.submit(_run_preload_job, key)
            _SESSION_PRELOAD_FUTURES[key] = future
            _ensure_preload_job_locked(key, status='queued', future=future)
            if LOG_SESSION_LOADING:
                logging.info(
                    "[session] preload started "
                    f"year={key[0]} race={key[1]} session={key[2]} "
                    f"laps={key[3]} telemetry={key[4]} weather={key[5]} messages={key[6]}"
                )
        elif future.done() and future.exception() is None:
            _ensure_preload_job_locked(key, status='ready', future=future)
        elif LOG_SESSION_LOADING:
            _ensure_preload_job_locked(key, status='loading', future=future)
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


def get_preload_status(year, race, session_name, laps=True, telemetry=False, weather=False, messages=False):
    """Return a JSON-safe status for a preload profile without loading data."""
    if not all([year, race, session_name]):
        return {'status': 'idle'}
    key = _session_preload_key(year, race, session_name, laps, telemetry, weather, messages)
    job_id = _preload_job_id(key)
    with _SESSION_PRELOAD_LOCK:
        job = _SESSION_PRELOAD_JOBS.get(job_id)
        if job is None:
            future = _SESSION_PRELOAD_FUTURES.get(key)
            if future is None:
                return {
                    'id': job_id,
                    'year': key[0],
                    'race': key[1],
                    'session': key[2],
                    'laps': key[3],
                    'telemetry': key[4],
                    'weather': key[5],
                    'messages': key[6],
                    'profile': _preload_profile(key[3], key[4], key[5], key[6]),
                    'status': 'idle',
                    'error': '',
                }
            status = 'ready' if future.done() and future.exception() is None else 'loading'
            job = _ensure_preload_job_locked(key, status=status, future=future)
        elif job.get('future') is not None:
            future = job['future']
            if future.done():
                try:
                    future.exception()
                except Exception:
                    pass
                job['status'] = 'ready' if future.exception() is None else 'error'
                job['updated_at'] = time.time()
        return _safe_job_view(job)


def get_preload_kwargs_for_tab(active_tab):
    """Map a dashboard tab to the data streams needed for that view."""
    kwargs = {'laps': True, 'telemetry': False, 'weather': False, 'messages': False}
    if active_tab in ('tab-telemetry', 'tab-trackmap'):
        kwargs['telemetry'] = True
    elif active_tab in ('tab-strategy', 'tab-gridpace'):
        kwargs['weather'] = True
    elif active_tab == 'tab-ai':
        kwargs.update({'telemetry': True, 'weather': True, 'messages': True})
    return kwargs


def get_preload_status_for_tab(params, active_tab):
    """Return preload status for the dashboard tab's data profile."""
    if not params:
        return {'status': 'idle'}
    kwargs = get_preload_kwargs_for_tab(active_tab)
    return get_preload_status(
        params.get('year'), params.get('race'), params.get('session_type'), **kwargs
    )


def ensure_preload_for_tab(params, active_tab):
    """Start the tab's preload profile if needed and return its status."""
    if not params:
        return {'status': 'idle'}
    kwargs = get_preload_kwargs_for_tab(active_tab)
    status = get_preload_status(
        params.get('year'), params.get('race'), params.get('session_type'), **kwargs
    )
    if status.get('status') == 'idle':
        preload_session(
            params.get('year'), params.get('race'), params.get('session_type'), **kwargs
        )
        status = get_preload_status(
            params.get('year'), params.get('race'), params.get('session_type'), **kwargs
        )
    return status


def get_preload_registry_snapshot():
    """Return a compact snapshot of tracked preload jobs."""
    with _SESSION_PRELOAD_LOCK:
        jobs = [_safe_job_view(job) for job in _SESSION_PRELOAD_JOBS.values()]
    jobs.sort(key=lambda item: float(item.get('updated_at', item.get('created_at', 0))), reverse=True)
    return jobs[:_MAX_TRACKED_PRELOAD_JOBS]


def get_cache_stats():
    """Return cheap cache stats for the admin perf panel."""
    stats = {
        'cache_dir': _CACHE_DIR,
        'cache_ready': _CACHE_READY,
        'cache_size_bytes': 0,
        'session_cache': _load_session_granular_cached.cache_info()._asdict(),
        'summary_cache': _load_session_summary_cached.cache_info()._asdict(),
        'schedule_cache': get_event_schedule_cached.cache_info()._asdict(),
    }
    try:
        if os.path.exists(_CACHE_DIR):
            stats['cache_size_bytes'] = _cache_size_bytes(_CACHE_DIR)
    except Exception:
        stats['cache_size_bytes'] = 0
    return stats


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

        color = resolve_team_color(
            team,
            session=session,
            raw_color=row.get('TeamColor', None),
            fallback_identifier=abbr,
        )

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
    return resolve_driver_color(driver_abbr, session)


@lru_cache(maxsize=16)
def _compute_labels_colors(year, race, session_type, d1, d2):
    """LRU-cached driver labels (with finishing position) and team colors.

    Separated from session loading so that different data-stream
    combinations (telemetry vs. weather) share a single cache entry.
    """
    session = load_session_summary(year, race, session_type, include_laps=False)

    c1, c2 = resolve_driver_color(d1, session), resolve_driver_color(d2, session)
    if c1.lower() == c2.lower():
        c2 = '#ffffff' if c1.lower() != '#ffffff' else '#ffff00'
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
