import json
from email.message import Message
from pathlib import Path
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

import pandas as pd

import session_data


FIXTURES = Path(__file__).parent / "fixtures" / "openf1"


def _fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class _Response:
    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, limit=-1):
        return self.body[:limit]


class SessionDataTests(unittest.TestCase):
    def setUp(self):
        session_data.clear_provider_cache()
        session_data.clear_rate_window_for_tests()

    def test_fixture_normalization_preserves_driver_identity_and_partial_fields(self):
        payload = _fixture("2023_monaco_race.json")
        drivers = session_data.normalize_drivers(payload["drivers"])
        self.assertEqual(drivers["driver_number"].tolist(), ["1", "14"])
        self.assertEqual(drivers.loc[0, "abbreviation"], "VER")

        stints = session_data.normalize_stints(payload["stints"], drivers)
        pits = session_data.normalize_pits(payload["pit"], drivers)
        laps = session_data.normalize_laps(payload["laps"], drivers, stints, pits)
        self.assertEqual(laps.loc[0, "compound"], "MEDIUM")
        self.assertTrue(bool(laps.loc[0, "pit_in"]) is False)
        self.assertFalse(bool(laps.loc[0, "is_pit_out_lap"]))
        self.assertTrue(pd.isna(laps.loc[laps["lap_number"] == 2, "lap_duration"]).all())
        self.assertEqual(pits.loc[0, "duration_semantics"], "pit_lane_total")
        self.assertTrue(pd.isna(pits.loc[0, "stop_duration"]))

    def test_results_keep_qualifying_phases_and_classification_flags(self):
        fixtures = _fixture("session_variants.json")
        drivers = session_data.normalize_drivers([
            {"driver_number": 4, "name_acronym": "NOR", "full_name": "Lando Norris"},
            {"driver_number": 81, "name_acronym": "PIA", "full_name": "Oscar Piastri"},
            {"driver_number": 1, "name_acronym": "VER", "full_name": "Max Verstappen"},
            {"driver_number": 16, "name_acronym": "LEC", "full_name": "Charles Leclerc"},
            {"driver_number": 55, "name_acronym": "SAI", "full_name": "Carlos Sainz"},
            {"driver_number": 11, "name_acronym": "PER", "full_name": "Sergio Perez"},
        ])
        qualifying = session_data.normalize_results(fixtures["qualifying_results"], drivers, "Qualifying")
        self.assertEqual(qualifying.loc[0, "duration_q1"], 90.1)
        self.assertEqual(qualifying.loc[0, "duration_q3"], 89.2)
        sprint = session_data.normalize_results(fixtures["sprint_results"], drivers, "Sprint")
        self.assertEqual(set(sprint["status"]), {"Finished", "DNS", "DSQ"})
        self.assertEqual(sprint.loc[sprint["abbreviation"] == "SAI", "status"].iloc[0], "DNS")
        sprint_qualifying = session_data.normalize_results(fixtures["qualifying_results"], drivers, "Sprint Qualifying")
        self.assertEqual(sprint_qualifying.loc[0, "duration_sq1"], 90.1)
        race = session_data.normalize_results(fixtures["sprint_results"], drivers, "Race")
        self.assertTrue(pd.isna(race.loc[race["abbreviation"] == "VER", "best_lap_time"].iloc[0]))
        self.assertEqual(race.loc[race["abbreviation"] == "SAI", "status"].iloc[0], "DNS")

    def test_jolpica_fallback_maps_results_gaps_and_pit_stops(self):
        fixtures = _fixture("session_variants.json")
        drivers = session_data.normalize_drivers([
            {"driver_number": 1, "name_acronym": "VER", "full_name": "Max Verstappen"},
            {"driver_number": 4, "name_acronym": "NOR", "full_name": "Lando Norris"},
        ])
        ref = session_data.SessionRef(
            year=2023, round=6, event_name="Monaco Grand Prix", country_name="Monaco",
            session_name="Race", session_type="Race", session_key=9094, meeting_key=1210,
        )
        responses = {
            "jolpica_results": fixtures["jolpica_race"],
            "jolpica_drivers": fixtures["jolpica_drivers"],
            "jolpica_pitstops": fixtures["jolpica_pitstops"],
            "jolpica_sprint": fixtures["jolpica_sprint"],
        }

        def jolpica_json(_path, *, endpoint, query=None):
            return responses[endpoint]

        with patch.object(session_data, "_jolpica_json", side_effect=jolpica_json):
            race = session_data._jolpica_results(ref, "Race", drivers)
            pits = session_data._jolpica_pits(ref, drivers)
            practice = session_data._jolpica_results(ref, "Practice 1", drivers)
            sprint = session_data._jolpica_results(
                session_data.SessionRef(
                    year=2023, round=6, event_name="Monaco Grand Prix", country_name="Monaco",
                    session_name="Sprint", session_type="Sprint", session_key=9093, meeting_key=1210,
                ),
                "Sprint", drivers,
            )
        normalized = session_data.normalize_results(race.to_dict("records"), drivers, "Race")
        normalized_grid = session_data.normalize_grid(race.to_dict("records"), drivers)
        normalized_pits = session_data.normalize_pits(pits.to_dict("records"), drivers)
        self.assertEqual(normalized.loc[normalized["abbreviation"] == "NOR", "gap"].iloc[0], "+1 Lap")
        self.assertEqual(normalized.loc[normalized["abbreviation"] == "NOR", "source"].iloc[0], "jolpica.results")
        self.assertEqual(
            dict(zip(normalized_grid["abbreviation"], normalized_grid["grid_position"])),
            {"VER": 2, "NOR": 1},
        )
        self.assertTrue(practice.empty)
        self.assertEqual(sprint.iloc[0]["source"], "jolpica.sprint")
        self.assertEqual(sprint.iloc[0]["grid_position"], 1)
        self.assertEqual(normalized_pits.loc[0, "driver_number"], "1")
        self.assertEqual(normalized_pits.loc[0, "stop_duration"], 2.4)
        self.assertEqual(normalized_pits.loc[0, "duration_semantics"], "stationary_service")
        self.assertEqual(normalized_pits.loc[0, "source"], "jolpica.pitstops")

    def test_jolpica_qualifying_phase_times_are_seconds(self):
        fixtures = _fixture("session_variants.json")
        drivers = session_data.normalize_drivers([
            {"driver_number": 1, "name_acronym": "VER", "full_name": "Max Verstappen"},
        ])
        ref = session_data.SessionRef(
            year=2023, round=6, event_name="Monaco Grand Prix", country_name="Monaco",
            session_name="Qualifying", session_type="Qualifying", session_key=9090, meeting_key=1210,
        )
        with patch.object(session_data, "_jolpica_json", return_value=fixtures["jolpica_qualifying"]):
            rows = session_data._jolpica_results(ref, "Qualifying", drivers)
        normalized = session_data.normalize_results(rows.to_dict("records"), drivers, "Qualifying")
        self.assertEqual(normalized.loc[0, "duration_q1"], 72.1)
        self.assertEqual(normalized.loc[0, "duration_q3"], 70.9)
        self.assertEqual(normalized.loc[0, "best_lap_time"], 70.9)

    def test_lap_trace_converts_brake_and_integrates_approximate_distance(self):
        ref = session_data.SessionRef(
            year=2023, round=6, event_name="Monaco Grand Prix", country_name="Monaco",
            session_name="Race", session_type="Race", session_key=9094, meeting_key=1210,
        )
        base = pd.Timestamp("2023-05-28T13:04:22Z")
        car_rows, location_rows = [], []
        for index in range(16):
            stamp = base + pd.to_timedelta(index * 0.25, unit="s")
            iso = stamp.isoformat()
            car_rows.append({"date": iso, "speed": 180 + index, "throttle": 75, "brake": 100 if index == 3 else 0, "n_gear": 5, "rpm": 10000, "drs": 10})
            location_rows.append({"date": iso, "x": index * 10, "y": index * -4})
        car_rows.extend([
            {"date": (base - pd.to_timedelta(0.25, unit="s")).isoformat(), "speed": 170, "throttle": 0, "brake": 0},
            {"date": (base + pd.to_timedelta(4.25, unit="s")).isoformat(), "speed": 170, "throttle": 0, "brake": 0},
        ])
        location_rows.extend([
            {"date": (base - pd.to_timedelta(0.25, unit="s")).isoformat(), "x": -10, "y": -10},
            {"date": (base + pd.to_timedelta(4.25, unit="s")).isoformat(), "x": 170, "y": -70},
        ])

        def records(endpoint, _query, **_kwargs):
            return car_rows if endpoint == "car_data" else location_rows

        lap = {"driver_number": "1", "lap_number": 1, "date_start": base.isoformat(), "lap_duration": 4.0}
        with patch.object(session_data, "_openf1_records", side_effect=records):
            trace = session_data.get_selected_lap_trace(ref, lap)
        self.assertEqual(len(trace), 16)
        self.assertEqual(trace.loc[3, "Brake"], 1.0)
        self.assertEqual(trace.loc[0, "DRS"], 10)
        self.assertGreater(trace["Distance"].iloc[-1], 0)
        self.assertTrue(trace.attrs["quality"]["distance_derived"])
        self.assertTrue(trace.attrs["quality"]["has_position"])

    def test_car_only_trace_survives_missing_or_unsynchronized_location(self):
        ref = session_data.SessionRef(
            year=2023, round=6, event_name="Monaco Grand Prix", country_name="Monaco",
            session_name="Race", session_type="Race", session_key=9094, meeting_key=1210,
        )
        base = pd.Timestamp("2023-05-28T13:04:22Z")
        rows = [
            {"date": (base + pd.to_timedelta(index * 0.25, unit="s")).isoformat(), "speed": 150 + index}
            for index in range(8)
        ]
        outside_locations = [
            {"date": (base + pd.to_timedelta(10 + index, unit="s")).isoformat(), "x": index, "y": index}
            for index in range(8)
        ]
        lap = {"driver_number": "1", "lap_number": 1, "date_start": base.isoformat(), "lap_duration": 2.0}

        def records(endpoint, _query, **_kwargs):
            return rows if endpoint == "car_data" else outside_locations

        with patch.object(session_data, "_openf1_records", side_effect=records):
            trace = session_data.get_selected_lap_trace(ref, lap, with_position=True)
        self.assertEqual(len(trace), 8)
        self.assertTrue(trace.attrs["quality"]["has_position"] is False)
        self.assertTrue(trace["X"].isna().all())
        self.assertTrue(trace["Throttle"].isna().all())

        with patch.object(session_data, "_openf1_records", return_value=rows[:5]):
            with self.assertRaisesRegex(session_data.ProviderError, "too few usable"):
                session_data.get_selected_lap_trace(ref, lap, with_position=False)

    def test_session_schedule_ignores_cancelled_and_not_yet_historical_sessions(self):
        meetings = [
            {"meeting_key": 10, "meeting_name": "Past Grand Prix", "country_name": "X", "date_start": "2024-01-01T10:00:00Z"},
            {"meeting_key": 11, "meeting_name": "Cancelled Grand Prix", "country_name": "Y", "date_start": "2024-01-02T10:00:00Z", "is_cancelled": True},
        ]
        sessions = [
            {"meeting_key": 10, "session_key": 100, "session_name": "Race", "session_type": "Race", "date_start": "2024-01-01T10:00:00Z", "date_end": "2024-01-01T12:00:00Z"},
            {"meeting_key": 10, "session_key": 101, "session_name": "Practice 1", "session_type": "Practice", "date_start": "2024-01-01T09:00:00Z", "date_end": "2024-01-01T09:00:00Z"},
            {"meeting_key": 11, "session_key": 102, "session_name": "Race", "session_type": "Race", "date_start": "2024-01-02T10:00:00Z", "date_end": "2024-01-02T12:00:00Z"},
            {"meeting_key": 10, "session_key": 103, "session_name": "Race 2", "session_type": "Race", "date_start": "2027-01-02T10:00:00Z", "date_end": "2027-01-02T12:01:00Z"},
        ]
        with patch.object(session_data, "_openf1_records", side_effect=[meetings, sessions]), patch.object(
            session_data, "_utc_now", return_value=pd.Timestamp("2024-01-05T00:00:00Z").to_pydatetime()
        ):
            refs = session_data.get_session_refs(2024)
        self.assertEqual([ref.session_key for ref in refs], [101, 100])
        self.assertTrue(all(ref.year >= 2023 for ref in refs))

    def test_qualifying_fixture_builds_stable_session_refs(self):
        fixture = _fixture("2023_monaco_qualifying.json")
        with patch.object(session_data, "_openf1_records", side_effect=[
            [fixture["meeting"]], fixture["sessions"],
        ]):
            refs = session_data.get_session_refs(2023)
        self.assertEqual([(ref.session_name, ref.session_key) for ref in refs], [("Qualifying", 9090), ("Race", 9094)])
        self.assertTrue(all(ref.meeting_key == 1210 and ref.round == 1 for ref in refs))

    def test_http_query_operators_are_encoded_and_bad_json_is_sanitized(self):
        captured = {}
        body = json.dumps([{"session_key": 9094}]).encode()

        def fake_urlopen(request, timeout, context=None):
            captured["url"] = request.full_url
            captured["timeout"] = timeout
            captured["agent"] = request.headers.get("User-agent")
            return _Response(body)

        with patch.object(session_data, "_wait_for_request_slot"), patch.object(session_data, "urlopen", side_effect=fake_urlopen):
            result = session_data._openf1_records("laps", {"date>": "2023-01-01T00:00:00Z"}, use_cache=False)
        self.assertEqual(result[0]["session_key"], 9094)
        self.assertIn("date%3E=", captured["url"])
        self.assertIn("F1Analyzer/", captured["agent"])
        with patch.object(session_data, "_wait_for_request_slot"), patch.object(
            session_data, "urlopen", return_value=_Response(b"not-json")
        ):
            with self.assertRaisesRegex(session_data.ProviderError, "malformed data"):
                session_data._openf1_records("laps", {"session_key": 1}, use_cache=False)
        with self.assertRaisesRegex(ValueError, "Unsupported OpenF1 filter field"):
            session_data._openf1_records("laps", {"date><": "2023-01-01"}, use_cache=False)

    def test_rate_limit_retry_respects_retry_after_and_does_not_expose_body(self):
        headers = Message()
        headers["Retry-After"] = "3"
        calls = []
        body = b"[]"

        def fake_urlopen(_request, timeout, context=None):
            calls.append(timeout)
            if len(calls) == 1:
                raise HTTPError("https://api.openf1.org/v1/laps", 429, "Too many requests", headers, None)
            return _Response(body)

        with patch.object(session_data, "_wait_for_request_slot"), patch.object(session_data, "urlopen", side_effect=fake_urlopen), patch.object(session_data.time, "sleep") as sleep:
            self.assertEqual(session_data._openf1_records("laps", {"session_key": 1}, use_cache=False), [])
        self.assertEqual(len(calls), 2)
        sleep.assert_called_once_with(3.0)
        with patch.object(session_data, "_utc_now", return_value=pd.Timestamp("2023-05-28T13:00:00Z").to_pydatetime()):
            self.assertEqual(session_data._retry_after_seconds({"Retry-After": "Sun, 28 May 2023 13:00:05 GMT"}), 5.0)

    def test_long_retry_after_is_not_retried_early(self):
        headers = Message()
        headers["Retry-After"] = "60"
        calls = []

        def fake_urlopen(_request, timeout, context=None):
            calls.append(timeout)
            raise HTTPError("https://api.openf1.org/v1/laps", 429, "Too many requests", headers, None)

        with patch.object(session_data, "_wait_for_request_slot"), patch.object(
            session_data, "urlopen", side_effect=fake_urlopen
        ), patch.object(session_data.time, "sleep") as sleep:
            with self.assertRaises(session_data.ProviderError) as error:
                session_data._openf1_records("laps", {"session_key": 1}, use_cache=False)
        self.assertEqual(error.exception.kind, "rate_limited")
        self.assertEqual(len(calls), 1)
        sleep.assert_not_called()

    def test_provider_cache_is_json_safe_and_byte_bounded(self):
        with patch.object(session_data, "_CACHE_MAX_BYTES", 40):
            session_data._cache_set(("provider", "one"), {"value": "1234567890"}, 60)
            first = session_data._cache_get(("provider", "one"))
            self.assertEqual(first, {"value": "1234567890"})
            first["value"] = "changed"
            self.assertEqual(session_data._cache_get(("provider", "one"))["value"], "1234567890")
            session_data._cache_set(("provider", "two"), {"value": "abcdefghij"}, 60)
            stats = session_data.provider_stats()
        self.assertEqual(stats["cache_entries"], 1)
        self.assertLessEqual(stats["cache_bytes"], 40)

    def test_bundle_keeps_optional_provider_failures_separate(self):
        ref = session_data.SessionRef(
            year=2023, round=6, event_name="Monaco Grand Prix", country_name="Monaco",
            session_name="Race", session_type="Race", session_key=9094, meeting_key=1210,
        )
        mapping = {
            "drivers": [{"driver_number": 1, "name_acronym": "VER", "full_name": "Max Verstappen"}],
            "session_result": [{"driver_number": 1, "position": 1, "duration": 100.0, "gap_to_leader": 0, "number_of_laps": 1}],
            "laps": [{"driver_number": 1, "lap_number": 1, "lap_duration": 100.0, "date_start": "2023-05-28T13:04:22Z"}],
        }

        def request(_ref, endpoint, _query=None, *, use_cache=True):
            if endpoint in mapping:
                return mapping[endpoint]
            raise session_data.ProviderError("not available", endpoint=endpoint)

        with patch.object(session_data, "_request_endpoint", side_effect=request), patch.object(
            session_data, "_jolpica_results", return_value=pd.DataFrame()
        ), patch.object(session_data, "_jolpica_pits", return_value=pd.DataFrame()), patch.object(
            session_data, "_qualifying_grid_ref", return_value=None
        ):
            bundle = session_data.load_session_bundle(ref, laps=True, results=True, strategy=True, race_context=True)
        self.assertEqual(bundle.results.loc[0, "position"], 1)
        self.assertEqual(bundle.quality["endpoints"]["weather"]["state"], "unavailable")
        self.assertEqual(bundle.quality["row_counts"]["laps"], 1)

    def test_partial_openf1_results_are_supplemented_by_source_labeled_jolpica_rows(self):
        ref = session_data.SessionRef(
            year=2023, round=6, event_name="Monaco Grand Prix", country_name="Monaco",
            session_name="Race", session_type="Race", session_key=9094, meeting_key=1210,
        )
        drivers = [
            {"driver_number": 1, "name_acronym": "VER", "full_name": "Max Verstappen"},
            {"driver_number": 4, "name_acronym": "NOR", "full_name": "Lando Norris"},
        ]
        fallback = pd.DataFrame([
            {"driver_number": "1", "abbreviation": "VER", "position": 1, "grid_position": 2, "status": "Finished", "source": "jolpica.results"},
            {"driver_number": "4", "abbreviation": "NOR", "position": 2, "grid_position": 1, "status": "+1 Lap", "source": "jolpica.results"},
        ])

        def request(_ref, endpoint, _query=None, *, use_cache=True):
            if endpoint == "drivers":
                return drivers
            if endpoint == "session_result":
                return [{"driver_number": 1, "position": 1, "duration": 6912.4, "gap_to_leader": 0}]
            raise session_data.ProviderError("not available", endpoint=endpoint)

        with patch.object(session_data, "_request_endpoint", side_effect=request), patch.object(
            session_data, "_jolpica_results", return_value=fallback
        ), patch.object(session_data, "_qualifying_grid_ref", return_value=None):
            bundle = session_data.load_session_bundle(ref, laps=False, results=True)
        sources = dict(zip(bundle.results["abbreviation"], bundle.results["source"]))
        self.assertEqual(sources["VER"], "openf1.session_result")
        self.assertEqual(sources["NOR"], "jolpica.results")
        self.assertTrue(pd.isna(bundle.results.loc[bundle.results["abbreviation"] == "VER", "best_lap_time"].iloc[0]))
        self.assertEqual(bundle.quality["row_counts"]["results"], 2)
        self.assertIn("source-labeled", " ".join(bundle.quality["notes"]))

    def test_partial_openf1_grid_uses_jolpica_only_for_missing_drivers(self):
        ref = session_data.SessionRef(
            year=2023, round=6, event_name="Monaco Grand Prix", country_name="Monaco",
            session_name="Race", session_type="Race", session_key=9094, meeting_key=1210,
        )
        drivers = [
            {"driver_number": 1, "name_acronym": "VER", "full_name": "Max Verstappen"},
            {"driver_number": 4, "name_acronym": "NOR", "full_name": "Lando Norris"},
        ]
        results = [
            {"driver_number": 1, "position": 1, "duration": 100.0},
            {"driver_number": 4, "position": 2, "duration": 101.0},
        ]
        fallback = pd.DataFrame([
            {"driver_number": "1", "abbreviation": "VER", "grid_position": 2, "source": "jolpica.results"},
            {"driver_number": "4", "abbreviation": "NOR", "grid_position": 1, "source": "jolpica.results"},
        ])
        grid_ref = session_data.SessionRef(
            year=2023, round=6, event_name="Monaco Grand Prix", country_name="Monaco",
            session_name="Qualifying", session_type="Qualifying", session_key=9090, meeting_key=1210,
        )

        def request(_ref, endpoint, _query=None, *, use_cache=True):
            if endpoint == "drivers":
                return drivers
            if endpoint == "session_result":
                return results
            raise session_data.ProviderError("not available", endpoint=endpoint)

        def openf1(endpoint, _query=None, **_kwargs):
            if endpoint == "starting_grid":
                return [{"driver_number": 1, "position": 1, "lap_duration": 71.2}]
            raise AssertionError(f"unexpected endpoint {endpoint}")

        with patch.object(session_data, "_request_endpoint", side_effect=request), patch.object(
            session_data, "_openf1_records", side_effect=openf1
        ), patch.object(session_data, "_qualifying_grid_ref", return_value=grid_ref), patch.object(
            session_data, "_jolpica_results", return_value=fallback
        ):
            bundle = session_data.load_session_bundle(ref, laps=False, results=True)
        self.assertEqual(bundle.grid["driver_number"].tolist(), ["1", "4"])
        self.assertEqual(bundle.grid["source"].tolist(), ["openf1.starting_grid", "jolpica.results"])
        self.assertEqual(bundle.quality["endpoints"]["starting_grid"]["source"], "openf1.starting_grid+jolpica.grid")

    def test_jolpica_not_found_and_outage_states_remain_distinct(self):
        ref = session_data.SessionRef(
            year=2023, round=6, event_name="Monaco Grand Prix", country_name="Monaco",
            session_name="Race", session_type="Race", session_key=9094, meeting_key=1210,
        )

        def request(_ref, endpoint, _query=None, *, use_cache=True):
            if endpoint == "drivers":
                return [{"driver_number": 1, "name_acronym": "VER"}]
            if endpoint == "session_result":
                return []
            raise session_data.ProviderError("unavailable", endpoint=endpoint)

        for error, expected in (
            (session_data.ProviderError("not found", kind="not_found"), "not_found"),
            (session_data.ProviderError("offline", kind="network"), "unavailable"),
        ):
            with self.subTest(expected=expected), patch.object(
                session_data, "_request_endpoint", side_effect=request
            ), patch.object(session_data, "_jolpica_results", side_effect=error), patch.object(
                session_data, "_qualifying_grid_ref", return_value=None
            ):
                bundle = session_data.load_session_bundle(ref, laps=False, results=True)
            self.assertEqual(bundle.quality["endpoints"]["jolpica_results"]["state"], expected)


if __name__ == "__main__":
    unittest.main()
