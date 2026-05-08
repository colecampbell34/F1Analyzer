"""AI response cache and simple per-user rate limiting."""
import json
import os
import time
import hashlib
import threading
import logging
from collections import defaultdict
from datetime import datetime, timezone


_RATE_LIMIT_LOCK = threading.Lock()
_USER_DAILY_USAGE = defaultdict(int)
USER_DAILY_LIMIT = 10
_daily_reset_date = None


def _runtime_dir(env_name, local_name):
    configured = os.getenv(env_name)
    if configured:
        return configured
    if os.getenv('VERCEL'):
        return os.path.join('/tmp', local_name)
    return local_name


_AI_CACHE_DIR = _runtime_dir('AI_CACHE_DIR', 'ai_cache')
_AI_CACHE_FILE = os.path.join(_AI_CACHE_DIR, 'responses.json')
_AI_CACHE_LOCK = threading.Lock()
_AI_RESPONSE_CACHE = {}
MAX_CACHE_SIZE = 100
_AI_CACHE_FLUSH_SECONDS = 30
_AI_CACHE_RETENTION_DAYS = 10
_AI_CACHE_DIRTY = False
_AI_CACHE_LAST_FLUSH = 0.0


def _load_cache_from_disk():
    global _AI_RESPONSE_CACHE
    try:
        if os.path.exists(_AI_CACHE_FILE):
            with open(_AI_CACHE_FILE, 'r', encoding='utf-8') as f:
                raw = json.load(f)

            if isinstance(raw, dict):
                if raw and all(isinstance(v, str) for v in raw.values()):
                    now_ts = time.time()
                    _AI_RESPONSE_CACHE = {
                        key: {'response': val, 'stored_at': now_ts}
                        for key, val in raw.items()
                    }
                else:
                    _AI_RESPONSE_CACHE = raw
            else:
                _AI_RESPONSE_CACHE = {}

            _prune_ai_cache_unlocked()
    except (json.JSONDecodeError, IOError):
        logging.warning("[ai_cache] failed to load cache from disk", exc_info=True)
        _AI_RESPONSE_CACHE = {}


def _save_cache_to_disk():
    try:
        os.makedirs(_AI_CACHE_DIR, exist_ok=True)
        with open(_AI_CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(_AI_RESPONSE_CACHE, f, ensure_ascii=False)
    except IOError:
        logging.warning("[ai_cache] failed to save cache to disk", exc_info=True)


def _prune_ai_cache_unlocked():
    now_ts = time.time()
    if _AI_CACHE_RETENTION_DAYS > 0:
        cutoff = now_ts - (_AI_CACHE_RETENTION_DAYS * 86400)
        stale_keys = [
            k for k, v in _AI_RESPONSE_CACHE.items()
            if isinstance(v, dict) and float(v.get('stored_at', 0)) < cutoff
        ]
        for key in stale_keys:
            del _AI_RESPONSE_CACHE[key]

    if len(_AI_RESPONSE_CACHE) > MAX_CACHE_SIZE:
        keys_by_age = sorted(
            _AI_RESPONSE_CACHE.keys(),
            key=lambda k: float(_AI_RESPONSE_CACHE.get(k, {}).get('stored_at', 0))
        )
        overflow = len(_AI_RESPONSE_CACHE) - MAX_CACHE_SIZE
        for key in keys_by_age[:overflow]:
            del _AI_RESPONSE_CACHE[key]


def _maybe_flush_cache_unlocked(force=False):
    global _AI_CACHE_DIRTY, _AI_CACHE_LAST_FLUSH
    now_ts = time.time()
    if not _AI_CACHE_DIRTY:
        return
    if not force and (now_ts - _AI_CACHE_LAST_FLUSH) < _AI_CACHE_FLUSH_SECONDS:
        return
    _save_cache_to_disk()
    _AI_CACHE_LAST_FLUSH = now_ts
    _AI_CACHE_DIRTY = False


def flush_ai_cache():
    with _AI_CACHE_LOCK:
        _maybe_flush_cache_unlocked(force=True)


def check_user_limit(ip):
    """Return (allowed, current_count) after applying the daily request limit."""
    global _daily_reset_date
    today = datetime.now(timezone.utc).date()

    with _RATE_LIMIT_LOCK:
        if _daily_reset_date != today:
            _USER_DAILY_USAGE.clear()
            _daily_reset_date = today

        current_usage = _USER_DAILY_USAGE[ip]
        if current_usage >= USER_DAILY_LIMIT:
            logging.info("[ai_rate_limit] denied ip=%s count=%s", ip, current_usage)
            return False, current_usage

        _USER_DAILY_USAGE[ip] += 1
        return True, _USER_DAILY_USAGE[ip]


def _cache_key(session_context, question):
    q_normalized = question.lower().strip()
    raw = (session_context or '') + '||' + q_normalized
    return hashlib.sha256(raw.encode()).hexdigest()


def get_cached_response(session_context, question):
    key = _cache_key(session_context, question)
    with _AI_CACHE_LOCK:
        item = _AI_RESPONSE_CACHE.get(key)
        if isinstance(item, dict):
            logging.info("[ai_cache] hit key=%s", key[:10])
            return item.get('response')
        if isinstance(item, str):
            logging.info("[ai_cache] hit legacy key=%s", key[:10])
            return item
        logging.info("[ai_cache] miss key=%s", key[:10])
        return None


def store_cached_response(session_context, question, response):
    global _AI_CACHE_DIRTY
    with _AI_CACHE_LOCK:
        key = _cache_key(session_context, question)
        _AI_RESPONSE_CACHE[key] = {
            'response': response,
            'stored_at': time.time()
        }
        _prune_ai_cache_unlocked()
        _AI_CACHE_DIRTY = True
        _maybe_flush_cache_unlocked()


_load_cache_from_disk()
