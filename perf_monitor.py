"""In-process performance snapshots for lightweight admin observability."""
import threading
import time
from collections import Counter, deque


_LOCK = threading.Lock()
_CALLBACK_TIMINGS = deque(maxlen=240)
_SESSION_EVENTS = deque(maxlen=120)


def record_callback_timing(name, elapsed_ms, fields=None, trigger=None):
    """Store one callback timing sample."""
    with _LOCK:
        _CALLBACK_TIMINGS.append({
            "name": str(name),
            "elapsed_ms": round(float(elapsed_ms), 1),
            "trigger": str(trigger or ""),
            "fields": dict(fields or {}),
            "ts": time.time(),
        })


def record_session_event(event, key=None, status=None, error=None):
    """Store a compact session/preload lifecycle event."""
    with _LOCK:
        _SESSION_EVENTS.append({
            "event": str(event),
            "key": str(key or ""),
            "status": str(status or ""),
            "error": str(error or "")[:240],
            "ts": time.time(),
        })


def _summarize_callbacks(samples):
    by_name = {}
    for sample in samples:
        bucket = by_name.setdefault(sample["name"], [])
        bucket.append(float(sample["elapsed_ms"]))

    summary = []
    for name, values in by_name.items():
        values_sorted = sorted(values)
        count = len(values_sorted)
        p95 = values_sorted[min(count - 1, int(count * 0.95))]
        summary.append({
            "name": name,
            "count": count,
            "avg_ms": round(sum(values_sorted) / count, 1),
            "p95_ms": round(p95, 1),
            "max_ms": round(values_sorted[-1], 1),
        })
    return sorted(summary, key=lambda item: item["max_ms"], reverse=True)


def get_perf_snapshot():
    """Return a JSON-safe rolling performance snapshot."""
    with _LOCK:
        callbacks = list(_CALLBACK_TIMINGS)
        session_events = list(_SESSION_EVENTS)

    slow_callbacks = [
        sample for sample in callbacks
        if sample["elapsed_ms"] >= 400
    ][-20:]
    status_counts = Counter(event.get("status") for event in session_events if event.get("status"))

    return {
        "callback_count": len(callbacks),
        "callbacks_by_name": _summarize_callbacks(callbacks)[:20],
        "recent_slow_callbacks": list(reversed(slow_callbacks)),
        "session_event_count": len(session_events),
        "session_status_counts": dict(status_counts),
        "recent_session_events": list(reversed(session_events[-20:])),
        "generated_at": time.time(),
    }


def reset_perf_snapshot():
    """Clear rolling performance state. Intended for tests only."""
    with _LOCK:
        _CALLBACK_TIMINGS.clear()
        _SESSION_EVENTS.clear()
