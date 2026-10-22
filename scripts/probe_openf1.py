#!/usr/bin/env python3
"""Paced, read-only OpenF1 coverage probe for completed archive sessions.

This is an opt-in engineering tool. It never saves raw telemetry or provider
response bodies. A report contains endpoint names, row counts, byte counts,
sample rates, timestamp alignment, and sanitized error categories only.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import sys
import time

import pandas as pd

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))
import session_data


def _sample_rate(frame: pd.DataFrame, time_column: str = "date") -> float | None:
    if frame.empty or time_column not in frame:
        return None
    times = pd.to_datetime(frame[time_column], format="mixed", utc=True, errors="coerce").dropna().sort_values()
    if len(times) < 2:
        return None
    span = (times.iloc[-1] - times.iloc[0]).total_seconds()
    return round((len(times) - 1) / span, 2) if span > 0 else None


def _lap_window(ref: session_data.SessionRef, driver_number: str, lap: dict) -> dict[str, str]:
    start, end, _duration = session_data._lap_start_and_end(lap)
    return {
        "session_key": ref.session_key,
        "driver_number": driver_number,
        "date>": (start - pd.to_timedelta(0.5, unit="s")).isoformat(),
        "date<": (end + pd.to_timedelta(0.5, unit="s")).isoformat(),
    }


def _probe_session(ref: session_data.SessionRef, include_trace: bool) -> dict:
    report = {
        "year": ref.year, "event": ref.event_name, "session": ref.session_name,
        "session_key": ref.session_key, "meeting_key": ref.meeting_key, "end": ref.date_end,
        "endpoints": {},
    }
    requests = ["drivers", "laps", "session_result", "stints", "pit", "weather", "position", "intervals", "race_control"]
    for endpoint in requests:
        try:
            before = session_data.provider_stats()["endpoints"].get(f"openf1.{endpoint}", {}).get("response_bytes", 0)
            records = session_data._request_endpoint(ref, endpoint, use_cache=False)
            stats = session_data.provider_stats()
            metric = stats["endpoints"].get(f"openf1.{endpoint}", {})
            report["endpoints"][endpoint] = {
                "state": "available" if records else "empty",
                "records": len(records),
                "response_bytes": metric.get("response_bytes", 0) - before,
                "non_null_field_counts": {
                    field: sum(record.get(field) is not None for record in records)
                    for field in sorted({key for record in records for key in record})
                },
            }
        except session_data.ProviderError as exc:
            report["endpoints"][endpoint] = {"state": "unavailable", "reason": exc.kind}
    try:
        grid_ref = session_data._qualifying_grid_ref(ref)
        if grid_ref is None:
            report["endpoints"]["starting_grid"] = {"state": "not_applicable"}
        else:
            before = session_data.provider_stats()["endpoints"].get("openf1.starting_grid", {}).get("response_bytes", 0)
            grid = session_data._openf1_records("starting_grid", {"session_key": grid_ref.session_key}, use_cache=False)
            metric = session_data.provider_stats()["endpoints"].get("openf1.starting_grid", {})
            report["endpoints"]["starting_grid"] = {
                "state": "available" if grid else "empty",
                "records": len(grid), "response_bytes": metric.get("response_bytes", 0) - before,
                "non_null_field_counts": {
                    field: sum(record.get(field) is not None for record in grid)
                    for field in sorted({key for record in grid for key in record})
                },
                "queried_session_key": grid_ref.session_key,
            }
    except session_data.ProviderError as exc:
        report["endpoints"]["starting_grid"] = {"state": "unavailable", "reason": exc.kind}
    if include_trace:
        try:
            drivers = session_data.normalize_drivers(session_data._request_endpoint(ref, "drivers", use_cache=False))
            laps = session_data._request_endpoint(ref, "laps", use_cache=False)
            candidates = []
            for driver in drivers.head(2).to_dict("records"):
                driver_laps = [row for row in laps if str(row.get("driver_number")) == driver["driver_number"] and session_data._number(row.get("lap_duration"))]
                if driver_laps:
                    candidates.append((driver, min(driver_laps, key=lambda row: float(row["lap_duration"]))))
            alignment = []
            for driver, lap in candidates:
                window = _lap_window(ref, driver["driver_number"], lap)
                samples = {}
                frames = {}
                for endpoint in ("car_data", "location"):
                    try:
                        before = session_data.provider_stats()["endpoints"].get(f"openf1.{endpoint}", {}).get("response_bytes", 0)
                        rows = session_data._openf1_records(endpoint, window, use_cache=False)
                        metric = session_data.provider_stats()["endpoints"].get(f"openf1.{endpoint}", {})
                        frames[endpoint] = pd.DataFrame(rows)
                        samples[endpoint] = {
                            "records": len(rows), "sample_hz": _sample_rate(frames[endpoint]),
                            "response_bytes": metric.get("response_bytes", 0) - before,
                        }
                    except session_data.ProviderError as exc:
                        samples[endpoint] = {"records": 0, "reason": exc.kind}
                matched = None
                car = frames.get("car_data", pd.DataFrame())
                loc = frames.get("location", pd.DataFrame())
                if not car.empty and not loc.empty and "date" in car and "date" in loc:
                    car_times = pd.to_datetime(car["date"], format="mixed", utc=True, errors="coerce").dropna()
                    loc_times = pd.to_datetime(loc["date"], format="mixed", utc=True, errors="coerce").dropna()
                    seconds = [min(abs((value - other).total_seconds()) for other in loc_times) for value in car_times]
                    matched = round(sum(value <= 0.75 for value in seconds) / max(1, len(seconds)), 3)
                alignment.append({"driver_number": driver["driver_number"], "lap_number": lap.get("lap_number"), "channels": samples, "car_samples_with_location_within_750ms": matched})
            report["selected_lap_trace"] = alignment
        except session_data.ProviderError as exc:
            report["selected_lap_trace"] = {"state": "unavailable", "reason": exc.kind}
    if ref.circuit_info_url:
        try:
            corners = session_data.get_circuit_corners(ref)
            report["circuit_info"] = {"state": "available" if not corners.empty else "empty", "corner_count": len(corners), "coordinate_alignment": "unverified; heuristic markers remain the fallback"}
        except session_data.ProviderError as exc:
            report["circuit_info"] = {"state": "unavailable", "reason": exc.kind}
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", action="append", type=int, help="Year to inspect; repeat for multiple seasons (default: 2023 and 2024).")
    parser.add_argument("--event", help="Limit to an event name, such as 'Monaco Grand Prix'.")
    parser.add_argument("--session-type", action="append", help="Session type/name to inspect; repeat as needed (default: Race, Qualifying, Sprint, Practice).")
    parser.add_argument("--max-sessions", type=int, default=8, help="Maximum selected sessions; default is 8.")
    parser.add_argument("--skip-trace", action="store_true", help="Skip the two-driver selected-lap car/location sample check.")
    args = parser.parse_args()

    years = args.year or [2023, 2024]
    type_names = [value.casefold() for value in (args.session_type or ["Race", "Qualifying", "Sprint", "Practice"])]
    selected = []
    for year in years:
        refs = session_data.get_session_refs(year)
        for type_name in type_names:
            matches = [ref for ref in refs if type_name in ref.session_type.casefold() or type_name in ref.session_name.casefold()]
            if args.event:
                matches = [ref for ref in matches if args.event.casefold() in ref.event_name.casefold()]
            if matches:
                selected.append(matches[-1])
    unique = {(ref.year, ref.session_key): ref for ref in selected}
    sessions = list(unique.values())[:max(1, args.max_sessions)]
    reports = []
    for index, ref in enumerate(sessions):
        reports.append(_probe_session(ref, include_trace=not args.skip_trace))
        # session_data enforces a process-local limit of 25/minute and 0.45s
        # minimum spacing. This small pause also spaces report-only work.
        if index + 1 < len(sessions):
            time.sleep(0.5)
    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "policy": "Read-only completed-session probe; raw provider records are not written.",
        "request_budget": session_data.provider_stats(),
        "sessions": reports,
    }
    print(json.dumps(output, indent=2, allow_nan=False))
    return 0 if reports else 1


if __name__ == "__main__":
    raise SystemExit(main())
