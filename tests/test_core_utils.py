import os
import unittest
from unittest.mock import patch, MagicMock

import pandas as pd

import data
import ui_utils
import ai_cache
import callbacks_shared
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

    def test_invalid_url_view_state_is_ignored(self):
        parsed = callbacks_shared._parse_url_state("?tab=bad&d1_lap_mode=bad&d1_lap=-2&trackmap=bad")
        self.assertIsNone(parsed["tab"])
        self.assertIsNone(parsed["d1_lap_mode"])
        self.assertIsNone(parsed["d1_lap"])
        self.assertIsNone(parsed["trackmap_mode"])


class TestLapSelection(unittest.TestCase):
    def test_specific_missing_lap_raises_clear_error(self):
        class Laps:
            def pick_drivers(self, driver):
                return pd.DataFrame({"Driver": [driver, driver], "LapNumber": [1, 3]})

        session = MagicMock()
        session.laps = Laps()

        with self.assertRaisesRegex(ValueError, "VER lap 2 is not available"):
            callbacks_shared._pick_driver_lap(session, "VER", "specific", 2, lambda *_: None)


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


if __name__ == "__main__":
    unittest.main()
