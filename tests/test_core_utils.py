import os
import unittest
from unittest.mock import patch, MagicMock

import pandas as pd
import numpy as np

import data
import ui_utils
import ai_cache
import callbacks_shared
import ux_helpers
import graphs
from flask import Flask


class TestSessionTypeHelpers(unittest.TestCase):
    def test_is_race(self):
        self.assertTrue(data.is_race("Race"))
        self.assertTrue(data.is_race("Sprint"))
        self.assertFalse(data.is_race("Qualifying"))

    def test_is_qualifying(self):
        self.assertTrue(data.is_qualifying("Qualifying"))
        self.assertTrue(data.is_qualifying("Sprint Shootout"))
        self.assertFalse(data.is_qualifying("Race"))

    def test_is_practice(self):
        self.assertTrue(data.is_practice("Practice 1"))
        self.assertTrue(data.is_practice("FP2"))
        self.assertFalse(data.is_practice("Sprint"))


class TestTeamColorFallbacks(unittest.TestCase):
    def test_resolves_feed_team_alias_without_raw_color(self):
        self.assertEqual(data.resolve_team_color("Red Bull", raw_color=""), "#4781D7")
        self.assertEqual(data.resolve_team_color("RB F1 Team", raw_color=None), "#6C98FF")

    def test_get_driver_info_does_not_collapse_missing_colors_to_white(self):
        session = MagicMock()
        session.results = pd.DataFrame([
            {
                "Abbreviation": "VER",
                "FirstName": "Max",
                "LastName": "Verstappen",
                "TeamName": "Red Bull",
                "TeamColor": "",
            },
            {
                "Abbreviation": "NOR",
                "FirstName": "Lando",
                "LastName": "Norris",
                "TeamName": "McLaren",
                "TeamColor": None,
            },
        ])

        info = data.get_driver_info(session)

        self.assertEqual([driver["color"] for driver in info], ["#4781D7", "#F47600"])


class TestAiCache(unittest.TestCase):
    def test_cache_round_trip(self):
        ctx = "test_session_context"
        q = "Who had better pace?"
        r = "Driver A had better average pace."
        ai_cache.store_cached_response(ctx, q, r)
        self.assertEqual(ai_cache.get_cached_response(ctx, q), r)

    def test_cache_key_normalizes_question(self):
        key1 = ai_cache._cache_key("ctx", " Hello  ")
        key2 = ai_cache._cache_key("ctx", "hello")
        self.assertEqual(key1, key2)


class TestFeedbackAdminAuth(unittest.TestCase):
    def setUp(self):
        self.flask_app = Flask(__name__)

    def test_authorized_via_query_param(self):
        with patch.dict(os.environ, {"FEEDBACK_ADMIN_TOKEN": "secret"}, clear=False):
            with self.flask_app.test_request_context("/?feedback_admin=secret"):
                with patch.object(ui_utils.flask, "request") as req:
                    req.headers = MagicMock()
                    req.cookies = MagicMock()
                    req.headers.get.return_value = ""
                    req.cookies.get.return_value = ""
                    self.assertTrue(ui_utils._feedback_admin_authorized("?feedback_admin=secret"))

    def test_authorized_via_header(self):
        with patch.dict(os.environ, {"FEEDBACK_ADMIN_TOKEN": "secret"}, clear=False):
            with self.flask_app.test_request_context("/"):
                with patch.object(ui_utils.flask, "request") as req:
                    req.headers = MagicMock()
                    req.cookies = MagicMock()
                    req.headers.get.return_value = "secret"
                    req.cookies.get.return_value = ""
                    self.assertTrue(ui_utils._feedback_admin_authorized(""))


class TestUrlState(unittest.TestCase):
    def test_url_round_trip_includes_view_state(self):
        params = {
            "year": 2025,
            "race": "British Grand Prix",
            "session_type": "Race",
            "driver1": "NOR",
            "driver2": "PIA",
        }
        search = callbacks_shared._build_url_search(params, "tab-trackmap", {
            "d1_lap_mode": "specific",
            "d1_lap": 12,
            "d2_lap_mode": "fastest",
            "trackmap_mode": "speed",
        })
        parsed = callbacks_shared._parse_url_state(search)
        self.assertEqual(parsed["year"], 2025)
        self.assertEqual(parsed["race"], "British Grand Prix")
        self.assertEqual(parsed["session_type"], "Race")
        self.assertEqual(parsed["d1_lap_mode"], "specific")
        self.assertEqual(parsed["d1_lap"], 12)
        self.assertEqual(parsed["trackmap_mode"], "speed")

    def test_url_round_trip_includes_experience_mode(self):
        params = {
            "year": 2025,
            "race": "British Grand Prix",
            "session_type": "Race",
            "driver1": "NOR",
            "driver2": "PIA",
        }
        search = callbacks_shared._build_url_search(params, "tab-telemetry", {"mode": "engineer"})
        parsed = callbacks_shared._parse_url_state(search)
        self.assertEqual(parsed["mode"], "engineer")

    def test_invalid_url_view_state_is_ignored(self):
        parsed = callbacks_shared._parse_url_state("?tab=bad&d1_lap_mode=bad&d1_lap=-2&trackmap=bad&mode=bad")
        self.assertIsNone(parsed["tab"])
        self.assertIsNone(parsed["d1_lap_mode"])
        self.assertIsNone(parsed["d1_lap"])
        self.assertIsNone(parsed["trackmap_mode"])
        self.assertIsNone(parsed["mode"])


class TestUxHelpers(unittest.TestCase):
    def test_experience_mode_normalizes_to_beginner(self):
        self.assertEqual(ux_helpers.normalize_experience_mode("ENGINEER"), "engineer")
        self.assertEqual(ux_helpers.normalize_experience_mode("bad"), "beginner")

    def test_glossary_and_empty_state(self):
        self.assertIn("Time gap", ux_helpers.get_glossary_definition("delta"))
        self.assertIn("Top 2", ux_helpers.empty_state_text("Race", "beginner"))

    def test_comparison_shortcuts_pick_teammate_and_closest(self):
        driver_info = [
            {"abbr": "VER", "team": "Red Bull"},
            {"abbr": "PER", "team": "Red Bull"},
            {"abbr": "NOR", "team": "McLaren"},
        ]
        d1, d2 = ux_helpers.get_comparison_shortcut_pair(
            "teammates", driver_info, current_driver1="VER"
        )
        self.assertEqual((d1, d2), ("VER", "PER"))

        results = pd.DataFrame([
            {"Abbreviation": "VER", "Position": 1, "Time": pd.Timedelta(seconds=0)},
            {"Abbreviation": "NOR", "Position": 2, "Time": pd.Timedelta(seconds=2.1)},
            {"Abbreviation": "LEC", "Position": 3, "Time": pd.Timedelta(seconds=2.7)},
        ])
        d1, d2 = ux_helpers.get_comparison_shortcut_pair("closest", driver_info, results=results)
        self.assertEqual((d1, d2), ("NOR", "LEC"))


class TestLapSelection(unittest.TestCase):
    def test_specific_missing_lap_raises_clear_error(self):
        class Laps:
            def pick_drivers(self, driver):
                return pd.DataFrame({"Driver": [driver, driver], "LapNumber": [1, 3]})

        session = MagicMock()
        session.laps = Laps()

        with self.assertRaisesRegex(ValueError, "VER lap 2 is not available"):
            callbacks_shared._pick_driver_lap(session, "VER", "specific", 2, lambda *_: None)


class TestDeltaChartSegments(unittest.TestCase):
    def test_zero_crossing_is_inserted_into_both_colored_traces(self):
        ahead_x, ahead_y, behind_x, behind_y = graphs._split_delta_by_sign(
            np.array([0.0, 10.0]),
            np.array([1.0, -1.0]),
        )

        self.assertIn(5.0, ahead_x.tolist())
        self.assertIn(5.0, behind_x.tolist())
        cross_idx_ahead = ahead_x.tolist().index(5.0)
        cross_idx_behind = behind_x.tolist().index(5.0)
        self.assertEqual(ahead_y[cross_idx_ahead], 0.0)
        self.assertEqual(behind_y[cross_idx_behind], 0.0)

    def test_missing_delta_data_still_breaks_trace(self):
        ahead_x, ahead_y, behind_x, behind_y = graphs._split_delta_by_sign(
            np.array([0.0, 10.0, 20.0]),
            np.array([1.0, np.nan, -1.0]),
        )

        self.assertTrue(np.isnan(ahead_y[1]))
        self.assertTrue(np.isnan(behind_y[1]))
        self.assertNotIn(10.0, ahead_x[~np.isnan(ahead_y)].tolist())
        self.assertNotIn(10.0, behind_x[~np.isnan(behind_y)].tolist())


class TestLatestRaceDefault(unittest.TestCase):
    def test_latest_race_default_uses_latest_past_race(self):
        schedule_2025 = pd.DataFrame([
            {
                "EventName": "Old Grand Prix",
                "EventFormat": "conventional",
                "EventDate": "2025-03-10T00:00:00Z",
                "Session5": "Race",
                "Session5DateUtc": "2025-03-09T14:00:00Z",
            },
            {
                "EventName": "Future Grand Prix",
                "EventFormat": "conventional",
                "EventDate": "2025-09-10T00:00:00Z",
                "Session5": "Race",
                "Session5DateUtc": "2025-09-09T14:00:00Z",
            },
            {
                "EventName": "Latest Grand Prix",
                "EventFormat": "conventional",
                "EventDate": "2025-06-10T00:00:00Z",
                "Session5": "Race",
                "Session5DateUtc": "2025-06-09T14:00:00Z",
            },
        ])
        empty_schedule = pd.DataFrame(columns=schedule_2025.columns)

        def fake_schedule(year):
            return schedule_2025 if year == 2025 else empty_schedule

        with patch.object(data, "get_event_schedule_cached", side_effect=fake_schedule):
            latest = data.get_latest_race_session_default(now="2025-07-01T00:00:00Z")

        self.assertEqual(latest, {
            "year": 2025,
            "race": "Latest Grand Prix",
            "session_type": "Race",
        })


class TestPreloadJobs(unittest.TestCase):
    def setUp(self):
        with data._SESSION_PRELOAD_LOCK:
            data._SESSION_PRELOAD_FUTURES.clear()
            data._SESSION_PRELOAD_JOBS.clear()

    def test_preload_dedupes_and_reports_ready(self):
        with patch.object(data, "_load_session_granular_cached", return_value="session") as loader:
            first = data.preload_session(2025, "British Grand Prix", "Race", telemetry=True)
            second = data.preload_session(2025, "British Grand Prix", "Race", telemetry=True)
            self.assertIs(first, second)
            self.assertEqual(first.result(timeout=2), "session")
            status = data.get_preload_status(2025, "British Grand Prix", "Race", telemetry=True)

        self.assertEqual(status["status"], "ready")
        self.assertEqual(loader.call_count, 1)

    def test_preload_job_cleanup_removes_stale_completed_jobs(self):
        now = 1000.0
        with data._SESSION_PRELOAD_LOCK:
            for idx in range(data._MAX_TRACKED_PRELOAD_JOBS + 2):
                data._SESSION_PRELOAD_JOBS[str(idx)] = {
                    "id": str(idx),
                    "status": "ready",
                    "created_at": now - data._PRELOAD_JOB_TTL_SECONDS - idx - 1,
                    "updated_at": now - data._PRELOAD_JOB_TTL_SECONDS - idx - 1,
                }
            data._cleanup_preload_jobs_locked(now=now)
            self.assertLessEqual(len(data._SESSION_PRELOAD_JOBS), data._MAX_TRACKED_PRELOAD_JOBS)


class TestApiValidation(unittest.TestCase):
    def test_preload_status_requires_params(self):
        import app as app_module
        client = app_module.server.test_client()
        response = client.get("/api/preload-status")
        self.assertEqual(response.status_code, 400)

    def test_perf_requires_admin_token_and_returns_snapshot(self):
        import app as app_module
        client = app_module.server.test_client()
        with patch.dict(os.environ, {"FEEDBACK_ADMIN_TOKEN": "secret"}, clear=False):
            response = client.get("/api/perf", headers={"X-Feedback-Admin-Token": "secret"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("perf", response.get_json())


if __name__ == "__main__":
    unittest.main()
