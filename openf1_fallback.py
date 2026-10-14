"""Small telemetry fallback for serverless FastF1 loads.

FastF1 remains the application's source of truth for event metadata, results
and lap selection.  Its official F1 live-timing car-data stream can however
return an empty, non-error payload from some cloud networks.  OpenF1 provides
the same historical car channels and location samples from 2023 onward, so it
is a useful *last-resort* source for the selected lap only.

This module intentionally exposes no OpenF1 implementation details to the
dashboard.  A failure always raises ``OpenF1FallbackError`` so callers can
retain the normal FastF1 error path rather than displaying partial data as if
it were complete.
"""
from __future__ import annotations

import json
import os
from datetime import timedelta
from functools import lru_cache
from urllib.parse import quote_plus, urlencode

import pandas as pd
import requests


_BASE_URL = "https://api.openf1.org/v1"
_USER_AGENT = "f1-analyzer-telemetry-fallback/1"


class OpenF1FallbackError(RuntimeError):
    """Raised when OpenF1 cannot supply a complete selected-lap trace."""


def _enabled():
    """Allow deployments to explicitly disable the optional fallback."""
    return str(os.getenv("OPENF1_FALLBACK_ENABLED", "1")).lower() not in {
        "0", "false", "no", "off"
    }


def _timeout_seconds():
    try:
        value = float(os.getenv("OPENF1_FALLBACK_TIMEOUT_SECONDS", "8"))
    except (TypeError, ValueError):
        value = 8.0
    return max(1.0, min(20.0, value))


def _request_json(resource, params):
    query_parts = []
    for key, value in params.items():
        if value is None:
            continue
        # OpenF1's time filters use operator keys such as ``date>=``. Its
        # router accepts ``date%3E=value`` but not the fully encoded
        # ``date%3E%3D=value`` produced by urlencode, so keep the final '='
        # as the query separator while still escaping all values safely.
        if key.endswith(('>=', '<=', '>', '<')):
            operator_key = quote_plus(str(key[:-1]), safe='><')
            query_parts.append(f"{operator_key}={quote_plus(str(value))}")
        else:
            query_parts.append(urlencode({str(key): str(value)}))
    query = '&'.join(query_parts)
    url = f"{_BASE_URL}/{resource}?{query}" if query else f"{_BASE_URL}/{resource}"
    try:
        response = requests.get(
            url,
            headers={"Accept": "application/json", "User-Agent": _USER_AGENT},
            timeout=_timeout_seconds(),
        )
        if response.status_code != 200:
            raise OpenF1FallbackError(f"OpenF1 returned HTTP {response.status_code} for {resource}.")
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise OpenF1FallbackError(f"OpenF1 request for {resource} failed.") from exc
    if not isinstance(payload, list):
        raise OpenF1FallbackError(f"OpenF1 returned an invalid {resource} response.")
    return payload


def _event_value(session, key):
    event = getattr(session, "event", None)
    try:
        return event.get(key)
    except AttributeError:
        try:
            return event[key]
        except (KeyError, TypeError):
            return None


def _session_year(session):
    for value in (_event_value(session, "EventDate"), getattr(session, "date", None)):
        timestamp = pd.to_datetime(value, errors="coerce", utc=True)
        if not pd.isna(timestamp):
            return int(timestamp.year)
    return None


def _session_country(session):
    for key in ("Country", "CountryName"):
        value = _event_value(session, key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _session_name(session):
    value = getattr(session, "name", None) or _event_value(session, "SessionName")
    return str(value).strip() if value else None


@lru_cache(maxsize=96)
def _find_session(year, country, session_name):
    sessions = _request_json(
        "sessions",
        {"year": int(year), "country_name": country, "session_name": session_name},
    )
    if not sessions:
        raise OpenF1FallbackError("OpenF1 has no matching historical session.")
    matching = [
        item for item in sessions
        if item.get("session_key") is not None and item.get("session_name") == session_name
    ]
    if not matching:
        raise OpenF1FallbackError("OpenF1 returned no usable matching session.")
    return int(matching[0]["session_key"])


def _lap_identity(lap):
    try:
        driver_number = int(lap.get("DriverNumber"))
        lap_number = int(float(lap.get("LapNumber")))
    except (AttributeError, TypeError, ValueError):
        raise OpenF1FallbackError("The selected lap does not include a driver or lap number.")
    return driver_number, lap_number


def _selected_openf1_lap(session_key, driver_number, lap_number):
    laps = _request_json(
        "laps",
        {
            "session_key": session_key,
            "driver_number": driver_number,
            "lap_number": lap_number,
        },
    )
    for lap in laps:
        duration = pd.to_numeric(lap.get("lap_duration"), errors="coerce")
        started = pd.to_datetime(lap.get("date_start"), errors="coerce", utc=True)
        if pd.notna(started) and pd.notna(duration) and float(duration) > 0:
            return started, float(duration)
    raise OpenF1FallbackError("OpenF1 has no complete record for the selected lap.")


def _lap_window(started, duration_seconds):
    # A little padding retains the first/last sample when endpoints use
    # slightly different sample timestamps than the recorded lap boundaries.
    start = started - timedelta(seconds=0.5)
    end = started + timedelta(seconds=float(duration_seconds) + 0.8)
    return start.isoformat(), end.isoformat()


def _telemetry_frame(car_samples, location_samples, lap_started):
    car = pd.DataFrame(car_samples)
    if car.empty or "date" not in car.columns or "speed" not in car.columns:
        raise OpenF1FallbackError("OpenF1 returned no speed samples for the selected lap.")

    car["Date"] = pd.to_datetime(car["date"], errors="coerce", utc=True)
    car["Speed"] = pd.to_numeric(car["speed"], errors="coerce")
    car = car.dropna(subset=["Date", "Speed"]).sort_values("Date").drop_duplicates("Date")
    if len(car) < 6:
        raise OpenF1FallbackError("OpenF1 returned too few speed samples for the selected lap.")

    brake = pd.to_numeric(car.get("brake"), errors="coerce")
    # OpenF1 exposes brake as 0/100 while FastF1's equivalent channel is a
    # boolean. Normalize to FastF1's 0/1 convention so the shared throttle /
    # brake chart and braking-intensity map retain their existing scale.
    if hasattr(brake, "max") and pd.notna(brake.max()) and float(brake.max()) > 1:
        brake = brake / 100.0

    trace = pd.DataFrame({
        "Date": car["Date"],
        "Speed": car["Speed"],
        "Throttle": pd.to_numeric(car.get("throttle"), errors="coerce"),
        "Brake": brake,
        "nGear": pd.to_numeric(car.get("n_gear"), errors="coerce"),
        "RPM": pd.to_numeric(car.get("rpm"), errors="coerce"),
    })

    if location_samples:
        location = pd.DataFrame(location_samples)
        if not location.empty and "date" in location.columns:
            location["Date"] = pd.to_datetime(location["date"], errors="coerce", utc=True)
            location["X"] = pd.to_numeric(location.get("x"), errors="coerce")
            location["Y"] = pd.to_numeric(location.get("y"), errors="coerce")
            location = location.dropna(subset=["Date"]).sort_values("Date").drop_duplicates("Date")
            if not location.empty:
                trace = pd.merge_asof(
                    trace.sort_values("Date"),
                    location.loc[:, ["Date", "X", "Y"]],
                    on="Date",
                    direction="nearest",
                    tolerance=pd.Timedelta(milliseconds=650),
                )

    elapsed = (trace["Date"] - lap_started).dt.total_seconds().clip(lower=0)
    delta_seconds = elapsed.diff().fillna(0).clip(lower=0, upper=2.0)
    average_speed_mps = ((trace["Speed"] + trace["Speed"].shift(1).fillna(trace["Speed"])) / 2) / 3.6
    trace["Distance"] = (average_speed_mps * delta_seconds).cumsum()
    trace["Time"] = pd.to_timedelta(elapsed, unit="s")
    return trace.loc[:, [
        column for column in ("Time", "Distance", "Speed", "Throttle", "Brake", "nGear", "RPM", "X", "Y")
        if column in trace.columns
    ]]


def trace_for_fastf1_lap(session, lap):
    """Return a normalized OpenF1 trace for an already-selected FastF1 lap.

    The caller supplies the FastF1 session and its selected lap, so selection,
    driver labels and timing remain consistent with the rest of the dashboard.
    """
    if not _enabled():
        raise OpenF1FallbackError("OpenF1 fallback is disabled.")

    year = _session_year(session)
    country = _session_country(session)
    session_name = _session_name(session)
    if not year or year < 2023 or not country or not session_name:
        raise OpenF1FallbackError("This FastF1 session cannot be matched to OpenF1.")

    driver_number, lap_number = _lap_identity(lap)
    session_key = _find_session(year, country, session_name)
    started, duration = _selected_openf1_lap(session_key, driver_number, lap_number)
    date_start, date_end = _lap_window(started, duration)
    query = {
        "session_key": session_key,
        "driver_number": driver_number,
        "date>=": date_start,
        "date<=": date_end,
    }
    car_samples = _request_json("car_data", query)
    try:
        location_samples = _request_json("location", query)
    except OpenF1FallbackError:
        # Position data improves the map but must not make the speed analysis
        # unusable when only the location endpoint has a transient issue.
        location_samples = []
    return _telemetry_frame(car_samples, location_samples, started)
