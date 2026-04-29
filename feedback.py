import os
import json
import uuid
import hashlib
import threading
import logging
from datetime import datetime, timezone

_FEEDBACK_LOCK = threading.Lock()
_FEEDBACK_DIR = 'feedback'
_FEEDBACK_FILE = os.path.join(_FEEDBACK_DIR, 'entries.jsonl')
_FEEDBACK_MAX_ENTRIES = 2000
_FEEDBACK_RETENTION_DAYS = 90
_FEEDBACK_PRUNE_INTERVAL_SECONDS = 1800
_LAST_FEEDBACK_PRUNE_TS = 0.0
_STORAGE_READY = False


def setup_feedback_storage():
    """Ensure the feedback inbox storage exists."""
    global _STORAGE_READY
    os.makedirs(_FEEDBACK_DIR, exist_ok=True)
    if not os.path.exists(_FEEDBACK_FILE):
        with open(_FEEDBACK_FILE, 'a', encoding='utf-8'):
            pass
    _STORAGE_READY = True
    prune_feedback_storage()


def _parse_iso_timestamp(ts):
    try:
        return datetime.fromisoformat(str(ts).replace('Z', '+00:00'))
    except (TypeError, ValueError):
        return None


def prune_feedback_storage():
    """Prune old/overflow feedback records while preserving newest entries."""
    global _LAST_FEEDBACK_PRUNE_TS
    now_ts = datetime.now(timezone.utc).timestamp()
    if _LAST_FEEDBACK_PRUNE_TS and (now_ts - _LAST_FEEDBACK_PRUNE_TS) < _FEEDBACK_PRUNE_INTERVAL_SECONDS:
        return
    if not os.path.exists(_FEEDBACK_FILE):
        return

    with _FEEDBACK_LOCK:
        with open(_FEEDBACK_FILE, 'r', encoding='utf-8') as f:
            raw_lines = f.readlines()

        entries = []
        for line in raw_lines:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue

        if not entries:
            return

        now = datetime.now(timezone.utc)
        kept = []
        for entry in entries:
            ts = _parse_iso_timestamp(entry.get('submitted_at'))
            if _FEEDBACK_RETENTION_DAYS > 0 and ts is not None:
                age_days = (now - ts).days
                if age_days > _FEEDBACK_RETENTION_DAYS:
                    continue
            kept.append(entry)

        kept.sort(key=lambda item: item.get('submitted_at', ''), reverse=True)
        if _FEEDBACK_MAX_ENTRIES > 0:
            kept = kept[:_FEEDBACK_MAX_ENTRIES]

        with open(_FEEDBACK_FILE, 'w', encoding='utf-8') as f:
            for entry in kept:
                f.write(json.dumps(entry, ensure_ascii=True) + '\n')
        _LAST_FEEDBACK_PRUNE_TS = now_ts


def _hash_feedback_ip(raw_ip):
    if not raw_ip:
        return 'anonymous'
    return hashlib.sha256(str(raw_ip).encode('utf-8')).hexdigest()[:12]


def store_feedback_entry(payload, raw_ip=None, user_agent=None):
    """Append a feedback entry to the JSONL inbox and return the stored record."""
    if not _STORAGE_READY:
        setup_feedback_storage()
    else:
        prune_feedback_storage()

    session = payload.get('session') or {}
    entry = {
        'id': uuid.uuid4().hex[:12],
        'submitted_at': datetime.now(timezone.utc).isoformat(),
        'category': str(payload.get('category') or 'general').strip().lower(),
        'rating': int(payload.get('rating') or 0),
        'message': str(payload.get('message') or '').strip(),
        'contact': str(payload.get('contact') or '').strip(),
        'active_tab': str(payload.get('active_tab') or '').strip(),
        'session': {
            'year': session.get('year'),
            'race': session.get('race'),
            'session_type': session.get('session_type'),
            'driver1': session.get('driver1'),
            'driver2': session.get('driver2')
        },
        'context_loaded': bool(payload.get('context_loaded')),
        'ip_hash': _hash_feedback_ip(raw_ip),
        'user_agent': (str(user_agent).strip()[:180] if user_agent else ''),
        'status': 'new'
    }

    with _FEEDBACK_LOCK:
        with open(_FEEDBACK_FILE, 'a', encoding='utf-8') as f:
            f.write(json.dumps(entry, ensure_ascii=True) + '\n')

    logging.info(
        "[feedback] stored id=%s category=%s rating=%s tab=%s context=%s",
        entry['id'], entry['category'], entry['rating'], entry['active_tab'], entry['context_loaded']
    )
    return entry


def load_feedback_entries(limit=None):
    """Return feedback entries sorted newest-first."""
    if not _STORAGE_READY:
        setup_feedback_storage()
    else:
        prune_feedback_storage()

    with _FEEDBACK_LOCK:
        with open(_FEEDBACK_FILE, 'r', encoding='utf-8') as f:
            lines = f.readlines()

    entries = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    entries.sort(key=lambda item: item.get('submitted_at', ''), reverse=True)
    if limit is not None:
        return entries[:limit]
    return entries
