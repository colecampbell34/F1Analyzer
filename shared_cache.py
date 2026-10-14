"""Optional, safe shared-cache access for serverless deployments.

The cache is intentionally an optimisation: FastF1 remains the source of
truth and a cache timeout must never stop a dashboard callback.  Upstash's
REST endpoint is used directly so this module adds no connection-pool or
native dependency to the Vercel bundle.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import threading
import time
import urllib.error
import urllib.request
import zlib
from collections import Counter


_STATS_LOCK = threading.Lock()
_STATS = Counter()
_LAST_ERROR = ''
_DEFAULT_TIMEOUT_SECONDS = 1.25
_MAX_VALUE_BYTES = 900_000


def _env_float(name, default, minimum=None, maximum=None):
    try:
        value = float(os.getenv(name, default))
    except (TypeError, ValueError):
        value = default
    if minimum is not None:
        value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


def _redis_rest_config():
    """Return configured Upstash REST credentials without exposing secrets."""
    if str(os.getenv('F1_ANALYZER_SHARED_CACHE_ENABLED', '1')).lower() in ('0', 'false', 'no', 'off'):
        return None
    # Vercel's Upstash integration currently exposes the KV_* names shown in
    # the project environment screen. Direct Upstash connections commonly use
    # UPSTASH_REDIS_REST_*. Support both, plus explicit app aliases.
    url = (
        os.getenv('F1_ANALYZER_REDIS_REST_URL')
        or os.getenv('UPSTASH_REDIS_REST_URL')
        or os.getenv('KV_REST_API_URL')
    )
    token = (
        os.getenv('F1_ANALYZER_REDIS_REST_TOKEN')
        or os.getenv('UPSTASH_REDIS_REST_TOKEN')
        or os.getenv('KV_REST_API_TOKEN')
    )
    if not url or not token:
        return None
    return str(url).rstrip('/'), str(token)


def is_configured():
    """Return whether this process has a usable shared-cache configuration."""
    return _redis_rest_config() is not None


def _record(name, error=None):
    global _LAST_ERROR
    with _STATS_LOCK:
        _STATS[name] += 1
        if error:
            _LAST_ERROR = str(error)[:160]


def _command(arguments):
    """Run one Upstash Redis REST command, returning its result or ``None``.

    The public API has a command-array POST format.  It avoids placing a large
    compressed telemetry payload or credentials in a URL, and works well in a
    short-lived Vercel function.
    """
    config = _redis_rest_config()
    if config is None:
        return None
    url, token = config
    timeout = _env_float('F1_ANALYZER_REDIS_TIMEOUT_SECONDS', _DEFAULT_TIMEOUT_SECONDS, 0.2, 5.0)
    payload = json.dumps(list(arguments), separators=(',', ':')).encode('utf-8')
    request = urllib.request.Request(
        url,
        data=payload,
        headers={
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json',
            'User-Agent': 'f1-analyzer-shared-cache/1',
        },
        method='POST',
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = json.loads(response.read().decode('utf-8'))
        if body.get('error'):
            raise RuntimeError(body['error'])
        return body.get('result')
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError, OSError, RuntimeError) as exc:
        _record('errors', error=exc)
        logging.warning('[shared-cache] Redis request skipped: %s', exc)
        return None


def _encode(value):
    raw = json.dumps(value, separators=(',', ':'), allow_nan=False).encode('utf-8')
    packed = b'z1:' + base64.urlsafe_b64encode(zlib.compress(raw, level=6))
    if len(packed) > _MAX_VALUE_BYTES:
        raise ValueError('prepared payload exceeds the shared-cache value limit')
    return packed.decode('ascii')


def _decode(value):
    if not isinstance(value, str) or not value.startswith('z1:'):
        raise ValueError('unknown shared-cache payload format')
    raw = zlib.decompress(base64.urlsafe_b64decode(value[3:].encode('ascii')))
    return json.loads(raw.decode('utf-8'))


def get_json(key):
    """Return one JSON-safe cached value, or ``None`` on a cache miss/failure."""
    if not is_configured():
        return None
    value = _command(('GET', key))
    if value is None:
        _record('misses')
        return None
    try:
        decoded = _decode(value)
    except (ValueError, TypeError, zlib.error) as exc:
        _record('corrupt_values', error=exc)
        _command(('DEL', key))
        return None
    _record('hits')
    return decoded


def set_json(key, value, ttl_seconds):
    """Store a JSON-safe value with TTL. Failures are deliberately non-fatal."""
    if not is_configured():
        return False
    try:
        encoded = _encode(value)
    except (TypeError, ValueError) as exc:
        _record('skipped_writes', error=exc)
        logging.warning('[shared-cache] Not caching payload: %s', exc)
        return False
    result = _command(('SET', key, encoded, 'EX', max(1, int(ttl_seconds))))
    if result == 'OK':
        _record('writes')
        return True
    return False


def acquire_lock(key, ttl_seconds=75):
    """Attempt a short Redis lock to avoid duplicate FastF1 cold loads."""
    if not is_configured():
        return None
    result = _command(('SET', key, '1', 'NX', 'EX', max(1, int(ttl_seconds))))
    if result == 'OK':
        _record('locks_acquired')
        return True
    if result is None:
        return None
    _record('locks_contended')
    return False


def release_lock(key):
    """Best-effort lock release after its associated value was written."""
    if not is_configured():
        return
    _command(('DEL', key))


def wait_for_json(key, wait_seconds):
    """Wait for another Vercel instance to populate a cache miss.

    Back off polling to avoid turning one cold telemetry request into hundreds
    of Upstash reads when several Dash callbacks arrive together.
    """
    deadline = time.monotonic() + max(0.0, float(wait_seconds))
    delay = 0.35
    while time.monotonic() < deadline:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        time.sleep(min(delay, remaining))
        value = get_json(key)
        if value is not None:
            _record('lock_wait_hits')
            return value
        delay = min(2.0, delay * 1.6)
    return None


def get_stats():
    """Expose JSON-safe diagnostics without leaking URLs or credentials."""
    with _STATS_LOCK:
        stats = dict(_STATS)
        last_error = _LAST_ERROR
    return {
        'configured': is_configured(),
        'backend': 'upstash-rest' if is_configured() else 'disabled',
        'stats': stats,
        'last_error': last_error,
    }


def reset_for_tests():
    """Clear in-process observability counters. Intended for focused tests."""
    global _LAST_ERROR
    with _STATS_LOCK:
        _STATS.clear()
        _LAST_ERROR = ''
