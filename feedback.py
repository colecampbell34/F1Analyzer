import os
import json
import uuid
import hashlib
import threading
from datetime import datetime, timezone

_FEEDBACK_LOCK = threading.Lock()
_FEEDBACK_DIR = 'feedback'
_FEEDBACK_FILE = os.path.join(_FEEDBACK_DIR, 'entries.jsonl')


def setup_feedback_storage():
    """Ensure the feedback inbox storage exists."""
    os.makedirs(_FEEDBACK_DIR, exist_ok=True)
    if not os.path.exists(_FEEDBACK_FILE):
        with open(_FEEDBACK_FILE, 'a', encoding='utf-8'):
            pass


def _hash_feedback_ip(raw_ip):
    if not raw_ip:
        return 'anonymous'
    return hashlib.sha256(str(raw_ip).encode('utf-8')).hexdigest()[:12]


def store_feedback_entry(payload, raw_ip=None, user_agent=None):
    """Append a feedback entry to the JSONL inbox and return the stored record."""
    setup_feedback_storage()

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

    return entry


def load_feedback_entries(limit=None):
    """Return feedback entries sorted newest-first."""
    setup_feedback_storage()

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
