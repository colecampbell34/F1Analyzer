"""Provider-neutral, validated OpenF1 session data.

The module keeps OpenF1's wire schema at the HTTP boundary and exposes small
normalized pandas frames to the dashboard. Historical endpoint responses are
cached as bounded JSON data; telemetry is requested only for a selected lap.
"""
from __future__ import annotations

from collections import OrderedDict, deque
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import json
import logging
import math
import re
import ssl
import threading
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import certifi
import numpy as np
import pandas as pd


OPENF1_BASE_URL = "https://api.openf1.org/v1"
JOLPICA_BASE_URL = "https://api.jolpi.ca/ergast/f1"
MULTIVIEWER_BASE_URL = "https://api.multiviewer.app"
SCHEMA_VERSION = 1
_MAX_BODY_BYTES = 8_000_000
_CACHE_MAX_ITEMS = 512
_CACHE_MAX_BYTES = 64_000_000
_CACHE = OrderedDict()
_CACHE_LOCK = threading.RLock()
_CACHE_BYTES = 0
_REQUEST_LOCK = threading.Lock()
_REQUEST_TIMES: deque[float] = deque()
_LAST_REQUEST_AT = 0.0
_REQUEST_COUNT = 0
_ERROR_COUNT = 0
_RESPONSE_BYTES = 0
_ENDPOINT_METRICS: dict[str, dict[str, int]] = {}
_ENDPOINTS = {
    "meetings", "sessions", "drivers", "laps", "car_data", "location",
    "intervals", "position", "pit", "stints", "weather", "race_control",
    "session_result", "starting_grid",
}
# Some Python installations (notably framework builds on macOS) do not use the
# system keychain as urllib's default CA source. Use certifi's maintained bundle
# for provider HTTPS requests so local and hosted Python runtimes verify the
# same public certificates.
_SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
_SAFE_QUERY_FIELDS = {
    "year", "meeting_key", "session_key", "driver_number", "lap_number",
    "date", "category", "flag", "scope", "position", "is_pit_out_lap",
}


class ProviderError(RuntimeError):
    """A sanitized, user-safe provider failure."""

    def __init__(self, message: str, *, kind: str = "unavailable", endpoint: str | None = None):
        super().__init__(message)
        self.kind = kind
        self.endpoint = endpoint


@dataclass(frozen=True)
class SessionRef:
    year: int
    round: int
    event_name: str
    country_name: str
    session_name: str
    session_type: str
    session_key: int
    meeting_key: int
    date_start: str | None = None
    date_end: str | None = None
    circuit_key: int | None = None
    circuit_short_name: str = ""
    circuit_info_url: str | None = None
    is_cancelled: bool = False

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SessionBundle:
    """Normalized data for one OpenF1 session.

    Frame columns are provider-neutral and nullable unless noted. `laps` uses
    seconds for durations; `race_control`, `positions`, `intervals`, `pits`,
    and `stints` retain UTC timestamps and source provenance in `quality`.
    """

    ref: SessionRef
    drivers: pd.DataFrame = field(default_factory=pd.DataFrame)
    results: pd.DataFrame = field(default_factory=pd.DataFrame)
    grid: pd.DataFrame = field(default_factory=pd.DataFrame)
    laps: pd.DataFrame = field(default_factory=pd.DataFrame)
    stints: pd.DataFrame = field(default_factory=pd.DataFrame)
    pits: pd.DataFrame = field(default_factory=pd.DataFrame)
    weather: pd.DataFrame = field(default_factory=pd.DataFrame)
    messages: pd.DataFrame = field(default_factory=pd.DataFrame)
    positions: pd.DataFrame = field(default_factory=pd.DataFrame)
    intervals: pd.DataFrame = field(default_factory=pd.DataFrame)
    circuit_corners: pd.DataFrame = field(default_factory=pd.DataFrame)
    quality: dict[str, Any] = field(default_factory=dict)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _as_int(value: Any) -> int | None:
    try:
        if value is None or pd.isna(value):
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, (int, float, np.number)):
        return bool(value) if math.isfinite(float(value)) else None
    if isinstance(value, str):
        normalized = value.strip().casefold()
        if normalized in {"true", "1", "yes", "y"}:
            return True
        if normalized in {"false", "0", "no", "n", ""}:
            return False
    return None


def _driver_number(value: Any) -> str:
    return "" if value is None or pd.isna(value) else str(value).strip()


def _number(value: Any) -> float | None:
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def _is_red_flag_event(event: dict[str, Any], text: str | None = None) -> bool:
    """Match an actual red flag without treating CHEQUERED FLAG as one."""
    flag = str(event.get("flag") or "").strip().casefold()
    if flag in {"red", "red flag"}:
        return True
    message = text if text is not None else " ".join(
        str(event.get(key) or "") for key in ("category", "message")
    ).casefold()
    return re.search(r"(?<![a-z])red\s+flag\b", message) is not None


def _time_seconds(value: Any) -> float | None:
    numeric = _number(value)
    if numeric is not None:
        return numeric
    if not isinstance(value, str) or ":" not in value:
        return None
    try:
        minutes, seconds = value.split(":", 1)
        return float(minutes) * 60 + float(seconds)
    except (TypeError, ValueError):
        return None


def _timestamp(value: Any) -> pd.Timestamp:
    return pd.to_datetime(value, utc=True, errors="coerce")


def _cache_ttl(query: dict[str, Any], endpoint: str, value: Any) -> int:
    if endpoint in {"session_result", "starting_grid"} and value == []:
        # Results can lag the end of the race; don't preserve a pending result
        # for the full historical retention window.
        return 5 * 60
    if query.get("session_key") is not None:
        return 30 * 24 * 3600
    year = _as_int(query.get("year"))
    if year and year < _utc_now().year:
        return 30 * 24 * 3600
    return 6 * 3600


def _retry_after_seconds(headers) -> float:
    value = headers.get("Retry-After") if headers else None
    seconds = _number(value)
    if seconds is not None:
        return max(0.0, seconds)
    if value:
        try:
            retry_at = parsedate_to_datetime(str(value))
            if retry_at.tzinfo is None:
                retry_at = retry_at.replace(tzinfo=timezone.utc)
            return max(0.0, (retry_at - _utc_now()).total_seconds())
        except (TypeError, ValueError, OverflowError):
            pass
    return 2.0


def _cache_get(key: tuple[Any, ...]):
    global _CACHE_BYTES
    now = time.monotonic()
    with _CACHE_LOCK:
        item = _CACHE.get(key)
        if item is None:
            return None
        expires, value, size = item
        if expires <= now:
            del _CACHE[key]
            _CACHE_BYTES = max(0, _CACHE_BYTES - size)
            return None
        _CACHE.move_to_end(key)
        return json.loads(json.dumps(value))


def _cache_set(key: tuple[Any, ...], value: Any, ttl: int):
    global _CACHE_BYTES
    try:
        encoded = json.dumps(value, allow_nan=False, separators=(",", ":"))
        size = len(encoded.encode("utf-8"))
        if size > _MAX_BODY_BYTES:
            return
        safe = json.loads(encoded)
    except (TypeError, ValueError):
        return
    with _CACHE_LOCK:
        previous = _CACHE.pop(key, None)
        if previous is not None:
            _CACHE_BYTES = max(0, _CACHE_BYTES - previous[2])
        _CACHE[key] = (time.monotonic() + ttl, safe, size)
        _CACHE_BYTES += size
        _CACHE.move_to_end(key)
        while len(_CACHE) > _CACHE_MAX_ITEMS or _CACHE_BYTES > _CACHE_MAX_BYTES:
            _old_key, old_item = _CACHE.popitem(last=False)
            _CACHE_BYTES = max(0, _CACHE_BYTES - old_item[2])


def clear_provider_cache():
    """Clear process-local endpoint cache; intended for tests/diagnostics."""
    global _CACHE_BYTES
    with _CACHE_LOCK:
        _CACHE.clear()
        _CACHE_BYTES = 0


def provider_stats() -> dict[str, Any]:
    with _CACHE_LOCK:
        cache_entries, cache_bytes = len(_CACHE), _CACHE_BYTES
    with _REQUEST_LOCK:
        return {
            "requests": _REQUEST_COUNT, "errors": _ERROR_COUNT,
            "response_bytes": _RESPONSE_BYTES,
            "cache_entries": cache_entries, "cache_bytes": cache_bytes,
            "endpoints": {key: value.copy() for key, value in _ENDPOINT_METRICS.items()},
        }


def _cache_key(provider: str, endpoint: str, url: str, query: dict[str, Any]) -> tuple[Any, ...]:
    return provider, endpoint, SCHEMA_VERSION, url, tuple(sorted((str(k), str(v)) for k, v in query.items()))


def _wait_for_request_slot():
    """Stay below OpenF1's published public ceiling within this process."""
    global _LAST_REQUEST_AT
    while True:
        with _REQUEST_LOCK:
            now = time.monotonic()
            while _REQUEST_TIMES and now - _REQUEST_TIMES[0] >= 60:
                _REQUEST_TIMES.popleft()
            spacing = max(0.0, 0.45 - (now - _LAST_REQUEST_AT))
            minute_wait = max(0.0, 60.0 - (now - _REQUEST_TIMES[0])) if len(_REQUEST_TIMES) >= 25 else 0.0
            delay = max(spacing, minute_wait)
            if delay <= 0:
                _REQUEST_TIMES.append(now)
                _LAST_REQUEST_AT = now
                return
        time.sleep(min(delay, 60.0))


def _get_json(url: str, *, endpoint: str, provider: str, query: dict[str, Any], use_cache=True):
    global _REQUEST_COUNT, _ERROR_COUNT, _RESPONSE_BYTES
    key = _cache_key(provider, endpoint, url, query)
    if use_cache:
        cached = _cache_get(key)
        if cached is not None:
            return cached
    encoded = urlencode([(key, value) for key, value in query.items()], doseq=True)
    full_url = f"{url}?{encoded}" if encoded else url
    is_openf1 = provider == "openf1"
    attempts = 3
    for attempt in range(attempts):
        if is_openf1:
            _wait_for_request_slot()
        request = Request(
            full_url,
            headers={
                "Accept": "application/json",
                "User-Agent": "F1Analyzer/2.0 (+https://github.com/colecampbell/F1Analyzer)",
            },
        )
        try:
            with urlopen(request, timeout=12, context=_SSL_CONTEXT) as response:
                body = response.read(_MAX_BODY_BYTES + 1)
                if len(body) > _MAX_BODY_BYTES:
                    raise ProviderError("The provider response exceeded the safe size limit.", kind="oversize", endpoint=endpoint)
                parsed = json.loads(body.decode("utf-8"))
            if not isinstance(parsed, (list, dict)):
                raise ProviderError("The provider returned an invalid JSON structure.", kind="malformed", endpoint=endpoint)
            if use_cache:
                _cache_set(key, parsed, _cache_ttl(query, endpoint, parsed))
            with _REQUEST_LOCK:
                _REQUEST_COUNT += 1
                _RESPONSE_BYTES += len(body)
                metric = _ENDPOINT_METRICS.setdefault(f"{provider}.{endpoint}", {"requests": 0, "response_bytes": 0, "records": 0})
                metric["requests"] += 1
                metric["response_bytes"] += len(body)
                metric["records"] += len(parsed) if isinstance(parsed, list) else 1
            return parsed
        except HTTPError as exc:
            with _REQUEST_LOCK:
                _ERROR_COUNT += 1
            if exc.code == 429:
                retry = _retry_after_seconds(exc.headers)
                # Retry only when the provider's requested delay fits the
                # bounded wait budget; never retry earlier than it asked.
                if attempt == 0 and retry <= 8.0:
                    time.sleep(retry)
                    continue
            if 500 <= exc.code < 600 and attempt < attempts - 1:
                time.sleep(min(2.0, 0.5 * (2 ** attempt)))
                continue
            kind = "rate_limited" if exc.code == 429 else "not_found" if exc.code == 404 else "http_error"
            raise ProviderError(
                "The data provider is temporarily rate limiting requests." if kind == "rate_limited"
                else "This session or data endpoint is not available." if kind == "not_found"
                else "The data provider could not complete this request.",
                kind=kind, endpoint=endpoint,
            ) from None
        except (URLError, TimeoutError, OSError) as exc:
            with _REQUEST_LOCK:
                _ERROR_COUNT += 1
            if attempt < attempts - 1:
                time.sleep(min(2.0, 0.5 * (2 ** attempt)))
                continue
            logging.warning("provider_request_failed provider=%s endpoint=%s cause_type=%s", provider, endpoint, type(exc).__name__)
            raise ProviderError("The data provider did not respond. Please retry shortly.", kind="network", endpoint=endpoint) from None
        except (json.JSONDecodeError, UnicodeDecodeError):
            with _REQUEST_LOCK:
                _ERROR_COUNT += 1
            raise ProviderError("The data provider returned malformed data.", kind="malformed", endpoint=endpoint) from None
    raise ProviderError("The data provider could not complete this request.", endpoint=endpoint)


def _openf1_records(endpoint: str, query: dict[str, Any] | None = None, *, use_cache=True) -> list[dict[str, Any]]:
    if endpoint not in _ENDPOINTS:
        raise ValueError("Unsupported OpenF1 endpoint.")
    query = query or {}
    for field_name in query:
        base = next(
            (field_name[:-len(operator)] for operator in (">=", "<=", ">", "<", "=") if field_name.endswith(operator)),
            field_name,
        )
        if base not in _SAFE_QUERY_FIELDS:
            raise ValueError(f"Unsupported OpenF1 filter field: {field_name}")
    payload = _get_json(
        f"{OPENF1_BASE_URL}/{endpoint}", endpoint=endpoint, provider="openf1",
        query=query, use_cache=use_cache,
    )
    if not isinstance(payload, list) or not all(isinstance(item, dict) for item in payload):
        raise ProviderError("The data provider returned an invalid record list.", kind="malformed", endpoint=endpoint)
    return payload


def _jolpica_json(path: str, *, endpoint: str, query: dict[str, Any] | None = None):
    url = f"{JOLPICA_BASE_URL}/{path.lstrip('/')}"
    return _get_json(url, endpoint=endpoint, provider="jolpica", query=query or {})


def _meeting_label(meeting: dict[str, Any]) -> str:
    return str(meeting.get("meeting_name") or meeting.get("circuit_short_name") or meeting.get("location") or "Grand Prix")


def get_session_refs(year: int) -> list[SessionRef]:
    """List completed 2023+ sessions and stable meeting/session identities."""
    year = int(year)
    if year < 2023:
        return []
    meetings = _openf1_records("meetings", {"year": year})
    sessions = _openf1_records("sessions", {"year": year})
    meetings_by_key = {_as_int(row.get("meeting_key")): row for row in meetings if _as_int(row.get("meeting_key")) is not None}
    completed_cutoff = _utc_now() - timedelta(minutes=30)
    event_keys = sorted(
        meetings_by_key,
        key=lambda key: str(meetings_by_key[key].get("date_start") or ""),
    )
    rounds = {meeting_key: index + 1 for index, meeting_key in enumerate(event_keys)}
    refs = []
    for row in sessions:
        meeting_key = _as_int(row.get("meeting_key"))
        session_key = _as_int(row.get("session_key"))
        meeting = meetings_by_key.get(meeting_key)
        if not meeting or session_key is None:
            continue
        date_end = _timestamp(row.get("date_end"))
        if pd.isna(date_end) or date_end.to_pydatetime() > completed_cutoff:
            continue
        cancelled = _as_bool(row.get("is_cancelled"))
        if cancelled is None:
            cancelled = _as_bool(meeting.get("is_cancelled"))
        if cancelled is True:
            continue
        refs.append(SessionRef(
            year=year,
            round=rounds.get(meeting_key, 0),
            event_name=_meeting_label(meeting),
            country_name=str(meeting.get("country_name") or ""),
            session_name=str(row.get("session_name") or row.get("session_type") or "Session"),
            session_type=str(row.get("session_type") or row.get("session_name") or "Session"),
            session_key=session_key,
            meeting_key=meeting_key,
            date_start=str(row.get("date_start") or "") or None,
            date_end=str(row.get("date_end") or "") or None,
            circuit_key=_as_int(meeting.get("circuit_key")),
            circuit_short_name=str(meeting.get("circuit_short_name") or ""),
            circuit_info_url=str(meeting.get("circuit_info_url") or "") or None,
            is_cancelled=False,
        ))
    return sorted(refs, key=lambda ref: (ref.round, ref.date_start or "", ref.session_name))


def get_schedule(year: int) -> list[dict[str, Any]]:
    refs = get_session_refs(year)
    grouped: dict[tuple[int, str], dict[str, Any]] = {}
    for ref in refs:
        key = (ref.meeting_key, ref.event_name)
        event = grouped.setdefault(key, {
            "year": ref.year, "round": ref.round, "race": ref.event_name,
            "country_name": ref.country_name, "meeting_key": ref.meeting_key,
            "sessions": [],
        })
        if ref.session_name not in event["sessions"]:
            event["sessions"].append(ref.session_name)
    return list(grouped.values())


def get_supported_years() -> list[int]:
    return list(range(2023, _utc_now().year + 1))


def resolve_session_ref(year: int, event_name: str, session_name: str) -> SessionRef:
    refs = get_session_refs(int(year))
    event_candidates = [ref for ref in refs if ref.event_name.casefold() == str(event_name).casefold()]
    match = next((ref for ref in event_candidates if ref.session_name.casefold() == str(session_name).casefold()), None)
    if match:
        return match
    raise ProviderError("This completed session is not in the supported OpenF1 archive.", kind="not_found", endpoint="sessions")


def latest_completed_race(now: datetime | None = None) -> dict[str, Any] | None:
    now = now or _utc_now()
    latest = None
    for year in reversed(get_supported_years()):
        for ref in get_session_refs(year):
            if ref.session_type.casefold() != "race":
                continue
            date_end = _timestamp(ref.date_end)
            if not pd.isna(date_end) and date_end.to_pydatetime() <= now - timedelta(minutes=30):
                if latest is None or (ref.date_end or "") > (latest.date_end or ""):
                    latest = ref
        if latest:
            break
    return {
        "year": latest.year, "race": latest.event_name,
        "session_type": latest.session_name, "round": latest.round,
        "session_key": latest.session_key,
    } if latest else None


def _empty_frame(columns: tuple[str, ...] | list[str]) -> pd.DataFrame:
    return pd.DataFrame(columns=list(columns))


def normalize_drivers(records: list[dict[str, Any]]) -> pd.DataFrame:
    rows = []
    seen = set()
    for record in records:
        number = _driver_number(record.get("driver_number"))
        abbreviation = str(record.get("name_acronym") or "").strip().upper()
        if not number or not abbreviation or number in seen:
            continue
        seen.add(number)
        full_name = str(record.get("full_name") or record.get("broadcast_name") or abbreviation).strip()
        rows.append({
            "driver_number": number, "abbreviation": abbreviation,
            "full_name": full_name, "team_name": str(record.get("team_name") or ""),
            "team_colour": record.get("team_colour"),
        })
    return pd.DataFrame(rows, columns=["driver_number", "abbreviation", "full_name", "team_name", "team_colour"])


def normalize_laps(records: list[dict[str, Any]], drivers: pd.DataFrame, stints: pd.DataFrame | None = None, pits: pd.DataFrame | None = None) -> pd.DataFrame:
    driver_codes = dict(zip(drivers.get("driver_number", []), drivers.get("abbreviation", []))) if not drivers.empty else {}
    stint_by_driver = {}
    if stints is not None and not stints.empty:
        for number, group in stints.groupby("driver_number", dropna=False):
            stint_by_driver[str(number)] = group.to_dict("records")
    pit_pairs = set()
    if pits is not None and not pits.empty:
        pit_pairs = {(str(row.driver_number), int(row.lap_number)) for row in pits.itertuples() if pd.notna(row.lap_number)}
    rows = []
    for record in records:
        driver_number = _driver_number(record.get("driver_number"))
        lap_number = _as_int(record.get("lap_number"))
        duration = _number(record.get("lap_duration"))
        if not driver_number or lap_number is None:
            continue
        date_start = _timestamp(record.get("date_start"))
        compound = None
        stint_number = None
        tyre_age = None
        for stint in stint_by_driver.get(driver_number, []):
            start_lap, end_lap = _as_int(stint.get("lap_start")), _as_int(stint.get("lap_end"))
            if start_lap is not None and lap_number >= start_lap and (end_lap is None or lap_number <= end_lap):
                compound = stint.get("compound")
                stint_number = _as_int(stint.get("stint_number"))
                tyre_age = _as_int(stint.get("tyre_age_at_start"))
                if tyre_age is not None:
                    tyre_age += max(0, lap_number - start_lap)
                break
        rows.append({
            "driver_number": driver_number, "abbreviation": driver_codes.get(driver_number, ""),
            "lap_number": lap_number, "date_start": date_start,
            "lap_duration": duration,
            "duration_sector_1": _number(record.get("duration_sector_1")),
            "duration_sector_2": _number(record.get("duration_sector_2")),
            "duration_sector_3": _number(record.get("duration_sector_3")),
            "i1_speed": _number(record.get("i1_speed")), "i2_speed": _number(record.get("i2_speed")),
            "st_speed": _number(record.get("st_speed")),
            "is_pit_out_lap": _as_bool(record.get("is_pit_out_lap")),
            "compound": str(compound).upper() if compound else None,
            "stint_number": stint_number, "tyre_age": tyre_age,
            "pit_in": (driver_number, lap_number) in pit_pairs,
            "pit_out": _as_bool(record.get("is_pit_out_lap")) or False,
            "position": None, "gap_to_leader": None, "interval": None,
            "track_status": None, "track_status_source": None,
            "segments_sector_1": record.get("segments_sector_1"),
            "segments_sector_2": record.get("segments_sector_2"),
            "segments_sector_3": record.get("segments_sector_3"),
        })
    frame = pd.DataFrame(rows)
    if frame.empty:
        return _empty_frame([
            "driver_number", "abbreviation", "lap_number", "date_start", "lap_duration",
            "duration_sector_1", "duration_sector_2", "duration_sector_3", "i1_speed", "i2_speed",
            "st_speed", "is_pit_out_lap", "compound", "stint_number", "tyre_age", "pit_in", "pit_out",
            "position", "gap_to_leader", "interval", "track_status", "track_status_source",
            "segments_sector_1", "segments_sector_2", "segments_sector_3",
        ])
    return frame.sort_values(["driver_number", "lap_number"], kind="stable").reset_index(drop=True)


def normalize_stints(records: list[dict[str, Any]], drivers: pd.DataFrame) -> pd.DataFrame:
    codes = dict(zip(drivers.get("driver_number", []), drivers.get("abbreviation", []))) if not drivers.empty else {}
    rows = []
    for record in records:
        number = _driver_number(record.get("driver_number"))
        if not number:
            continue
        rows.append({
            "driver_number": number, "abbreviation": codes.get(number, ""),
            "stint_number": _as_int(record.get("stint_number")),
            "lap_start": _as_int(record.get("lap_start")), "lap_end": _as_int(record.get("lap_end")),
            "compound": str(record.get("compound") or "UNKNOWN").upper(),
            "tyre_age_at_start": _as_int(record.get("tyre_age_at_start")), "source": "openf1.stints",
        })
    frame = pd.DataFrame(rows, columns=["driver_number", "abbreviation", "stint_number", "lap_start", "lap_end", "compound", "tyre_age_at_start", "source"])
    return frame.sort_values(["driver_number", "stint_number"], kind="stable").reset_index(drop=True) if not frame.empty else frame


def normalize_pits(records: list[dict[str, Any]], drivers: pd.DataFrame) -> pd.DataFrame:
    codes = dict(zip(drivers.get("driver_number", []), drivers.get("abbreviation", []))) if not drivers.empty else {}
    rows = []
    for record in records:
        number = _driver_number(record.get("driver_number"))
        lap = _as_int(record.get("lap_number"))
        if not number or lap is None:
            continue
        rows.append({
            "driver_number": number, "abbreviation": codes.get(number, ""), "lap_number": lap,
            "date": _timestamp(record.get("date")),
            "stop_duration": _number(record.get("stop_duration") if record.get("stop_duration") is not None else record.get("duration")),
            "lane_duration": _number(record.get("lane_duration")),
            "stop_time": record.get("time"),
            "duration_semantics": record.get("duration_semantics") or (
                "stationary_service" if record.get("stop_duration") is not None or record.get("duration") is not None
                else "pit_lane_total" if record.get("lane_duration") is not None else "unavailable"
            ),
            "source": record.get("source", "openf1.pit"),
        })
    return pd.DataFrame(rows, columns=["driver_number", "abbreviation", "lap_number", "date", "stop_duration", "lane_duration", "stop_time", "duration_semantics", "source"])


def normalize_results(records: list[dict[str, Any]], drivers: pd.DataFrame, session_type: str) -> pd.DataFrame:
    codes = dict(zip(drivers.get("driver_number", []), drivers.get("abbreviation", []))) if not drivers.empty else {}
    names = dict(zip(drivers.get("driver_number", []), drivers.get("full_name", []))) if not drivers.empty else {}
    teams = dict(zip(drivers.get("driver_number", []), drivers.get("team_name", []))) if not drivers.empty else {}
    rows = []
    is_qualy = "qualifying" in session_type.casefold() or "shootout" in session_type.casefold()
    is_sprint_qualy = "sprint" in session_type.casefold() or "shootout" in session_type.casefold()
    phases = ("sq1", "sq2", "sq3") if is_sprint_qualy else ("q1", "q2", "q3")
    for record in records:
        number = _driver_number(record.get("driver_number"))
        if not number:
            continue
        duration = record.get("duration")
        gap = record.get("gap_to_leader")
        if gap is None:
            gap = record.get("gap")
        durations = duration if isinstance(duration, list) else [duration]
        gaps = gap if isinstance(gap, list) else [gap]
        phase_values = {
            f"duration_{phase}": _number(durations[index]) if index < len(durations) and _number(durations[index]) is not None else _number(record.get(f"duration_{phase}"))
            for index, phase in enumerate(phases)
        }
        gap_values = {
            f"gap_{phase}": gaps[index] if index < len(gaps) and gaps[index] is not None else record.get(f"gap_{phase}")
            for index, phase in enumerate(phases)
        }
        status = (
            "DSQ" if _as_bool(record.get("dsq")) else "DNS" if _as_bool(record.get("dns")) else
            "DNF" if _as_bool(record.get("dnf")) else str(record.get("status")) if record.get("status") else
            "Finished" if record.get("position") is not None else "Unclassified"
        )
        rows.append({
            "driver_number": number, "abbreviation": codes.get(number, ""),
            "full_name": names.get(number, ""), "team_name": teams.get(number, ""),
            "position": _as_int(record.get("position")),
            "status": status, "points": _number(record.get("points")),
            "classified_laps": _as_int(record.get("number_of_laps") if record.get("number_of_laps") is not None else record.get("classified_laps")),
            "grid_position": _as_int(record.get("grid_position") or record.get("grid")),
            "race_time": None if isinstance(duration, list) else _number(duration) if _number(duration) is not None else _number(record.get("race_time")),
            "gap": gap if not isinstance(gap, list) else None,
            # `duration` is a race/session result duration outside qualifying;
            # it is not the driver's fastest lap.
            "best_lap_time": next((value for value in reversed(durations) if _number(value) is not None), None) if is_qualy else _number(record.get("best_lap_time")),
            "source": record.get("source", "openf1.session_result"), **phase_values, **gap_values,
        })
        if rows[-1]["best_lap_time"] is None:
            rows[-1]["best_lap_time"] = _number(record.get("best_lap_time"))
    frame = pd.DataFrame(rows)
    if frame.empty:
        return _empty_frame(["driver_number", "abbreviation", "full_name", "team_name", "position", "grid_position", "status", "points", "classified_laps", "race_time", "gap", "best_lap_time", "source"])
    return frame.sort_values(["position", "driver_number"], na_position="last", kind="stable").reset_index(drop=True)


def normalize_grid(records: list[dict[str, Any]], drivers: pd.DataFrame) -> pd.DataFrame:
    codes = dict(zip(drivers.get("driver_number", []), drivers.get("abbreviation", []))) if not drivers.empty else {}
    rows = []
    for record in records:
        number = _driver_number(record.get("driver_number"))
        if not number:
            continue
        grid_position = record.get("grid_position") if record.get("grid_position") is not None else record.get("position")
        rows.append({"driver_number": number, "abbreviation": codes.get(number, ""), "grid_position": _as_int(grid_position), "qualifying_lap_duration": _number(record.get("lap_duration") if record.get("lap_duration") is not None else record.get("qualifying_lap_duration")), "source": record.get("source", "openf1.starting_grid")})
    frame = pd.DataFrame(rows, columns=["driver_number", "abbreviation", "grid_position", "qualifying_lap_duration", "source"])
    return frame.sort_values("grid_position", na_position="last", kind="stable").reset_index(drop=True) if not frame.empty else frame


def _normalize_weather(records: list[dict[str, Any]]) -> pd.DataFrame:
    frame = pd.DataFrame(records)
    mapping = {"date": "timestamp", "track_temperature": "track_temperature", "air_temperature": "air_temperature", "humidity": "humidity", "pressure": "pressure", "wind_speed": "wind_speed", "wind_direction": "wind_direction", "rainfall": "rainfall"}
    if frame.empty:
        return _empty_frame(list(mapping.values()))
    frame = frame.rename(columns=mapping)
    frame["timestamp"] = pd.to_datetime(frame.get("timestamp"), format="mixed", utc=True, errors="coerce")
    for column in mapping.values():
        if column in ("timestamp",):
            continue
        if column in frame:
            if column == "rainfall":
                frame[column] = frame[column].map(lambda value: None if value is None or pd.isna(value) else bool(value) if isinstance(value, (bool, np.bool_)) else (_number(value) > 0 if _number(value) is not None else None))
            else:
                frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame[[column for column in mapping.values() if column in frame]].sort_values("timestamp", na_position="last").reset_index(drop=True)


def _normalize_messages(records: list[dict[str, Any]]) -> pd.DataFrame:
    columns = ["timestamp", "category", "flag", "scope", "sector", "lap_number", "message", "source"]
    rows = []
    for record in records:
        rows.append({
            "timestamp": _timestamp(record.get("date")), "category": record.get("category"),
            "flag": record.get("flag"), "scope": record.get("scope"),
            "sector": _as_int(record.get("sector")), "lap_number": _as_int(record.get("lap_number")),
            "message": record.get("message"), "source": "openf1.race_control",
        })
    frame = pd.DataFrame(rows, columns=columns)
    return frame.sort_values("timestamp", na_position="last").reset_index(drop=True) if not frame.empty else frame


def _classify_race_control_event(event: dict[str, Any]) -> tuple[str | None, str | None]:
    """Classify explicit status changes without matching incidental mentions."""
    message = str(event.get("message") or "").strip().casefold()
    flag = str(event.get("flag") or "").strip().casefold()
    category = re.sub(r"[^a-z]", "", str(event.get("category") or "").casefold())

    vsc = r"(?:vsc|virtual safety car)"
    if category == "safetycar":
        if re.search(rf"^{vsc}\s+(?:deployed|deploy|out)\b", message):
            return "vsc", "start"
        if re.search(rf"^{vsc}\s+(?:ending|in this lap|ended|withdrawn)\b", message):
            return "vsc", "end"
        if re.search(r"^safety car\s+(?:deployed|deploy|out)\b", message):
            return "safety", "start"
        if re.search(r"^safety car\s+(?:ending|in this lap|ended|withdrawn)\b", message):
            return "safety", "end"

    if category == "flag":
        if flag in {"red", "red flag"} or re.match(r"^red flag(?:\b|$)", message):
            return "red", "start"
        if flag in {"green", "green flag"} or re.match(r"^(?:green flag|session resumed|session restarted)\b", message):
            return "red", "end"
        if flag in {"yellow", "double yellow"} or re.match(r"^(?:yellow|double yellow)\b", message):
            return "yellow", "point"
    return None, None


def _normalize_timed_position(records: list[dict[str, Any]], kind: str) -> pd.DataFrame:
    rows = []
    for record in records:
        number = _driver_number(record.get("driver_number"))
        if not number:
            continue
        rows.append({
            "driver_number": number,
            "timestamp": _timestamp(record.get("date")),
            "position": _as_int(record.get("position")),
            "gap_to_leader": record.get("gap_to_leader"),
            "interval": record.get("interval"),
            "source": f"openf1.{kind}",
        })
    frame = pd.DataFrame(rows, columns=["driver_number", "timestamp", "position", "gap_to_leader", "interval", "source"])
    return frame.sort_values(["timestamp", "driver_number"], na_position="last", kind="stable").reset_index(drop=True) if not frame.empty else frame


def _qualifying_grid_ref(ref: SessionRef) -> SessionRef | None:
    candidates = [candidate for candidate in get_session_refs(ref.year) if candidate.meeting_key == ref.meeting_key]
    name = ref.session_name.casefold()
    if "sprint" in name:
        preferred = [c for c in candidates if "sprint" in c.session_name.casefold() and ("qualifying" in c.session_name.casefold() or "shootout" in c.session_name.casefold())]
    else:
        preferred = [c for c in candidates if "qualifying" in c.session_name.casefold() and "sprint" not in c.session_name.casefold()]
    if "qualifying" in name and "sprint" not in name:
        return ref
    return preferred[-1] if preferred else None


def _attach_lap_context(laps: pd.DataFrame, positions: pd.DataFrame, intervals: pd.DataFrame, messages: pd.DataFrame) -> pd.DataFrame:
    if laps.empty:
        return laps
    result = laps.copy(deep=True)
    result["lap_end"] = result["date_start"] + pd.to_timedelta(result["lap_duration"], unit="s", errors="coerce")
    for samples, columns in ((positions, ("position",)), (intervals, ("gap_to_leader", "interval"))):
        if samples is None or samples.empty or "timestamp" not in samples:
            continue
        for driver_number, lap_indexes in result.groupby("driver_number").groups.items():
            driver_samples = samples[samples["driver_number"].astype(str) == str(driver_number)].dropna(subset=["timestamp"]).sort_values("timestamp")
            if driver_samples.empty:
                continue
            sample_times = pd.to_datetime(driver_samples["timestamp"], utc=True, errors="coerce").astype("int64").to_numpy()
            targets = pd.to_datetime(result.loc[lap_indexes, "lap_end"], utc=True, errors="coerce").astype("int64").to_numpy()
            sample_rows = driver_samples.to_dict("records")
            for lap_index, target in zip(lap_indexes, targets):
                sample_index = int(np.searchsorted(sample_times, target, side="right") - 1)
                if sample_index < 0:
                    continue
                sample = sample_rows[sample_index]
                for column in columns:
                    if column not in sample:
                        continue
                    value = sample[column]
                    if column in {"position"}:
                        result.at[lap_index, column] = _as_int(value)
                    elif column in {"gap_to_leader", "interval"}:
                        numeric = _number(value)
                        result.at[lap_index, column] = numeric if numeric is not None else str(value) if value is not None and not pd.isna(value) else None
    if messages is not None and not messages.empty:
        explicit = messages.dropna(subset=["lap_number"]).copy()
        for event in explicit.to_dict("records"):
            lap_number = _as_int(event.get("lap_number"))
            if lap_number is None:
                continue
            status, action = _classify_race_control_event(event)
            if status and action in {"start", "point"}:
                status = {"safety": "safety_car", "red": "red_flag"}.get(status, status)
                result.loc[result["lap_number"] == lap_number, "track_status"] = status
                result.loc[result["lap_number"] == lap_number, "track_status_source"] = "race_control_explicit_lap"
    return result.drop(columns=["lap_end"], errors="ignore")


def _jolpica_results(ref: SessionRef, session_type: str, drivers: pd.DataFrame) -> pd.DataFrame:
    session_name = str(session_type).casefold()
    if "qualifying" in session_name or "shootout" in session_name:
        endpoint = "qualifying"
    elif session_name in {"race", "sprint", "sprint race"}:
        endpoint = "sprint" if "sprint" in session_name else "results"
    else:
        # Jolpica does not publish practice classification. Never reuse the
        # Grand Prix result table for a practice session.
        return pd.DataFrame()
    payload = _jolpica_json(f"{ref.year}/{ref.round}/{endpoint}.json", endpoint=f"jolpica_{endpoint}", query={"limit": "100"})
    table_key = {"qualifying": "QualifyingTable", "sprint": "SprintTable", "results": "RaceTable"}[endpoint]
    table = payload.get("MRData", {}).get(table_key, {})
    raw_rows = table.get("Races", [])
    if raw_rows:
        raw_rows = raw_rows[0].get("QualifyingResults" if endpoint == "qualifying" else "SprintResults" if endpoint == "sprint" else "Results", [])
    codes = {str(row.get("abbreviation", "")).upper(): row for row in drivers.to_dict("records")} if not drivers.empty else {}
    rows = []
    for item in raw_rows:
        driver = item.get("Driver", {})
        code = str(driver.get("code") or "").upper()
        match = codes.get(code)
        if endpoint == "qualifying":
            phase_times = [item.get(f"Q{i}") for i in range(1, 4)]
            duration = [_time_seconds(value) for value in phase_times]
        else:
            duration = None
        best_time = next((value for value in reversed(duration or []) if value is not None), None)
        time_data = item.get("Time") if isinstance(item.get("Time"), dict) else {}
        gap_value = time_data.get("time")
        if isinstance(gap_value, str) and gap_value.startswith("+"):
            parsed_gap = _time_seconds(gap_value[1:])
            if parsed_gap is not None:
                gap_value = parsed_gap
        millis = _number(time_data.get("millis"))
        rows.append({
            "driver_number": match.get("driver_number") if match else str(driver.get("permanentNumber") or ""),
            "abbreviation": code, "full_name": " ".join(filter(None, [driver.get("givenName"), driver.get("familyName")])),
            "team_name": (item.get("Constructor") or {}).get("name", ""),
            "position": _as_int(item.get("position")), "grid_position": _as_int(item.get("grid")),
            "status": item.get("status", ""), "points": _number(item.get("points")),
            "classified_laps": _as_int(item.get("laps")), "race_time": millis / 1000 if millis is not None else None,
            "gap": gap_value if gap_value is not None else item.get("status"),
            "best_lap_time": best_time, "source": f"jolpica.{endpoint}",
            "duration_q1": duration[0] if isinstance(duration, list) and len(duration) > 0 else None,
            "duration_q2": duration[1] if isinstance(duration, list) and len(duration) > 1 else None,
            "duration_q3": duration[2] if isinstance(duration, list) and len(duration) > 2 else None,
        })
    return pd.DataFrame(rows)


def _jolpica_pits(ref: SessionRef, drivers: pd.DataFrame) -> pd.DataFrame:
    """Map Jolpica pitstop IDs back to session drivers for an empty OpenF1 feed."""
    pit_payload = _jolpica_json(
        f"{ref.year}/{ref.round}/pitstops.json",
        endpoint="jolpica_pitstops", query={"limit": "1000"},
    )
    driver_payload = _jolpica_json(
        f"{ref.year}/drivers.json",
        endpoint="jolpica_drivers", query={"limit": "100"},
    )
    races = pit_payload.get("MRData", {}).get("RaceTable", {}).get("Races", [])
    raw_stops = races[0].get("PitStops", []) if races else []
    driver_rows = driver_payload.get("MRData", {}).get("DriverTable", {}).get("Drivers", [])
    code_by_id = {
        str(row.get("driverId")): str(row.get("code") or "").upper()
        for row in driver_rows if row.get("driverId") and row.get("code")
    }
    number_by_code = dict(zip(drivers.get("abbreviation", []), drivers.get("driver_number", []))) if not drivers.empty else {}
    rows = []
    for stop in raw_stops:
        code = code_by_id.get(str(stop.get("driverId")), "")
        number = number_by_code.get(code)
        lap = _as_int(stop.get("lap"))
        duration = _number(stop.get("duration"))
        if number is None or lap is None:
            continue
        rows.append({
            "driver_number": str(number), "lap_number": lap, "date": None,
            "stop_duration": duration, "lane_duration": None,
            "duration_semantics": "stationary_service", "time": stop.get("time"),
            "source": "jolpica.pitstops",
        })
    return pd.DataFrame(rows)


def _request_endpoint(ref: SessionRef, name: str, query: dict[str, Any] | None = None, *, use_cache=True) -> list[dict[str, Any]]:
    return _openf1_records(name, {"session_key": ref.session_key, **(query or {})}, use_cache=use_cache)


def load_session_bundle(ref: SessionRef, *, laps=True, results=True, strategy=False, race_context=False, circuit=False) -> SessionBundle:
    """Load requested endpoint profiles; endpoint failures remain isolated."""
    quality: dict[str, Any] = {"schema_version": SCHEMA_VERSION, "provider": "OpenF1", "endpoints": {}, "notes": []}
    driver_rows = _request_endpoint(ref, "drivers")
    drivers = normalize_drivers(driver_rows)
    quality["endpoints"]["drivers"] = {"state": "available" if len(drivers) else "empty", "rows": len(drivers), "source": "openf1.drivers"}
    if drivers.empty:
        raise ProviderError("No driver metadata was published for this session.", kind="empty", endpoint="drivers")

    result_rows: list[dict[str, Any]] = []
    grid_rows: list[dict[str, Any]] = []
    jolpica_result_frame: pd.DataFrame | None = None

    def get_jolpica_results():
        nonlocal jolpica_result_frame
        if jolpica_result_frame is not None:
            return jolpica_result_frame
        try:
            jolpica_result_frame = _jolpica_results(ref, ref.session_name, drivers)
        except ProviderError as exc:
            state = "not_found" if exc.kind == "not_found" else "unavailable"
            quality["endpoints"]["jolpica_results"] = {"state": state, "reason": exc.kind}
            jolpica_result_frame = pd.DataFrame()
        else:
            quality["endpoints"]["jolpica_results"] = {
                "state": "available" if not jolpica_result_frame.empty else "empty",
                "rows": len(jolpica_result_frame), "source": "jolpica",
            }
        return jolpica_result_frame

    if results or race_context:
        try:
            result_rows = _request_endpoint(ref, "session_result")
            quality["endpoints"]["session_result"] = {"state": "available" if result_rows else "pending", "rows": len(result_rows), "source": "openf1.session_result"}
        except ProviderError as exc:
            quality["endpoints"]["session_result"] = {"state": "unavailable", "reason": exc.kind}
        if not result_rows:
            fallback = get_jolpica_results()
            if not fallback.empty:
                result_rows = fallback.to_dict("records")
                quality["endpoints"]["session_result"] = {"state": "available", "rows": len(result_rows), "source": str(fallback.iloc[0].get("source", "jolpica"))}
                quality["notes"].append("Official result is supplemented by Jolpica-F1.")
        elif len(result_rows) < len(drivers):
            fallback = get_jolpica_results()
            if not fallback.empty:
                present = {str(row.get("driver_number")) for row in result_rows}
                missing = fallback[fallback["driver_number"].astype(str).map(lambda number: number not in present)]
                if not missing.empty:
                    result_rows.extend(missing.to_dict("records"))
                    quality["notes"].append("Missing classification rows are supplemented by Jolpica-F1 and source-labeled.")
        try:
            grid_ref = _qualifying_grid_ref(ref) if race_context or ref.session_type.casefold() in {"race", "sprint"} else None
        except ProviderError:
            # Grid context is optional; a schedule failure must not prevent
            # the session results, laps, or other independent views loading.
            grid_ref = None
        if grid_ref:
            try:
                grid_rows = _openf1_records("starting_grid", {"session_key": grid_ref.session_key})
                quality["endpoints"]["starting_grid"] = {"state": "available" if grid_rows else "pending", "rows": len(grid_rows), "source": "openf1.starting_grid", "queried_session_key": grid_ref.session_key}
            except ProviderError as exc:
                grid_rows = []
                quality["endpoints"]["starting_grid"] = {"state": "unavailable", "reason": exc.kind}
            if ref.session_type.casefold() in {"race", "sprint", "sprint race"}:
                fallback_grid = get_jolpica_results()
                if not fallback_grid.empty and "grid_position" in fallback_grid:
                    fallback_grid = fallback_grid.dropna(subset=["grid_position"])
                    present = {str(row.get("driver_number")) for row in grid_rows}
                    missing = fallback_grid[fallback_grid["driver_number"].astype(str).map(lambda number: number not in present)]
                    if not missing.empty:
                        grid_rows.extend(missing.to_dict("records"))
                        quality["endpoints"]["starting_grid"] = {
                            "state": "available", "rows": len(grid_rows),
                            "source": "openf1.starting_grid+jolpica.grid",
                            "queried_session_key": grid_ref.session_key,
                        }

    result_frame = normalize_results(result_rows, drivers, ref.session_type)
    grid_frame = normalize_grid(grid_rows, drivers)
    if not grid_frame.empty and not result_frame.empty:
        grid_map = dict(zip(grid_frame["driver_number"], grid_frame["grid_position"]))
        result_frame["grid_position"] = result_frame["driver_number"].map(grid_map)

    stints = pd.DataFrame()
    pits = pd.DataFrame()
    if strategy:
        for endpoint in ("stints", "pit"):
            try:
                rows = _request_endpoint(ref, endpoint)
                quality["endpoints"][endpoint] = {"state": "available" if rows else "empty", "rows": len(rows), "source": f"openf1.{endpoint}"}
            except ProviderError as exc:
                rows = []
                quality["endpoints"][endpoint] = {"state": "unavailable", "reason": exc.kind}
            if endpoint == "stints":
                stints = normalize_stints(rows, drivers)
            else:
                pits = normalize_pits(rows, drivers)
        if pits.empty:
            try:
                fallback_pits = _jolpica_pits(ref, drivers)
            except ProviderError as exc:
                state = "not_found" if exc.kind == "not_found" else "unavailable"
                quality["endpoints"]["jolpica_pitstops"] = {"state": state, "reason": exc.kind}
                fallback_pits = pd.DataFrame()
            else:
                quality["endpoints"]["jolpica_pitstops"] = {
                    "state": "available" if not fallback_pits.empty else "empty",
                    "rows": len(fallback_pits), "source": "jolpica.pitstops",
                }
            if not fallback_pits.empty:
                pits = normalize_pits(fallback_pits.to_dict("records"), drivers)
                quality["endpoints"]["pit"] = {
                    "state": "available", "rows": len(pits), "source": "jolpica.pitstops",
                }
                quality["notes"].append("Pit-stop records are supplemented by Jolpica-F1; timestamps and lane duration are unavailable.")
        if not pits.empty and pits["stop_duration"].isna().all():
            if pits["lane_duration"].notna().any():
                quality["notes"].append("Only pit-lane total times are published for this session; stationary service duration is unavailable.")
            else:
                quality["notes"].append("Pit events are listed, but no pit-duration measurement is available for this session.")

    lap_frame = pd.DataFrame()
    if laps:
        try:
            lap_rows = _request_endpoint(ref, "laps")
            quality["endpoints"]["laps"] = {"state": "available" if lap_rows else "empty", "rows": len(lap_rows), "source": "openf1.laps"}
        except ProviderError as exc:
            lap_rows = []
            quality["endpoints"]["laps"] = {"state": "unavailable", "reason": exc.kind}
        if lap_rows:
            if stints.empty and strategy:
                try:
                    stints = normalize_stints(_request_endpoint(ref, "stints"), drivers)
                except ProviderError:
                    pass
            if pits.empty and strategy:
                try:
                    pits = normalize_pits(_request_endpoint(ref, "pit"), drivers)
                except ProviderError:
                    pass
            lap_frame = normalize_laps(lap_rows, drivers, stints, pits)
    if laps and lap_frame.empty:
        quality["notes"].append("Lap timing is unavailable; driver and session context can still be shown.")

    weather = messages = positions = intervals = pd.DataFrame()
    if strategy or race_context:
        optional = ["weather"] if strategy else []
        if race_context:
            optional.extend(["race_control", "position", "intervals"])
        for endpoint in optional:
            try:
                rows = _request_endpoint(ref, endpoint)
                quality["endpoints"][endpoint] = {"state": "available" if rows else "empty", "rows": len(rows), "source": f"openf1.{endpoint}"}
            except ProviderError as exc:
                rows = []
                quality["endpoints"][endpoint] = {"state": "unavailable", "reason": exc.kind}
            if endpoint == "weather":
                weather = _normalize_weather(rows)
            elif endpoint == "race_control":
                messages = _normalize_messages(rows)
            elif endpoint in {"position", "intervals"}:
                frame = _normalize_timed_position(rows, endpoint)
                if endpoint == "position":
                    positions = frame
                else:
                    intervals = frame

    corners = pd.DataFrame()
    if circuit and ref.circuit_info_url:
        try:
            corners = get_circuit_corners(ref)
        except ProviderError as exc:
            # Circuit corners are supplemental. An unavailable circuit source
            # must not block the session's lap data or active analysis view.
            corners = pd.DataFrame(columns=["number", "letter", "x", "y", "source"])
            quality["endpoints"]["circuit_info"] = {"state": "unavailable", "reason": exc.kind, "source": "multiviewer"}
        else:
            quality["endpoints"]["circuit_info"] = {"state": "available" if not corners.empty else "unavailable", "rows": len(corners), "source": "multiviewer"}
        if not corners.empty:
            quality["notes"].append("Linked circuit corners are optional; coordinates are not overlaid unless their frame is validated against OpenF1 location samples.")

    quality["row_counts"] = {
        "drivers": len(drivers), "results": len(result_frame), "grid": len(grid_frame),
        "laps": len(lap_frame), "stints": len(stints), "pits": len(pits),
        "weather": len(weather), "race_control": len(messages), "positions": len(positions), "intervals": len(intervals),
    }
    lap_frame = _attach_lap_context(lap_frame, positions, intervals, messages)
    return SessionBundle(ref, drivers, result_frame, grid_frame, lap_frame, stints, pits, weather, messages, positions, intervals, corners, quality)


def get_circuit_corners(ref: SessionRef) -> pd.DataFrame:
    if not ref.circuit_info_url:
        return pd.DataFrame(columns=["number", "letter", "x", "y", "source"])
    url = ref.circuit_info_url
    if not url.startswith(MULTIVIEWER_BASE_URL + "/"):
        return pd.DataFrame(columns=["number", "letter", "x", "y", "source"])
    payload = _get_json(url, endpoint="circuit_info", provider="multiviewer", query={})
    raw = payload.get("corners", []) if isinstance(payload, dict) else []
    rows = []
    for row in raw if isinstance(raw, list) else []:
        position = row.get("trackPosition") if isinstance(row, dict) else None
        if not isinstance(position, dict):
            continue
        x, y = _number(position.get("x")), _number(position.get("y"))
        number = _as_int(row.get("number"))
        if number and x is not None and y is not None:
            rows.append({"number": number, "letter": str(row.get("letter") or ""), "x": x, "y": y, "source": "multiviewer.circuit_info"})
    return pd.DataFrame(rows, columns=["number", "letter", "x", "y", "source"])


def _lap_start_and_end(lap: dict[str, Any] | pd.Series) -> tuple[pd.Timestamp, pd.Timestamp, float]:
    record = dict(lap)
    start = _timestamp(record.get("date_start"))
    duration = _number(record.get("lap_duration"))
    if pd.isna(start) or duration is None or duration <= 0:
        raise ProviderError("This lap has no valid published start time or duration.", kind="incomplete", endpoint="laps")
    return start, start + pd.to_timedelta(duration, unit="s"), duration


def get_selected_lap_trace(ref: SessionRef, lap: dict[str, Any] | pd.Series, *, with_position=True) -> pd.DataFrame:
    """Load bounded car/location windows for one selected lap and normalize."""
    record = dict(lap)
    start, end, duration = _lap_start_and_end(record)
    driver_number = _driver_number(record.get("driver_number"))
    if not driver_number:
        raise ProviderError("This lap is missing its session driver identity.", kind="incomplete", endpoint="laps")
    start_wire = (start - pd.to_timedelta(0.5, unit="s")).isoformat()
    end_wire = (end + pd.to_timedelta(0.5, unit="s")).isoformat()
    window = {"session_key": ref.session_key, "driver_number": driver_number, "date>": start_wire, "date<": end_wire}
    car_records = _openf1_records("car_data", window)
    if len(car_records) > 2500:
        raise ProviderError("The selected-lap telemetry response was larger than expected.", kind="oversize", endpoint="car_data")
    car = pd.DataFrame(car_records)
    if car.empty:
        raise ProviderError("No speed samples are available for this selected lap.", kind="empty", endpoint="car_data")
    car["timestamp"] = pd.to_datetime(car.get("date"), format="mixed", utc=True, errors="coerce")
    car = car.dropna(subset=["timestamp"]).sort_values("timestamp", kind="stable")
    car = car[(car["timestamp"] >= start) & (car["timestamp"] <= end)].copy()
    car["Time"] = car["timestamp"] - start
    car["Speed"] = pd.to_numeric(car.get("speed"), errors="coerce")
    car["Throttle"] = pd.to_numeric(car.get("throttle"), errors="coerce")
    brake = pd.to_numeric(car.get("brake"), errors="coerce")
    car["Brake"] = brake / 100.0
    car["nGear"] = pd.to_numeric(car.get("n_gear"), errors="coerce")
    car["RPM"] = pd.to_numeric(car.get("rpm"), errors="coerce")
    car["DRS"] = pd.to_numeric(car.get("drs"), errors="coerce")
    # OpenF1 speed is km/h. Integrate over each observed interval; the result
    # is a derived progress axis, never a claimed circuit-distance measurement.
    elapsed_s = car["Time"].dt.total_seconds().to_numpy(dtype=float)
    speed_ms = car["Speed"].to_numpy(dtype=float) / 3.6
    distance = np.zeros(len(car), dtype=float)
    if len(car) > 1:
        dt = np.diff(elapsed_s)
        dt = np.clip(dt, 0, 2.0)
        avg_speed = (speed_ms[1:] + speed_ms[:-1]) / 2
        distance[1:] = np.cumsum(np.nan_to_num(avg_speed, nan=0.0) * dt)
    car["Distance"] = distance

    location_count = 0
    if with_position:
        try:
            location_records = _openf1_records("location", window)
        except ProviderError:
            location_records = []
        location = pd.DataFrame(location_records)
        if not location.empty and {"date", "x", "y"}.issubset(location.columns):
            location["timestamp"] = pd.to_datetime(location["date"], format="mixed", utc=True, errors="coerce")
            location["X"] = pd.to_numeric(location["x"], errors="coerce")
            location["Y"] = pd.to_numeric(location["y"], errors="coerce")
            location = location.dropna(subset=["timestamp", "X", "Y"]).sort_values("timestamp", kind="stable")
            # Keep the merged sidecar within the selected lap, even though
            # the request itself has a small guard band around its boundaries.
            location = location[(location["timestamp"] >= start) & (location["timestamp"] <= end)].copy()
            location_count = len(location)
            car = pd.merge_asof(
                car.sort_values("timestamp"), location[["timestamp", "X", "Y"]],
                on="timestamp", direction="nearest", tolerance=pd.Timedelta(seconds=0.75),
            )
    for column in ("Throttle", "Brake", "nGear", "RPM", "DRS", "X", "Y"):
        if column not in car:
            car[column] = np.nan
    car = car.loc[:, ["Time", "Distance", "Speed", "Throttle", "Brake", "nGear", "RPM", "DRS", "X", "Y"]]
    car = car.dropna(subset=["Speed", "Time"]).reset_index(drop=True)
    car.attrs["quality"] = {
        "source": "openf1.car_data", "sample_count": len(car),
        "position_sample_count": location_count, "sampling_hz": 3.7,
        "has_position": len(car.dropna(subset=["X", "Y"])) >= 12,
        "distance_derived": True, "lap_duration_seconds": duration,
        "notes": ["Distance is integrated from sampled speed and is approximate.", "Samples are approximately 3.7 Hz."] + (["Location samples are missing or insufficient for position views."] if location_count < 12 else []),
    }
    if len(car) < 6:
        raise ProviderError("The selected lap has too few usable speed samples.", kind="incomplete", endpoint="car_data")
    return car


def clear_rate_window_for_tests():
    global _LAST_REQUEST_AT, _REQUEST_COUNT, _ERROR_COUNT, _RESPONSE_BYTES
    with _REQUEST_LOCK:
        _REQUEST_TIMES.clear()
        _LAST_REQUEST_AT = 0.0
        _REQUEST_COUNT = 0
        _ERROR_COUNT = 0
        _RESPONSE_BYTES = 0
        _ENDPOINT_METRICS.clear()
