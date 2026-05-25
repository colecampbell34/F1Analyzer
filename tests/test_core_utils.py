import os
import unittest
from unittest.mock import patch, MagicMock

import pandas as pd
import numpy as np

import data
import ui_utils
import ai_cache
import callbacks_shared
import callbacks_ai
import callbacks_tabs
import telemetry_prep
import ux_helpers
import graphs
import graphs_pace
import graphs_race
import graphs_telemetry
import graphs_trackmap
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

    def test_figure_cache_key_changes_with_tab_inputs(self):
        params = {
            "year": 2025,
            "race": "British Grand Prix",
            "session_type": "Race",
            "driver1": "NOR",
            "driver2": "PIA",
        }

        base = callbacks_shared._figure_cache_key(params, "trackmap", "dominance")
        changed_mode = callbacks_shared._figure_cache_key(params, "trackmap", "speed")
        changed_driver = callbacks_shared._figure_cache_key({**params, "driver2": "VER"}, "trackmap", "dominance")

        self.assertNotEqual(base, changed_mode)
        self.assertNotEqual(base, changed_driver)


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


class TestGraphModules(unittest.TestCase):
    def test_graphs_module_preserves_public_import_surface(self):
        self.assertIs(graphs._build_telemetry_fig, graphs_telemetry._build_telemetry_fig)
        self.assertIs(graphs._build_dominance_fig, graphs_trackmap._build_dominance_fig)
        self.assertIs(graphs._build_race_gaps_fig, graphs_race._build_race_gaps_fig)
        self.assertIs(graphs._build_grid_pace_fig, graphs_pace._build_grid_pace_fig)


class TestAiLapContext(unittest.TestCase):
    def test_ai_context_header_includes_selected_laps(self):
        params = {
            "year": 2025,
            "race": "British Grand Prix",
            "session_type": "Race",
            "driver1": "NOR",
            "driver2": "PIA",
        }

        header = callbacks_ai._ai_context_header(params, 12, "fastest")
        context = f"{header}\n\nbody"

        self.assertIn("NOR=Lap 12", header)
        self.assertIn("PIA=fastest", header)
        self.assertTrue(callbacks_ai._ai_context_matches_params(context, params, 12, "fastest"))
        self.assertFalse(callbacks_ai._ai_context_matches_params(context, params, 13, "fastest"))

    def test_ai_callbacks_depend_on_lap_dropdowns(self):
        fake_app = TestLapSelection.FakeDashApp()
        callbacks_ai.register_ai_callbacks(fake_app)

        context_callback = next(
            callback for callback in fake_app.callbacks
            if getattr(callback["outputs"], "component_id", None) == "session-context-store"
        )
        context_input_ids = [dependency.component_id for dependency in context_callback["inputs"]]
        self.assertIn("d1-lap-dropdown", context_input_ids)
        self.assertIn("d2-lap-dropdown", context_input_ids)

        ask_callback = next(
            callback for callback in fake_app.callbacks
            if isinstance(callback["outputs"], (list, tuple))
            and any(output.component_id == "ai-history-store" for output in callback["outputs"])
            and any(output.component_id == "ai-question-input" for output in callback["outputs"])
        )
        ask_state_ids = [dependency.component_id for dependency in ask_callback["args"][0]]
        self.assertIn("d1-lap-dropdown", ask_state_ids)
        self.assertIn("d2-lap-dropdown", ask_state_ids)


class TestLapSelection(unittest.TestCase):
    class FakeDashApp:
        def __init__(self):
            self.callbacks = []

        def callback(self, outputs, inputs, *callback_args, **callback_kwargs):
            def decorator(func):
                self.callbacks.append({
                    "outputs": outputs,
                    "inputs": inputs,
                    "args": callback_args,
                    "kwargs": callback_kwargs,
                    "func": func,
                })
                return func
            return decorator

        def clientside_callback(self, *_args, **_kwargs):
            return None

    def test_specific_missing_lap_raises_clear_error(self):
        class Laps:
            def pick_drivers(self, driver):
                return pd.DataFrame({"Driver": [driver, driver], "LapNumber": [1, 3]})

        session = MagicMock()
        session.laps = Laps()

        with self.assertRaisesRegex(ValueError, "VER lap 2 is not available"):
            callbacks_shared._pick_driver_lap(session, "VER", "specific", 2, lambda *_: None)

    def test_lap_dropdown_to_mode_normalizes_fastest_and_specific(self):
        self.assertEqual(callbacks_shared._lap_dropdown_to_mode("fastest"), ("fastest", None))
        self.assertEqual(callbacks_shared._lap_dropdown_to_mode(None), ("fastest", None))
        self.assertEqual(callbacks_shared._lap_dropdown_to_mode(12), ("specific", 12))
        self.assertEqual(callbacks_shared._lap_dropdown_to_mode("12"), ("specific", 12))

    def test_trackmap_lap_summary_reflects_selected_laps(self):
        fake_app = self.FakeDashApp()
        callbacks_tabs.register_tab_callbacks(fake_app)

        summary_callback = next(
            callback for callback in fake_app.callbacks
            if getattr(callback["outputs"], "component_id", None) == "trackmap-lap-summary"
        )
        params = {
            "year": 2025,
            "race": "British Grand Prix",
            "session_type": "Race",
            "driver1": "NOR",
            "driver2": "PIA",
        }

        self.assertEqual(
            summary_callback["func"](params, 12, "fastest"),
            "Laps: NOR Lap 12 vs PIA fastest",
        )

    def test_trackmap_callback_uses_selected_lap_dropdowns(self):
        fake_app = self.FakeDashApp()
        callbacks_tabs.register_tab_callbacks(fake_app)

        def _outputs(callback):
            outputs = callback["outputs"]
            return outputs if isinstance(outputs, (list, tuple)) else [outputs]

        trackmap_callback = next(
            callback for callback in fake_app.callbacks
            if any(output.component_id == "2d-dominance-graph" for output in _outputs(callback))
        )
        input_ids = [dependency.component_id for dependency in trackmap_callback["inputs"]]

        self.assertIn("d1-lap-dropdown", input_ids)
        self.assertIn("d2-lap-dropdown", input_ids)

        params = {
            "year": 2025,
            "race": "British Grand Prix",
            "session_type": "Race",
            "driver1": "NOR",
            "driver2": "PIA",
        }
        lap1 = pd.Series({"LapTime": pd.Timedelta(seconds=90)})
        lap2 = pd.Series({"LapTime": pd.Timedelta(seconds=91)})
        comparison = {
            "session": MagicMock(),
            "d1": "NOR",
            "d2": "PIA",
            "lbl1": "NOR",
            "lbl2": "PIA",
            "c1": "#f47600",
            "c2": "#f47600",
            "lap1": lap1,
            "lap2": lap2,
            "tel1": pd.DataFrame(),
            "tel2": pd.DataFrame(),
        }

        with (
            patch.object(callbacks_tabs, "_active_tab_ready", return_value=True),
            patch("telemetry_prep.prepare_selected_lap_comparison", return_value=comparison) as prep,
            patch("graph_shared._sort_fastest_driver", return_value=("fast", "slow")),
            patch("graphs._build_driver_radar", return_value=({"data": [], "layout": {}}, [])),
            patch("graphs._build_dominance_fig", return_value={"data": [], "layout": {}}),
        ):
            figure, _dna_ui, cache_key = trackmap_callback["func"](
                params, "tab-trackmap", 12, 13, "braking", 0, {}, None
            )

        prep.assert_called_once_with(params, "specific", "specific", 12, 13)
        self.assertEqual(figure, {"data": [], "layout": {}})
        self.assertIn("12", cache_key)
        self.assertIn("13", cache_key)


class TestTelemetryPrepCache(unittest.TestCase):
    def setUp(self):
        telemetry_prep._prepare_selected_lap_comparison_cached.cache_clear()

    def tearDown(self):
        telemetry_prep._prepare_selected_lap_comparison_cached.cache_clear()

    def test_selected_lap_cache_reuses_telemetry_and_returns_copies(self):
        params = {
            "year": 2025,
            "race": "British Grand Prix",
            "session_type": "Race",
            "driver1": "NOR",
            "driver2": "PIA",
        }
        session = MagicMock()
        lap1 = pd.Series({"LapTime": pd.Timedelta(seconds=90)})
        lap2 = pd.Series({"LapTime": pd.Timedelta(seconds=91)})

        def fake_telemetry(lap, drop_xy_time=False, session=None):
            x_values = [np.nan, 1.0, 2.0] if lap is lap1 else [0.0, 1.0, 2.0]
            return pd.DataFrame({
                "Distance": [0.0, 10.0, 20.0],
                "Time": pd.to_timedelta([0, 1, 2], unit="s"),
                "X": x_values,
                "Y": [0.0, 1.0, 2.0],
                "Speed": [100.0, 110.0, 120.0],
            })

        with (
            patch.object(
                telemetry_prep,
                "get_shared_data",
                return_value=(session, "NOR", "PIA", "NOR", "PIA", "#f47600", "#f47600"),
            ) as shared,
            patch.object(telemetry_prep, "_pick_driver_lap", side_effect=[lap1, lap2]) as picker,
            patch.object(telemetry_prep, "_telemetry_with_distance", side_effect=fake_telemetry) as telemetry,
        ):
            first = telemetry_prep.prepare_selected_lap_comparison(params)
            first["tel1"].loc[0, "Distance"] = 999.0

            dropped = telemetry_prep.prepare_selected_lap_comparison(params, drop_xy_time=True)
            again = telemetry_prep.prepare_selected_lap_comparison(params)

        self.assertEqual(shared.call_count, 1)
        self.assertEqual(picker.call_count, 2)
        self.assertEqual(telemetry.call_count, 2)
        self.assertEqual(again["tel1"].loc[0, "Distance"], 0.0)
        self.assertEqual(dropped["tel1"]["Distance"].tolist(), [0.0, 10.0])


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


class TestPitStops(unittest.TestCase):
    def test_pit_driver_id_maps_to_session_abbreviation(self):
        session = MagicMock()
        session.results = pd.DataFrame([
            {
                "Abbreviation": "VER",
                "FirstName": "Max",
                "LastName": "Verstappen",
                "FullName": "Max Verstappen",
            }
        ])

        code = graphs._resolve_pit_driver_code({"driverId": "max_verstappen", "driverCode": None}, session)

        self.assertEqual(code, "VER")

    def test_pit_stop_fallback_excludes_transits_without_tyre_stop(self):
        class PickableLaps(pd.DataFrame):
            @property
            def _constructor(self):
                return PickableLaps

            def pick_drivers(self, driver):
                return PickableLaps(self[self["Driver"] == driver])

        session = MagicMock()
        session.name = "Sprint"
        session.results = pd.DataFrame([
            {"Abbreviation": "VER", "TeamName": "Red Bull", "TeamColor": "4781D7"},
            {"Abbreviation": "PER", "TeamName": "Red Bull", "TeamColor": "4781D7"},
        ])
        session.laps = PickableLaps([
            {
                "Driver": "VER",
                "LapNumber": 10,
                "PitInTime": pd.Timedelta(seconds=600),
                "PitOutTime": pd.NaT,
                "Stint": 1,
                "Compound": "MEDIUM",
                "FreshTyre": False,
            },
            {
                "Driver": "VER",
                "LapNumber": 11,
                "PitInTime": pd.NaT,
                "PitOutTime": pd.Timedelta(seconds=625),
                "Stint": 2,
                "Compound": "HARD",
                "FreshTyre": True,
            },
            {
                "Driver": "PER",
                "LapNumber": 5,
                "PitInTime": pd.Timedelta(seconds=300),
                "PitOutTime": pd.NaT,
                "Stint": 1,
                "Compound": "MEDIUM",
                "FreshTyre": False,
            },
            {
                "Driver": "PER",
                "LapNumber": 6,
                "PitInTime": pd.NaT,
                "PitOutTime": pd.Timedelta(seconds=323),
                "Stint": 1,
                "Compound": "MEDIUM",
                "FreshTyre": False,
            },
        ])

        fig = graphs._build_pit_stops_fig(session, "VER", "PER", "VER", "PER", "#4781D7", "#4781D7")

        self.assertEqual(list(fig.data[0].x), ["VER L10"])


class TestLatestRaceDefault(unittest.TestCase):
    def test_latest_race_default_uses_latest_past_race(self):
        expected = {
            "year": 2025,
            "race": "Latest Grand Prix",
            "session_type": "Race",
        }
        with patch.object(data, "get_latest_static_race_session", return_value=expected):
            latest = data.get_latest_race_session_default(now="2025-07-01T00:00:00Z")

        self.assertEqual(latest, expected)


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

    def test_vercel_uses_direct_load_instead_of_background_preload(self):
        params = {
            "year": 2025,
            "race": "British Grand Prix",
            "session_type": "Race",
        }
        with patch.dict(os.environ, {"VERCEL": "1"}, clear=False):
            with patch.object(data._SESSION_PRELOAD_EXECUTOR, "submit") as submit:
                future = data.preload_session(2025, "British Grand Prix", "Race", telemetry=True)
                status = data.ensure_preload_for_tab(params, "tab-telemetry")

        self.assertIsNone(future)
        submit.assert_not_called()
        self.assertEqual(status["status"], "direct")
        self.assertEqual(status["profile"], "telemetry")

    def test_load_session_with_preload_does_not_duplicate_started_preload(self):
        with patch.object(data, "_load_session_granular_cached", return_value="session") as loader:
            first = data.load_session_with_preload(
                2025, "British Grand Prix", "Race", telemetry=True
            )
            second = data.load_session_with_preload(
                2025, "British Grand Prix", "Race", telemetry=True
            )

        self.assertEqual(first, "session")
        self.assertEqual(second, "session")
        self.assertEqual(loader.call_count, 1)

    def test_load_session_with_preload_retries_failed_preload_future(self):
        from concurrent.futures import Future

        key = data._session_preload_key(
            2025, "British Grand Prix", "Race", True, True, False, False
        )
        failed_future = Future()
        failed_future.set_exception(RuntimeError("previous failure"))
        with data._SESSION_PRELOAD_LOCK:
            data._SESSION_PRELOAD_FUTURES[key] = failed_future

        with patch.object(data, "_load_session_granular_cached", return_value="session") as loader:
            result = data.load_session_with_preload(
                2025, "British Grand Prix", "Race", telemetry=True
            )

        self.assertEqual(result, "session")
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


class TestGridPaceFiltering(unittest.TestCase):
    def test_string_false_rainfall_still_counts_as_dry(self):
        weather = pd.DataFrame({"Rainfall": ["False", "0", False, np.nan]})
        self.assertTrue(graphs._is_dry_session_from_weather(weather))

    def test_dry_107_filter_removes_major_outliers(self):
        lap_times = pd.Series([80.0, 82.0, 86.0, 95.0])
        filtered = graphs._filter_lap_times_107(lap_times, 80.0, enabled=True)
        self.assertEqual(filtered.tolist(), [80.0, 82.0])

    def test_wet_session_keeps_laps_outside_107_percent(self):
        lap_times = pd.Series([80.0, 95.0])
        filtered = graphs._filter_lap_times_107(lap_times, 80.0, enabled=False)
        self.assertEqual(filtered.tolist(), [80.0, 95.0])

    def test_clean_pace_laps_drops_inaccurate_laps_before_filtering(self):
        laps = pd.DataFrame({
            "LapTime": pd.to_timedelta([80, 81, 82], unit="s"),
            "IsAccurate": [True, "False", np.nan],
        })
        clean = graphs._clean_pace_laps(laps)
        self.assertEqual(clean["LapTime"].dt.total_seconds().tolist(), [80.0])


class TestApiValidation(unittest.TestCase):
    def test_css_assets_revalidate_after_deploy(self):
        import app as app_module
        client = app_module.server.test_client()

        response = client.get("/assets/custom.css")
        try:
            self.assertEqual(response.headers.get("Cache-Control"), "no-cache, max-age=0, must-revalidate")
        finally:
            response.close()

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
