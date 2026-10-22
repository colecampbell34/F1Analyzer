"""Behavior tests for the normalized provider facade and dashboard consumers."""
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

import ai_cache
import ai_utils
import app
import callbacks
import callbacks_shared
import callbacks_tabs
import data
import graphs
import graphs_pace
import graphs_race
import session_data
import shared_cache
import strategy_insights
import telemetry_dynamics
import telemetry_prep
import ui_utils
import runtime


FIXTURES = Path(__file__).parent / "fixtures" / "openf1"


def _bundle():
    raw = json.loads((FIXTURES / "2023_monaco_race.json").read_text(encoding="utf-8"))
    info = raw["session"]
    ref = session_data.SessionRef(
        year=info["year"], round=info["round"], event_name=info["event_name"],
        country_name="Monaco", session_name=info["session_name"],
        session_type=info["session_type"], session_key=info["session_key"],
        meeting_key=info["meeting_key"], date_start=info["date_start"],
        date_end=info["date_end"], circuit_info_url=info["circuit_info_url"],
    )
    drivers = session_data.normalize_drivers(raw["drivers"])
    stints = session_data.normalize_stints(raw["stints"], drivers)
    pits = session_data.normalize_pits(raw["pit"], drivers)
    additional_laps = [
        {"driver_number": 1, "lap_number": 3, "date_start": "2023-05-28T13:07:00Z", "lap_duration": 78.0, "duration_sector_1": 22.0, "duration_sector_2": 32.0, "duration_sector_3": 24.0},
        {"driver_number": 1, "lap_number": 4, "date_start": "2023-05-28T13:08:18Z", "lap_duration": 79.0, "duration_sector_1": 22.1, "duration_sector_2": 32.5, "duration_sector_3": 24.4},
        {"driver_number": 14, "lap_number": 3, "date_start": "2023-05-28T13:07:01Z", "lap_duration": 78.9, "duration_sector_1": 22.1, "duration_sector_2": 32.4, "duration_sector_3": 24.4},
        {"driver_number": 14, "lap_number": 4, "date_start": "2023-05-28T13:08:20Z", "lap_duration": 79.6, "duration_sector_1": 22.2, "duration_sector_2": 32.8, "duration_sector_3": 24.6},
    ]
    laps = session_data.normalize_laps(raw["laps"] + additional_laps, drivers, stints, pits)
    results = session_data.normalize_results(raw["session_result"], drivers, "Race")
    grid = session_data.normalize_grid(raw["starting_grid"], drivers)
    if not results.empty and not grid.empty:
        results["grid_position"] = results["driver_number"].map(dict(zip(grid.driver_number, grid.grid_position)))
    weather = session_data._normalize_weather(raw["weather"])
    messages = session_data._normalize_messages(raw["race_control"])
    positions = session_data._normalize_timed_position(raw["position"], "position")
    intervals = session_data._normalize_timed_position(raw["intervals"], "intervals")
    laps = session_data._attach_lap_context(laps, positions, intervals, messages)
    return session_data.SessionBundle(
        ref=ref, drivers=drivers, results=results, grid=grid, laps=laps,
        stints=stints, pits=pits, weather=weather, messages=messages,
        positions=positions, intervals=intervals,
        quality={
            "provider": "OpenF1", "notes": [], "endpoints": {
                name: {"state": "available", "source": f"openf1.{name}"}
                for name in ("drivers", "session_result", "starting_grid", "laps", "stints", "pit", "weather", "race_control")
            },
        },
    )


class TestUrlAndRuntimeContracts(unittest.TestCase):
    def test_url_round_trip_preserves_session_view_and_laps(self):
        params = {"year": 2023, "race": "Monaco Grand Prix", "session_type": "Race", "driver1": "VER", "driver2": "ALO"}
        search = callbacks_shared._build_url_search(params, "tab-telemetry", {
            "d1_lap_mode": "specific", "d1_lap": 12, "trackmap_mode": "speed",
        })
        state = callbacks_shared._parse_url_state(search)
        self.assertEqual(state["year"], 2023)
        self.assertEqual(state["driver1"], "VER")
        self.assertEqual(state["d1_lap"], 12)
        self.assertEqual(state["tab"], "tab-telemetry")

    def test_figure_cache_key_changes_with_selected_lap(self):
        params = {"year": 2023, "race": "Monaco Grand Prix", "session_type": "Race", "driver1": "VER", "driver2": "ALO"}
        one = callbacks_shared._figure_cache_key(params, "telemetry", 1, 2)
        two = callbacks_shared._figure_cache_key(params, "telemetry", 1, 3)
        self.assertNotEqual(one, two)

    def test_varying_local_and_serverless_runtime_directory(self):
        with patch.dict("os.environ", {"VERCEL": "1"}, clear=False):
            self.assertEqual(runtime.runtime_directory("F1_TEST_CACHE", "test-cache"), "/tmp/test-cache")
        with patch.dict("os.environ", {"VERCEL": "", "F1_TEST_CACHE": "custom"}, clear=False):
            self.assertEqual(runtime.runtime_directory("F1_TEST_CACHE", "test-cache"), "custom")

    def test_flask_health_and_static_cache_headers(self):
        client = app.server.test_client()
        health = client.get("/healthz")
        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.get_json()["status"], "ok")
        response = client.get("/assets/custom.css")
        self.assertIn("must-revalidate", response.headers.get("Cache-Control", ""))
        response.close()

    def test_schedule_and_latest_race_helpers_use_supported_completed_sessions(self):
        data.get_event_schedule_cached.cache_clear()
        schedule = [{
            "year": 2024, "race": "Example Grand Prix", "round": 3,
            "sessions": ["Practice 1", "Qualifying", "Race"],
        }]
        with patch.object(data, "_get_schedule", return_value=schedule):
            self.assertEqual(data.get_event_schedule(2024)[0]["race"], "Example Grand Prix")
        with patch.object(data, "latest_completed_race", return_value=None):
            self.assertIsNone(data.get_latest_race_session_default())
        with patch.object(data, "latest_completed_race", return_value={"year": 2022, "race": "Old Grand Prix"}):
            self.assertIsNone(data.get_latest_race_session_default())

    def test_selection_callbacks_choose_schedule_url_latest_and_driver_values(self):
        race_callback = app.dash_app.callback_map["..race-dropdown.options...race-dropdown.value.."]["callback"].__wrapped__
        session_callback = app.dash_app.callback_map["..session-dropdown.options...session-dropdown.value.."]["callback"].__wrapped__
        driver_callback = app.dash_app.callback_map[
            "..driver1-dropdown.options...driver1-dropdown.value...driver2-dropdown.options...driver2-dropdown.value.."
        ]["callback"].__wrapped__
        schedule = [{"race": "Monaco Grand Prix", "sessions": ["Practice 1", "Qualifying", "Race"]}]
        with patch.object(data, "get_event_schedule", return_value=schedule):
            race_options, race_value = race_callback(2023, None, "?year=2023&race=Monaco+Grand+Prix", "Silverstone")
            session_options, session_value = session_callback(
                "Monaco Grand Prix", None, 2023,
                "?year=2023&race=Monaco+Grand+Prix&session=Qualifying", "Race",
            )
            latest_options, latest_session = session_callback(
                "Monaco Grand Prix",
                {"year": 2023, "race": "Monaco Grand Prix", "session_type": "Race"},
                2023, "?session=Qualifying", None,
            )
        self.assertEqual(race_value, "Monaco Grand Prix")
        self.assertEqual([item["value"] for item in race_options], ["Monaco Grand Prix"])
        self.assertEqual(session_value, "Qualifying")
        self.assertEqual(latest_session, "Race")
        self.assertEqual([item["value"] for item in latest_options], ["Practice 1", "Qualifying", "Race"])
        with patch.object(data, "get_event_schedule", side_effect=RuntimeError("upstream body")):
            self.assertEqual(race_callback(2023, None, "", None), ([], None))

        driver_info = (
            {"abbr": "VER", "name": "Max Verstappen", "team": "Red Bull", "color": "#3671C6", "driver_number": "1"},
            {"abbr": "NOR", "name": "Lando Norris", "team": "McLaren", "color": "#F47600", "driver_number": "4"},
        )
        with patch.object(data, "_load_drivers_fast", return_value=driver_info):
            options, d1, _options2, d2 = driver_callback(
                "Race", 2023, "Monaco Grand Prix",
                "?year=2023&race=Monaco+Grand+Prix&session=Race&driver1=NOR&driver2=VER",
                "VER", "NOR",
            )
        self.assertEqual([item["value"] for item in options], ["VER", "NOR"])
        self.assertEqual((d1, d2), ("NOR", "VER"))
        with patch.object(data, "_load_drivers_fast", return_value=()):
            self.assertEqual(driver_callback("Race", 2023, "Monaco Grand Prix", "", None, None), ([], None, [], None))

    def test_dashboard_load_callback_uses_complete_url_while_controls_hydrate(self):
        key = next(
            key for key in app.dash_app.callback_map
            if "dashboard-params-store.data" in key and "error-dialog.displayed" in key
        )
        callback = app.dash_app.callback_map[key]["callback"].__wrapped__
        search = "?year=2023&race=Monaco+Grand+Prix&session=Race&driver1=VER&driver2=ALO&tab=tab-telemetry"
        with patch.object(data, "get_preload_kwargs_for_tab", return_value={}), \
             patch.object(data, "preload_session") as preload:
            result = callback(1, 0, None, None, None, None, None, "tab-racepace", search)

        self.assertEqual(
            result,
            ({
                "year": 2023, "race": "Monaco Grand Prix", "session_type": "Race",
                "driver1": "VER", "driver2": "ALO",
            }, False, ""),
        )
        preload.assert_called_once_with(2023, "Monaco Grand Prix", "Race")

    def test_session_summary_api_returns_canonical_fields_and_sanitizes_errors(self):
        bundle = _bundle()
        with patch.object(data, "load_session_summary", return_value=bundle):
            response = app.server.test_client().get(
                "/api/session-summary?year=2023&race=Monaco%20Grand%20Prix&session=Race"
            )
        self.assertEqual(response.status_code, 200)
        result = response.get_json()["results"][0]
        self.assertEqual(result["abbr"], "VER")
        self.assertEqual(result["position"], 1)
        self.assertTrue(result["source"].startswith("openf1."))

        with patch.object(data, "load_session_summary", side_effect=RuntimeError("secret response body")):
            failure = app.server.test_client().get(
                "/api/session-summary?year=2023&race=Monaco&session=Race"
            )
        self.assertEqual(failure.status_code, 502)
        self.assertNotIn("secret response body", failure.get_data(as_text=True))


class TestNormalizedDashboardWorkflows(unittest.TestCase):
    def test_loaded_selection_match_checks_every_sidebar_field(self):
        loaded = {
            "year": 2026,
            "race": "Spanish Grand Prix",
            "session_type": "Qualifying",
            "driver1": "HAM",
            "driver2": "RUS",
        }
        selection = (2026, "Spanish Grand Prix", "Qualifying", "HAM", "RUS")
        self.assertTrue(callbacks._loaded_selection_matches(loaded, *selection))
        self.assertFalse(callbacks._loaded_selection_matches(None, *selection))
        for index in range(len(selection)):
            changed = list(selection)
            changed[index] = "different"
            self.assertFalse(callbacks._loaded_selection_matches(loaded, *changed))

    def test_selection_warning_is_hidden_only_for_the_loaded_selection(self):
        key = next(
            key for key in app.dash_app.callback_map
            if "selection-dirty-warning.children" in key
        )
        callback = app.dash_app.callback_map[key]["callback"].__wrapped__
        loaded = {
            "year": 2026,
            "race": "Spanish Grand Prix",
            "session_type": "Qualifying",
            "driver1": "HAM",
            "driver2": "RUS",
        }
        selection = (2026, "Spanish Grand Prix", "Qualifying", "HAM", "RUS")
        self.assertEqual(callback(None, *selection), ("", {"display": "none"}))
        self.assertEqual(callback(loaded, *selection), ("", {"display": "none"}))
        warning, style = callback(loaded, 2026, "Monaco Grand Prix", "Qualifying", "HAM", "RUS")
        self.assertIn("Click Load analysis", warning)
        self.assertEqual(style, {})

    def test_telemetry_graph_aligns_delta_and_channels_on_reference_distance(self):
        progress = np.linspace(0.0, 1.0, 12)

        def trace(distance_span, duration):
            return pd.DataFrame({
                "Distance": progress * distance_span,
                "Time": pd.to_timedelta(progress * duration, unit="s"),
                "Speed": np.linspace(100.0, 300.0, len(progress)),
                "Throttle": np.linspace(10.0, 90.0, len(progress)),
                "Brake": np.zeros(len(progress)),
                "nGear": np.ones(len(progress)),
            })

        faster = trace(4000.0, 74.679)
        slower = trace(4200.0, 74.743)
        fast_data = ("RUS", faster, "#3671C6", 74.679, {"lap_duration": 74.679}, "RUS")
        slow_data = ("HAM", slower, "#e8002d", 74.743, {"lap_duration": 74.743}, "HAM")
        figure = graphs._build_telemetry_fig(
            fast_data,
            slow_data,
            ("HAM", {"lap_duration": 74.743}),
            ("RUS", {"lap_duration": 74.679}),
        )

        speed_traces = [item for item in figure.data if item.name.endswith(" Speed")]
        self.assertEqual(len(speed_traces), 2)
        np.testing.assert_allclose(speed_traces[0].x, speed_traces[1].x)
        self.assertAlmostEqual(float(speed_traces[0].x[0]), 0.0)
        self.assertAlmostEqual(float(speed_traces[0].x[-1]), 4000.0)
        self.assertEqual(figure.layout.xaxis4.title.text, "Derived distance (m)")
        for axis_name in ("xaxis", "xaxis2", "xaxis3", "xaxis4"):
            axis = getattr(figure.layout, axis_name)
            self.assertEqual(list(axis.range), [0, 4000])
            self.assertFalse(axis.autorange)
        delta_traces = [item for item in figure.data if item.name in ("HAM ahead", "HAM behind")]
        delta_x = np.concatenate([np.asarray(item.x, dtype=float) for item in delta_traces])
        self.assertAlmostEqual(float(np.nanmin(delta_x)), 0.0)
        self.assertAlmostEqual(float(np.nanmax(delta_x)), 4000.0)
        ham_behind = next(item for item in figure.data if item.name == "HAM behind")
        self.assertLess(float(np.nanmin(ham_behind.y)), 0.0)
        self.assertTrue(all(
            np.sign(float(value)) == np.sign(float(label))
            for value, label in zip(figure.layout.yaxis.tickvals, figure.layout.yaxis.ticktext)
        ))

    def test_provider_fixture_builds_driver_result_stint_and_pit_context(self):
        bundle = _bundle()
        bundle.stints = pd.DataFrame([
            {"abbreviation": "VER", "stint_number": 1, "lap_start": 1, "lap_end": 20, "compound": "MEDIUM"},
            {"abbreviation": "VER", "stint_number": 2, "lap_start": 21, "lap_end": 78, "compound": "HARD"},
        ])
        bundle.pits = pd.DataFrame([{"abbreviation": "VER", "lap_number": 20}])
        driver_info = data.get_driver_info(bundle)
        self.assertEqual([driver["abbr"] for driver in driver_info[:2]], ["VER", "ALO"])
        self.assertEqual(data.get_teammate_from_info("VER", driver_info), None)
        self.assertEqual(data.get_best_lap(bundle, "VER")["lap_number"], 3)
        self.assertEqual(strategy_insights.build_driver_stints(bundle, "VER")[0]["compound"], "MEDIUM")
        pit = strategy_insights.build_driver_pit_impacts(bundle, "VER")[0]
        self.assertEqual(pit["source"], "openf1.stints")
        self.assertEqual(pit["to_compound"], "HARD")

    def test_fixture_backed_graphs_return_figures_with_sparse_laps(self):
        bundle = _bundle()
        extra_laps = []
        for driver_number, abbreviation in ((1, "VER"), (14, "ALO")):
            for lap_number in range(5, 11):
                extra_laps.append({
                    "driver_number": driver_number, "abbreviation": abbreviation,
                    "lap_number": lap_number, "lap_duration": 78.0 + lap_number / 10,
                    "stint_number": 1, "compound": "MEDIUM",
                })
        bundle.laps = pd.concat([bundle.laps, pd.DataFrame(extra_laps)], ignore_index=True)
        strategy = graphs._build_strategy_fig(bundle, "VER", "ALO", "VER", "ALO", "#3671C6", "#358C75")
        degradation = graphs._build_deg_fig(bundle, "VER", "ALO", "VER", "ALO", "#3671C6", "#358C75")
        race_gap = graphs._build_race_gaps_fig(bundle, "VER", "ALO", "VER", "ALO", "#3671C6", "#358C75")
        pace = graphs._build_grid_pace_fig(bundle, "Race")
        self.assertTrue(strategy.data)
        self.assertTrue(degradation.data)
        self.assertTrue(race_gap.data)
        self.assertTrue(pace.data or pace.layout.annotations)
        self.assertTrue({"SC", "VSC", "Red flag"}.issubset({trace.name for trace in strategy.data}))
        self.assertTrue({"SC", "VSC", "Red flag"}.issubset({trace.name for trace in race_gap.data}))

    def test_strategy_calls_follow_displayed_stints_including_same_compound_stop(self):
        bundle = _bundle()
        bundle.stints = pd.DataFrame([
            {"abbreviation": "VER", "stint_number": 1, "lap_start": 1, "lap_end": 11, "compound": "SOFT"},
            {"abbreviation": "VER", "stint_number": 2, "lap_start": 12, "lap_end": 27, "compound": "HARD"},
            {"abbreviation": "VER", "stint_number": 3, "lap_start": 28, "lap_end": 41, "compound": "MEDIUM"},
            {"abbreviation": "VER", "stint_number": 4, "lap_start": 42, "lap_end": 60, "compound": "HARD"},
            {"abbreviation": "VER", "stint_number": 5, "lap_start": 61, "lap_end": 66, "compound": "HARD"},
        ])
        bundle.pits = pd.DataFrame([
            {"abbreviation": "VER", "lap_number": 2},
            {"abbreviation": "VER", "lap_number": 27},
            {"abbreviation": "VER", "lap_number": 41},
            {"abbreviation": "VER", "lap_number": 60},
        ])
        bundle.laps = pd.DataFrame([
            {"abbreviation": "VER", "lap_number": lap, "position": 3}
            for lap in range(1, 68)
        ])

        impacts = strategy_insights.build_driver_pit_impacts(bundle, "VER")
        self.assertEqual([event["pit_lap"] for event in impacts], [11, 27, 41, 60])
        self.assertEqual(
            [(event["from_compound"], event["to_compound"]) for event in impacts],
            [("SOFT", "HARD"), ("HARD", "MEDIUM"), ("MEDIUM", "HARD"), ("HARD", "HARD")],
        )
        self.assertTrue(all(event["source"] == "openf1.stints" for event in impacts))

        overview = callbacks_tabs._render_stint_overview([
            ("VER", strategy_insights.build_driver_stints(bundle, "VER")),
        ])
        bar = overview.children[1].children[0].children[1]
        markers = [child for child in bar.children if child.className == "stint-pit-marker"]
        self.assertEqual(len(markers), 4)
        labels = [child.children for child in bar.children if child.className == "stint-bar-segment"]
        self.assertEqual(labels, ["SOFT 1–11", "HARD 12–27", "MEDIUM 28–41", "HARD 42–60", "HARD 61–66"])

    def test_pace_excludes_known_pit_and_out_laps_and_race_gap_labels_lapped_strings(self):
        laps = pd.DataFrame({
            "lap_duration": [80.0, 81.0, 79.5, 82.0],
            "is_pit_out_lap": [False, True, False, False],
            "pit_in": [False, False, True, False],
        })
        self.assertEqual(graphs_pace._clean_pace_laps(laps)["lap_duration"].tolist(), [80.0, 82.0])
        bundle = _bundle()
        bundle.laps.loc[bundle.laps["abbreviation"] == "VER", "gap_to_leader"] = "+1 LAP"
        gap = graphs_race._build_race_gaps_fig(bundle, "VER", "ALO", "VER", "ALO", "#3671C6", "#358C75")
        self.assertIn("Derived cumulative lap-time gap", gap.layout.title.text)

    def test_race_control_status_intervals_use_explicit_deployments_without_yellow_shading(self):
        bundle = _bundle()
        starts = pd.date_range("2023-05-28T13:00:00Z", periods=9, freq="min")
        bundle.laps = pd.DataFrame({
            "abbreviation": ["VER"] * 9,
            "lap_number": range(1, 10), "date_start": starts,
            "lap_duration": [60.0] * 9, "stint_number": [1] * 9,
            "compound": ["MEDIUM"] * 9, "pit_in": [False] * 9,
        })
        bundle.messages = session_data._normalize_messages([
            {"date": "2023-05-28T13:00:30Z", "category": "SafetyCar", "lap_number": 1, "message": "VSC DEPLOYED"},
            {"date": "2023-05-28T13:01:30Z", "category": "SafetyCar", "lap_number": 2, "message": "VSC ENDING"},
            {"date": "2023-05-28T13:02:10Z", "category": "Other", "lap_number": 3, "message": "INCIDENT DURING VSC"},
            {"date": "2023-05-28T13:03:10Z", "category": "SafetyCar", "lap_number": 4, "message": "VSC DEPLOYED"},
            {"date": "2023-05-28T13:03:20Z", "category": "SafetyCar", "lap_number": 4, "message": "VSC ENDING"},
            {"date": "2023-05-28T13:04:30Z", "category": "SafetyCar", "lap_number": 5, "message": "SAFETY CAR DEPLOYED"},
            {"date": "2023-05-28T13:04:45Z", "category": "SafetyCar", "lap_number": 5, "message": "VSC DEPLOYED"},
            {"date": "2023-05-28T13:05:00Z", "category": "SafetyCar", "lap_number": 5, "message": "VSC ENDING"},
            {"date": "2023-05-28T13:05:30Z", "category": "SafetyCar", "lap_number": 6, "message": "SAFETY CAR IN THIS LAP"},
            {"date": "2023-05-28T13:06:30Z", "category": "Flag", "flag": "RED", "lap_number": 7, "message": "RED FLAG"},
            {"date": "2023-05-28T13:07:30Z", "category": "Flag", "lap_number": 8, "message": "SESSION RESUMED"},
            {"date": "2023-05-28T13:08:10Z", "category": "Flag", "flag": "DOUBLE YELLOW", "scope": "Sector", "lap_number": 9, "message": "DOUBLE YELLOW IN SECTOR 2"},
        ])
        safety, vsc, red, yellow = data.get_track_status_events(bundle)
        self.assertEqual(safety, {5})
        self.assertEqual(vsc, {1, 4})
        self.assertEqual(red, {7})
        self.assertEqual(yellow, {9})
        strategy = graphs._build_strategy_fig(bundle, "VER", "ALO", "VER", "ALO", "#3671C6", "#358C75")
        status_regions = [
            shape for shape in strategy.layout.shapes
            if shape.fillcolor in {"orange", "yellow", "red"}
        ]
        self.assertEqual(len(status_regions), 4)

    def test_2026_barcelona_vsc_shading_uses_only_explicit_deployment_laps(self):
        bundle = _bundle()
        bundle.ref = session_data.SessionRef(
            year=2026, round=9, event_name="Barcelona Grand Prix",
            country_name="Spain", session_name="Race", session_type="Race",
            session_key=11307, meeting_key=1287,
        )
        race_start = pd.Timestamp("2026-06-14T13:00:00Z")
        rows = []
        for abbreviation, offset in (("VER", 0), ("ALO", 8)):
            for lap_number in range(1, 67):
                rows.append({
                    "abbreviation": abbreviation, "lap_number": lap_number,
                    "date_start": race_start + pd.Timedelta(seconds=offset + (lap_number - 1) * 82),
                    "lap_duration": 82.0, "stint_number": 1, "compound": "HARD",
                    "pit_in": False, "pit_out": False,
                })
        bundle.laps = pd.DataFrame(rows)
        bundle.messages = session_data._normalize_messages([
            {"date": "2026-06-14T13:59:03Z", "category": "SafetyCar", "lap_number": 41, "message": "VSC DEPLOYED"},
            {"date": "2026-06-14T14:01:20Z", "category": "SafetyCar", "lap_number": 42, "message": "VSC ENDING"},
            {"date": "2026-06-14T14:29:52Z", "category": "SafetyCar", "lap_number": 63, "message": "VSC DEPLOYED"},
            {"date": "2026-06-14T14:33:35Z", "category": "SafetyCar", "lap_number": 65, "message": "VSC ENDING"},
        ])

        safety, vsc, red, _yellow = data.get_track_status_events(bundle)
        self.assertEqual(safety, set())
        self.assertEqual(vsc, {41, 63})
        self.assertEqual(red, set())

        strategy = graphs._build_strategy_fig(bundle, "VER", "ALO", "VER", "ALO", "#3671C6", "#358C75")
        vsc_regions = [shape for shape in strategy.layout.shapes if shape.fillcolor == "yellow"]
        self.assertEqual([(shape.x0, shape.x1) for shape in vsc_regions], [(40.5, 41.5), (62.5, 63.5)])

    def test_public_data_facade_loads_fixture_backed_bundle(self):
        bundle = _bundle()
        data._load_bundle_cached.cache_clear()
        with patch.object(session_data, "resolve_session_ref", return_value=bundle.ref), patch.object(
            data, "load_session_bundle", return_value=bundle
        ):
            loaded = data.load_session_summary(2023, "Monaco Grand Prix", "Race", include_laps=True)
        self.assertEqual(loaded.ref.session_key, 9094)
        self.assertEqual([row["abbr"] for row in data.get_driver_info(loaded)], ["VER", "ALO"])

    def test_ai_context_retains_classification_grid_weather_and_provenance_without_trace(self):
        bundle = _bundle()
        context = ai_utils._gather_session_context(
            bundle, "Race", "VER", "ALO",
            selected_lap_context={"lap1": None, "lap2": None, "tel1": None, "tel2": None},
        )
        self.assertIn("FULL FIELD CLASSIFICATION", context)
        self.assertIn("STARTING GRID", context)
        self.assertIn("WEATHER SAMPLES", context)
        self.assertIn("do not infer", context.casefold())
        prompt = ai_utils.build_ai_prompt(context, "Compare what the data says about these drivers.")
        self.assertIn("Do not fill gaps from memory", prompt)

    def test_ai_context_keeps_lapped_result_and_fallback_provenance(self):
        bundle = _bundle()
        bundle.results["gap"] = bundle.results["gap"].astype(object)
        bundle.results.loc[bundle.results["abbreviation"] == "ALO", "gap"] = "+1 LAP"
        bundle.results.loc[bundle.results["abbreviation"] == "ALO", "source"] = "jolpica.results"
        context = ai_utils._gather_session_context(bundle, "Race", "VER", "ALO")
        self.assertIn("gap +1 LAP", context)
        self.assertIn("jolpica.results", context)

    def test_missing_optional_weather_messages_and_results_keep_bundle_usable(self):
        bundle = _bundle()
        bundle.weather = pd.DataFrame()
        bundle.messages = pd.DataFrame()
        bundle.results = pd.DataFrame(columns=bundle.results.columns)
        bundle.laps = pd.DataFrame(columns=bundle.laps.columns)
        context = ai_utils._gather_session_context(bundle, "Race", "VER", "ALO")
        self.assertIn("Classification unavailable", context)
        self.assertNotIn("WEATHER SAMPLES", context)
        self.assertIn("Lap timing is unavailable", context)

    def test_specific_lap_is_not_replaced_but_fastest_can_use_next_trace(self):
        bundle = _bundle()
        trace = pd.DataFrame({
            "Time": pd.to_timedelta(range(8), unit="s"), "Distance": np.arange(8) * 10.0,
            "Speed": np.arange(8) + 180.0,
        })

        def trace_for(_ref, lap, with_position=True):
            if int(lap["lap_number"]) == 3:
                raise session_data.ProviderError("missing", kind="empty", endpoint="car_data")
            return trace.copy()

        selected = bundle.laps[(bundle.laps["abbreviation"] == "VER") & (bundle.laps["lap_number"] == 3)].iloc[0]
        with patch.object(telemetry_prep, "get_selected_lap_trace", side_effect=trace_for):
            fallback_lap, _fallback_trace, used_fallback = telemetry_prep._selected_trace(bundle, "VER", selected, "fastest")
            self.assertEqual(fallback_lap["lap_number"], 1)
            self.assertTrue(used_fallback)
            with self.assertRaises(session_data.ProviderError):
                telemetry_prep._selected_trace(bundle, "VER", selected, "specific")

    def test_bundle_cache_returns_deep_frame_copies(self):
        bundle = _bundle()
        cloned = data._clone_bundle(bundle)
        cloned.laps.loc[0, "lap_duration"] = -1
        self.assertEqual(bundle.laps.loc[0, "lap_duration"], 78.5)

    def test_selected_trace_cache_wire_preserves_quality_and_drs_without_session_objects(self):
        trace = pd.DataFrame({
            "Time": pd.to_timedelta([0.0, 0.25, 0.5, 0.75, 1.0, 1.25], unit="s"),
            "Distance": [0, 10, 20, 30, 40, 50], "Speed": [180, 181, 183, 184, 185, 186],
            "DRS": [8, 8, 10, 10, 12, 12], "X": [1, 2, 3, 4, 5, 6], "Y": [6, 5, 4, 3, 2, 1],
        })
        trace.attrs["quality"] = {"source": "openf1.car_data", "distance_derived": True}
        payload = {
            "session": _bundle(), "d1": "VER", "d2": "ALO", "lbl1": "VER", "lbl2": "ALO",
            "c1": "#3671C6", "c2": "#358C75", "lap1": _bundle().laps.iloc[0],
            "lap2": _bundle().laps.iloc[2], "tel1": trace, "tel2": trace.copy(),
            "circuit_corners": [],
        }
        wire = telemetry_prep._payload_to_wire(payload)
        restored = telemetry_prep._payload_from_wire(wire)
        self.assertNotIn("session", wire)
        self.assertEqual(restored["tel1"]["DRS"].tolist(), [8, 8, 10, 10, 12, 12])
        self.assertTrue(restored["tel1"].attrs["quality"]["distance_derived"])

    def test_estimated_g_requires_position_samples(self):
        time = pd.to_timedelta(np.arange(20) * 0.25, unit="s")
        trace = pd.DataFrame({
            "Time": time, "Distance": np.arange(20) * 10.0,
            "Speed": np.linspace(100, 220, 20),
            "X": np.cos(np.arange(20) / 5) * 100,
            "Y": np.sin(np.arange(20) / 5) * 100,
        })
        self.assertEqual(len(telemetry_dynamics.calculate_g_series(trace)), 4)
        with self.assertRaisesRegex(ValueError, "position"):
            telemetry_dynamics.calculate_g_series(trace.drop(columns=["X", "Y"]))


class TestCacheAndErrors(unittest.TestCase):
    def test_ai_cache_key_normalizes_question(self):
        self.assertEqual(ai_cache._cache_key("ctx", " Hello  "), ai_cache._cache_key("ctx", "hello"))

    def test_shared_cache_json_encoder_round_trips_bounded_payload(self):
        payload = {"schema": 3, "drivers": ["VER", "ALO"], "values": [1.0, None]}
        self.assertEqual(shared_cache._decode(shared_cache._encode(payload)), payload)

    def test_provider_errors_map_to_safe_actionable_messages(self):
        err = session_data.ProviderError("private upstream response", kind="rate_limited")
        self.assertEqual(ui_utils._friendly_error(err), "The public timing service is busy. Please wait a moment and try again.")
        self.assertNotIn("private upstream", ui_utils._friendly_error(err))


if __name__ == "__main__":
    unittest.main()
