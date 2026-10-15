import json
import os
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch, MagicMock

import pandas as pd
import numpy as np

import data
import ui_utils
import ai_cache
import callbacks_shared
import callbacks_ai
import callbacks_tabs
import callbacks_telemetry
import telemetry_prep
import telemetry_dynamics
import strategy_insights
import ux_helpers
import graphs
import graph_shared
import graphs_pace
import graphs_race
import graphs_telemetry
import graphs_trackmap
import runtime
import shared_cache
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

    def test_authorized_via_header(self):
        with patch.dict(os.environ, {"FEEDBACK_ADMIN_TOKEN": "secret"}, clear=False):
            with self.flask_app.test_request_context("/"):
                with patch.object(ui_utils.flask, "request") as req:
                    req.headers = MagicMock()
                    req.cookies = MagicMock()
                    req.headers.get.return_value = "secret"
                    req.cookies.get.return_value = ""
                    self.assertTrue(ui_utils._feedback_admin_authorized())


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
            "tm_d1_lap_mode": "specific",
            "tm_d1_lap": 14,
            "tm_d2_lap_mode": "specific",
            "tm_d2_lap": 15,
            "trackmap_mode": "speed",
        })
        parsed = callbacks_shared._parse_url_state(search)
        self.assertEqual(parsed["year"], 2025)
        self.assertEqual(parsed["race"], "British Grand Prix")
        self.assertEqual(parsed["session_type"], "Race")
        self.assertEqual(parsed["d1_lap_mode"], "specific")
        self.assertEqual(parsed["d1_lap"], 12)
        self.assertEqual(parsed["tm_d1_lap_mode"], "specific")
        self.assertEqual(parsed["tm_d1_lap"], 14)
        self.assertEqual(parsed["tm_d2_lap"], 15)
        self.assertEqual(parsed["trackmap_mode"], "speed")

    def test_invalid_url_view_state_is_ignored(self):
        parsed = callbacks_shared._parse_url_state("?tab=bad&d1_lap_mode=bad&d1_lap=-2&trackmap=bad&mode=bad")
        self.assertIsNone(parsed["tab"])
        self.assertIsNone(parsed["d1_lap_mode"])
        self.assertIsNone(parsed["d1_lap"])
        self.assertIsNone(parsed["trackmap_mode"])
        self.assertNotIn("mode", parsed)

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

    def test_driver_dna_summary_has_expected_labels(self):
        tel = pd.DataFrame({
            "Speed": [90.0, 180.0, 310.0],
            "Brake": [0.0, 0.2, 0.0],
            "Throttle": [10.0, 80.0, 100.0],
            "nGear": [2, 4, 8],
        })

        legend, raw1, raw2, norm1, norm2 = graphs._compute_driver_dna_summary(tel, tel)

        self.assertEqual([abbr for abbr, _label in legend], ["TS", "CS", "FT", "TR", "BU", "BI", "GD"])
        self.assertEqual(len(raw1), 7)
        self.assertEqual(len(raw2), 7)
        self.assertEqual(norm1, [50.0] * 7)
        self.assertEqual(norm2, [50.0] * 7)

    def test_race_position_trace_starts_at_the_grid(self):
        class Laps(pd.DataFrame):
            @property
            def _constructor(self):
                return Laps

            def pick_drivers(self, driver):
                return Laps(self[self['Driver'] == driver])

        session = MagicMock()
        session.laps = Laps([
            {'Driver': 'VER', 'LapNumber': 1, 'Time': pd.Timedelta(seconds=90), 'Position': 3},
            {'Driver': 'VER', 'LapNumber': 2, 'Time': pd.Timedelta(seconds=180), 'Position': 2},
            {'Driver': 'NOR', 'LapNumber': 1, 'Time': pd.Timedelta(seconds=91), 'Position': 5},
            {'Driver': 'NOR', 'LapNumber': 2, 'Time': pd.Timedelta(seconds=182), 'Position': 4},
        ])
        session.results = pd.DataFrame([
            {'Abbreviation': 'VER', 'GridPosition': 6},
            {'Abbreviation': 'NOR', 'GridPosition': 2},
        ])

        with patch.object(graphs_race, 'get_track_status_events', return_value=([], [], [])):
            figure = graphs_race._build_race_gaps_fig(
                session, 'VER', 'NOR', 'VER', 'NOR', '#4781D7', '#F47600',
            )

        self.assertEqual(list(figure.data[1].x)[0], 0)
        self.assertEqual(list(figure.data[1].y)[0], 6.0)
        self.assertEqual(list(figure.data[2].x)[0], 0)
        self.assertEqual(list(figure.data[2].y)[0], 2.0)


class TestStrategyInsights(unittest.TestCase):
    class _Laps:
        def __init__(self, frame):
            self.frame = frame

        def pick_drivers(self, driver):
            return self.frame[self.frame['Driver'] == driver]

    def test_stints_and_pit_impacts_are_compact_and_factual(self):
        session = MagicMock()
        session.laps = self._Laps(pd.DataFrame([
            {'Driver': 'VER', 'LapNumber': 1, 'Stint': 1, 'Compound': 'SOFT', 'Position': 4, 'FreshTyre': True},
            {'Driver': 'VER', 'LapNumber': 2, 'Stint': 1, 'Compound': 'SOFT', 'Position': 4, 'FreshTyre': True},
            {'Driver': 'VER', 'LapNumber': 3, 'Stint': 2, 'Compound': 'MEDIUM', 'Position': 6, 'FreshTyre': True},
            {'Driver': 'VER', 'LapNumber': 4, 'Stint': 2, 'Compound': 'MEDIUM', 'Position': 5, 'FreshTyre': True},
        ]))

        self.assertEqual(strategy_insights.build_driver_stints(session, 'VER'), [
            {'compound': 'SOFT', 'stint': 1.0, 'start_lap': 1, 'end_lap': 2},
            {'compound': 'MEDIUM', 'stint': 2.0, 'start_lap': 3, 'end_lap': 4},
        ])
        self.assertEqual(strategy_insights.build_driver_pit_impacts(session, 'VER'), [{
            'pit_lap': 2,
            'from_compound': 'SOFT',
            'to_compound': 'MEDIUM',
            'position_before': 4,
            'position_after': 6,
        }])


class TestTelemetryGForce(unittest.TestCase):
    def test_dynamics_estimate_normalizes_time_and_returns_finite_summary(self):
        samples = np.arange(20, dtype=float)
        telemetry = pd.DataFrame({
            'Time': pd.to_timedelta(samples + 12, unit='s'),
            'Distance': samples * 15,
            'Speed': 160 + samples * 2,
            'X': 100 * np.cos(samples / 8),
            'Y': 100 * np.sin(samples / 8),
        })

        times, distances, lateral, longitudinal = telemetry_dynamics.calculate_g_series(telemetry)
        self.assertAlmostEqual(times[0], 0.0)
        self.assertEqual(len(distances), len(telemetry))
        self.assertTrue(np.isfinite(lateral).all())
        self.assertTrue(np.isfinite(longitudinal).all())

    def test_replay_uses_browser_animation_loop(self):
        with open('assets/scripts.js', encoding='utf-8') as script_file:
            script = script_file.read()

        self.assertIn('requestAnimationFrame(draw)', script)
        self.assertIn('window.f1AnalyzerPlayback', script)
        self.assertIn('Plotly can move the two mounted marker', script)


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

    def test_ai_context_survives_an_unavailable_speed_trace(self):
        """Telemetry must enrich AI context, never prevent it from loading."""
        params = {
            'year': 2025,
            'race': 'British Grand Prix',
            'session_type': 'Race',
            'driver1': 'NOR',
            'driver2': 'PIA',
        }
        session = MagicMock()
        lap1 = pd.Series({'LapTime': pd.Timedelta(seconds=90)})
        lap2 = pd.Series({'LapTime': pd.Timedelta(seconds=91)})

        with (
            patch('data.load_session_with_preload', return_value=session),
            patch('data.get_best_lap', side_effect=[lap1, lap2]),
            patch(
                'telemetry_prep._usable_lap_and_trace',
                side_effect=ValueError('No usable speed trace is available for this selected lap.'),
            ),
            patch('ai_utils._gather_session_context', return_value='core session context') as gather,
        ):
            context = callbacks_ai._build_ai_session_context(params)

        self.assertTrue(context.startswith(callbacks_ai._ai_context_header(params)))
        self.assertIn('core session context', context)
        self.assertIn('Do not infer speed, braking, throttle, gear, GPS, or delta details.', context)
        selected_context = gather.call_args.kwargs['selected_lap_context']
        self.assertIsNone(selected_context['tel1'])
        self.assertIsNone(selected_context['tel2'])


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

        self.assertIn("trackmap-d1-lap-dropdown", input_ids)
        self.assertIn("trackmap-d2-lap-dropdown", input_ids)
        self.assertNotIn("d1-lap-dropdown", input_ids)

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

        prep.assert_called_once_with(
            params, "specific", "specific", 12, 13, require_position=True
        )
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


class TestTelemetryTraceFallbacks(unittest.TestCase):
    @staticmethod
    def _core_trace(points=8):
        return pd.DataFrame({
            'Time': pd.to_timedelta(range(points), unit='s'),
            'Distance': [float(point * 10) for point in range(points)],
            'Speed': [180.0 + point for point in range(points)],
        })

    def test_car_data_recovers_when_merged_trace_has_no_speed_channel(self):
        lap = MagicMock()
        merged = MagicMock()
        merged.add_distance.return_value = self._core_trace().drop(columns=['Speed'])
        car = MagicMock()
        car.add_distance.return_value = self._core_trace()
        lap.get_telemetry.return_value = merged
        lap.get_car_data.return_value = car

        trace = telemetry_prep._telemetry_with_distance(lap)

        lap.get_car_data.assert_called_once()
        self.assertEqual(len(trace), 8)
        self.assertTrue(trace['Throttle'].isna().all())
        self.assertTrue(trace['Brake'].isna().all())
        self.assertTrue(trace['nGear'].isna().all())

    def test_speed_trace_survives_missing_optional_channels(self):
        lap = MagicMock()
        merged = MagicMock()
        merged.add_distance.return_value = self._core_trace()
        lap.get_telemetry.return_value = merged

        trace = telemetry_prep._telemetry_with_distance(lap)

        lap.get_car_data.assert_not_called()
        self.assertEqual(len(trace), 8)
        self.assertIn('RPM', trace.columns)

    def test_openf1_recovers_when_fastf1_has_no_car_trace(self):
        lap = MagicMock()
        lap.get_telemetry.side_effect = KeyError('no FastF1 telemetry')
        lap.get_car_data.side_effect = KeyError('no FastF1 car data')
        session = MagicMock()
        expected = self._core_trace()

        with patch('openf1_fallback.trace_for_fastf1_lap', return_value=expected) as fallback:
            trace = telemetry_prep._telemetry_with_distance(lap, session=session)

        fallback.assert_called_once_with(session, lap)
        self.assertEqual(trace['Speed'].tolist(), expected['Speed'].tolist())

    def test_fastest_mode_uses_next_fastest_lap_when_the_nominal_best_has_no_trace(self):
        class DriverLaps(pd.DataFrame):
            @property
            def _constructor(self):
                return DriverLaps

            def pick_drivers(self, _driver):
                return self

        laps = DriverLaps([
            {'LapNumber': 12, 'LapTime': pd.Timedelta(seconds=89.5)},
            {'LapNumber': 13, 'LapTime': pd.Timedelta(seconds=89.8)},
        ])
        session = MagicMock()
        session.laps = laps
        selected = laps.iloc[0]
        trace = self._core_trace()

        def get_trace(lap, **_kwargs):
            if int(lap['LapNumber']) == 12:
                raise ValueError('No usable speed trace is available for this selected lap.')
            return trace

        with patch.object(telemetry_prep, '_telemetry_with_distance', side_effect=get_trace):
            lap, actual_trace, used_fallback = telemetry_prep._usable_lap_and_trace(
                session, 'NOR', selected, 'fastest', None
            )

        self.assertTrue(used_fallback)
        self.assertEqual(int(lap['LapNumber']), 13)
        self.assertIs(actual_trace, trace)

    def test_fastest_mode_preserves_the_original_error_when_no_fallback_trace_exists(self):
        """A failed fallback must not replace the useful trace error.

        ``except ValueError as exc`` variables are cleared by Python after the
        exception handler. This guards the failure mode where a fastest-lap
        fallback exhausted every candidate and then raised ``UnboundLocalError``
        instead of the original data-availability message.
        """
        class DriverLaps(pd.DataFrame):
            @property
            def _constructor(self):
                return DriverLaps

            def pick_drivers(self, _driver):
                return self

        laps = DriverLaps([
            {'LapNumber': 12, 'LapTime': pd.Timedelta(seconds=89.5)},
            {'LapNumber': 13, 'LapTime': pd.Timedelta(seconds=89.8)},
        ])
        session = MagicMock()
        session.laps = laps

        with patch.object(
            telemetry_prep,
            '_telemetry_with_distance',
            side_effect=ValueError('No usable speed trace is available for this selected lap.'),
        ):
            with self.assertRaisesRegex(ValueError, 'No usable speed trace'):
                telemetry_prep._usable_lap_and_trace(
                    session, 'NOR', laps.iloc[0], 'fastest', None
                )

    def test_fastest_mode_checks_laps_beyond_the_old_eight_lap_limit(self):
        class DriverLaps(pd.DataFrame):
            @property
            def _constructor(self):
                return DriverLaps

            def pick_drivers(self, _driver):
                return self

        laps = DriverLaps([
            {'LapNumber': lap_number, 'LapTime': pd.Timedelta(seconds=89 + lap_number / 10)}
            for lap_number in range(1, 12)
        ])
        session = MagicMock()
        session.laps = laps
        trace = self._core_trace()

        def get_trace(lap, **_kwargs):
            if int(lap['LapNumber']) != 11:
                raise ValueError('No usable speed trace is available for this selected lap.')
            return trace

        with (
            patch.dict(os.environ, {'TELEMETRY_LAP_FALLBACK_ATTEMPTS': '0'}, clear=False),
            patch.object(telemetry_prep, '_telemetry_with_distance', side_effect=get_trace),
        ):
            lap, actual_trace, used_fallback = telemetry_prep._usable_lap_and_trace(
                session, 'NOR', laps.iloc[0], 'fastest', None
            )

        self.assertTrue(used_fallback)
        self.assertEqual(int(lap['LapNumber']), 11)
        self.assertIs(actual_trace, trace)

    def test_specific_lap_never_substitutes_another_trace(self):
        session = MagicMock()
        selected = pd.Series({'LapNumber': 12, 'LapTime': pd.Timedelta(seconds=89.5)})

        with patch.object(
            telemetry_prep,
            '_telemetry_with_distance',
            side_effect=ValueError('No usable speed trace is available for this selected lap.'),
        ):
            with self.assertRaisesRegex(ValueError, 'No usable speed trace'):
                telemetry_prep._usable_lap_and_trace(session, 'NOR', selected, 'specific', 12)


class TestSharedTelemetryPayload(unittest.TestCase):
    def test_contended_redis_lock_waits_for_the_leader_payload(self):
        """A follower must not start another FastF1 load during a cold miss."""
        trace = pd.DataFrame({
            'Time': pd.to_timedelta(range(8), unit='s'),
            'Distance': [float(point * 10) for point in range(8)],
            'Speed': [180.0 + point for point in range(8)],
        })
        payload = {
            'session': MagicMock(), 'd1': 'NOR', 'd2': 'PIA',
            'lbl1': 'NOR (P1)', 'lbl2': 'PIA (P2)',
            'c1': '#F47600', 'c2': '#F47600',
            'lap1': pd.Series({'LapTime': pd.Timedelta(seconds=90)}),
            'lap2': pd.Series({'LapTime': pd.Timedelta(seconds=91)}),
            'tel1': trace, 'tel2': trace,
        }
        wire = telemetry_prep._payload_to_shared_wire(payload)
        args = (2025, 'British Grand Prix', 'Race', 'NOR', 'PIA', 'fastest', 'fastest', None, None)

        with (
            patch('shared_cache.is_configured', return_value=True),
            patch('shared_cache.get_json', side_effect=[None]),
            patch('shared_cache.acquire_lock', return_value=False),
            patch('shared_cache.wait_for_json', return_value=wire) as wait_for_payload,
            patch.object(telemetry_prep, '_prepare_selected_lap_comparison_cached') as local_load,
        ):
            loaded = telemetry_prep._load_selected_lap_payload(args)

        wait_for_payload.assert_called_once()
        local_load.assert_not_called()
        self.assertEqual(loaded['d1'], 'NOR')

    def test_shared_cache_wait_default_covers_a_cold_fastf1_load(self):
        with patch.dict(os.environ, {'SHARED_TELEMETRY_LOCK_WAIT_SECONDS': ''}, clear=False):
            self.assertEqual(telemetry_prep._shared_cache_wait_seconds(), 80.0)

    def test_shared_payload_skips_a_second_fastf1_load(self):
        trace = pd.DataFrame({
            'Time': pd.to_timedelta(range(8), unit='s'),
            'Distance': [float(point * 10) for point in range(8)],
            'Speed': [180.0 + point for point in range(8)],
            'Throttle': [50.0] * 8,
            'Brake': [0.0] * 8,
            'nGear': [5.0] * 8,
        })
        session = MagicMock()
        session.get_circuit_info.return_value = MagicMock(corners=pd.DataFrame([
            {'Number': 1, 'Letter': '', 'X': 100.0, 'Y': 200.0},
            {'Number': 2, 'Letter': 'A', 'X': 300.0, 'Y': 400.0},
        ]))
        payload = {
            'session': session,
            'd1': 'NOR',
            'd2': 'PIA',
            'lbl1': 'NOR (P1)',
            'lbl2': 'PIA (P2)',
            'c1': '#F47600',
            'c2': '#F47600',
            'lap1': pd.Series({'LapTime': pd.Timedelta(seconds=90)}),
            'lap2': pd.Series({'LapTime': pd.Timedelta(seconds=91)}),
            'tel1': trace,
            'tel2': trace,
        }
        wire = telemetry_prep._payload_to_shared_wire(payload)
        args = (2025, 'British Grand Prix', 'Race', 'NOR', 'PIA', 'fastest', 'fastest', None, None)

        with (
            patch('shared_cache.is_configured', return_value=True),
            patch('shared_cache.get_json', return_value=wire),
            patch.object(telemetry_prep, '_prepare_selected_lap_comparison_cached') as local_load,
        ):
            loaded = telemetry_prep._load_selected_lap_payload(args)

        local_load.assert_not_called()
        self.assertIsNone(loaded['session'])
        self.assertEqual(loaded['lap1']['LapTime'], pd.Timedelta(seconds=90))
        self.assertEqual(len(loaded['tel1']), len(trace))
        self.assertEqual(loaded['circuit_corners'], [
            {'Number': 1, 'Letter': '', 'X': 100.0, 'Y': 200.0},
            {'Number': 2, 'Letter': 'A', 'X': 300.0, 'Y': 400.0},
        ])


class TestTrackMapCornerMarkers(unittest.TestCase):
    def test_cached_circuit_markers_preserve_every_official_turn(self):
        """A Redis cache hit must not replace official markers with speed dips."""
        telemetry = pd.DataFrame({
            'Distance': [float(index * 100) for index in range(16)],
            'Speed': [250.0 - index for index in range(16)],
            'X': [float(index * 10) for index in range(16)],
            'Y': [float(index * 5) for index in range(16)],
        })
        circuit_corners = [
            {'Number': index, 'Letter': '', 'X': float(index * 10), 'Y': float(index * 5)}
            for index in range(1, 16)
        ]

        corners = graphs_trackmap._identify_corners_from_circuit(
            None,
            telemetry,
            telemetry,
            circuit_corners=circuit_corners,
        )

        self.assertEqual(len(corners), 15)
        self.assertEqual([corner['turn'] for corner in corners], [str(index) for index in range(1, 16)])


class TestSharedCacheTransport(unittest.TestCase):
    def setUp(self):
        shared_cache.reset_for_tests()

    def test_upstash_rest_round_trip_uses_compressed_json(self):
        encoded = shared_cache._encode({'answer': 42})
        response_set = MagicMock()
        response_set.read.return_value = b'{"result":"OK"}'
        response_set.__enter__.return_value = response_set
        response_get = MagicMock()
        response_get.read.return_value = (
            ('{"result":' + repr(encoded) + '}').replace("'", '"').encode('utf-8')
        )
        response_get.__enter__.return_value = response_get

        with (
            patch.dict(os.environ, {
                'UPSTASH_REDIS_REST_URL': 'https://cache.example.test',
                'UPSTASH_REDIS_REST_TOKEN': 'test-token',
            }, clear=False),
            patch('shared_cache.urllib.request.urlopen', side_effect=[response_set, response_get]) as urlopen,
        ):
            self.assertTrue(shared_cache.set_json('test:key', {'answer': 42}, 60))
            self.assertEqual(shared_cache.get_json('test:key'), {'answer': 42})

        set_request = urlopen.call_args_list[0].args[0]
        self.assertEqual(json.loads(set_request.data.decode('utf-8'))[:2], ['SET', 'test:key'])

    def test_vercel_kv_environment_names_enable_the_cache(self):
        with patch.dict(os.environ, {
            'KV_REST_API_URL': 'https://cache.example.test',
            'KV_REST_API_TOKEN': 'test-token',
        }, clear=True):
            self.assertTrue(shared_cache.is_configured())

    def test_probe_reports_live_cache_without_exposing_credentials(self):
        with (
            patch('shared_cache.is_configured', return_value=True),
            patch('shared_cache._command', return_value='PONG'),
        ):
            self.assertEqual(
                shared_cache.probe(),
                {'configured': True, 'reachable': True},
            )


class TestDeltaChartSegments(unittest.TestCase):
    def test_live_delta_progress_normalizes_metre_and_fallback_traces(self):
        progress, values = callbacks_telemetry._delta_progress_values(
            [125.0, 562.5, 1000.0], [0.0, 0.18, 0.42]
        )
        self.assertTrue(np.allclose(progress, [0.0, 0.5, 1.0]))
        self.assertTrue(np.allclose(values, [0.0, 0.18, 0.42]))

        fallback_progress, fallback_values = callbacks_telemetry._delta_progress_values(
            [0.0, 0.5, 1.0], [0.0, 0.18, 0.42]
        )
        self.assertTrue(np.allclose(fallback_progress, progress))
        self.assertTrue(np.allclose(fallback_values, values))

    def test_car_trace_delta_fallback_preserves_a_usable_gap_series(self):
        points = list(range(12))
        reference = pd.DataFrame({
            'Distance': [float(point * 10) for point in points],
            'Time': pd.to_timedelta(points, unit='s'),
        })
        compare = pd.DataFrame({
            'Distance': [float(point * 11) for point in points],
            'Time': pd.to_timedelta([point * 1.1 for point in points], unit='s'),
        })

        delta, ref_trace, compare_trace = graph_shared._telemetry_delta_fallback(reference, compare)

        self.assertGreater(len(delta), 100)
        self.assertAlmostEqual(float(delta[-1]), 1.1, places=6)
        self.assertEqual(len(ref_trace), len(compare_trace))

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
        expected = {
            "year": 2025,
            "race": "Latest Grand Prix",
            "session_type": "Race",
        }
        with patch.object(data, "get_latest_static_race_session", return_value=expected):
            latest = data.get_latest_race_session_default(now="2025-07-01T00:00:00Z")

        self.assertEqual(latest, expected)


class TestPreloadJobs(unittest.TestCase):
    def test_tab_profiles_match_their_data_requirements(self):
        trackmap = data.get_preload_kwargs_for_tab('tab-trackmap')
        racepace = data.get_preload_kwargs_for_tab('tab-racepace')

        self.assertTrue(trackmap['telemetry'])
        self.assertFalse(trackmap['weather'])
        self.assertFalse(racepace['telemetry'])
        self.assertTrue(racepace['weather'])

    def setUp(self):
        with data._SESSION_PRELOAD_LOCK:
            data._SESSION_PRELOAD_FUTURES.clear()
            data._SESSION_PRELOAD_JOBS.clear()
        with data._DIRECT_PROFILE_LOCK:
            data._DIRECT_PROFILE_FUTURES.clear()
        data._load_session_granular_cached.cache_clear()

    def tearDown(self):
        data._load_session_granular_cached.cache_clear()

    def test_telemetry_load_retries_when_fastf1_returns_an_empty_car_data_feed(self):
        empty_session = MagicMock()
        empty_session.car_data = {}
        recovered_session = MagicMock()
        recovered_session.car_data = {
            '1': pd.DataFrame({'Speed': [100.0] * 6}),
        }

        with (
            patch.object(data, '_ensure_cache_ready'),
            patch('fastf1.get_session', side_effect=[empty_session, recovered_session]) as get_session,
            patch('fastf1.Cache.enable_cache') as enable_cache,
            patch.object(data.time, 'sleep'),
        ):
            loaded = data._load_session_granular_cached(
                2025, 'British Grand Prix', 'Race', laps=True, telemetry=True
            )

        self.assertIs(loaded, recovered_session)
        self.assertEqual(get_session.call_count, 2)
        empty_session.load.assert_called_once_with(
            laps=True, telemetry=True, weather=False, messages=False
        )
        recovered_session.load.assert_called_once_with(
            laps=True, telemetry=True, weather=False, messages=False
        )
        enable_cache.assert_has_calls([
            unittest.mock.call(data._CACHE_DIR, force_renew=True),
            unittest.mock.call(data._CACHE_DIR),
        ])

    def test_vercel_keeps_valid_laps_for_openf1_after_empty_fastf1_car_data(self):
        empty_session = MagicMock()
        empty_session.car_data = {}
        empty_session.laps = pd.DataFrame([
            {'DriverNumber': '1', 'LapNumber': 4},
        ])

        with (
            patch.dict(os.environ, {'VERCEL': '1', 'OPENF1_FALLBACK_ENABLED': '1'}, clear=False),
            patch.object(data, '_ensure_cache_ready'),
            patch('fastf1.get_session', return_value=empty_session) as get_session,
            patch('fastf1.Cache.enable_cache') as enable_cache,
        ):
            loaded = data._load_session_granular_cached(
                2026, 'Singapore Grand Prix', 'Race', laps=True, telemetry=True
            )

        self.assertIs(loaded, empty_session)
        self.assertTrue(loaded._fastf1_telemetry_unavailable)
        self.assertEqual(get_session.call_count, 1)
        enable_cache.assert_not_called()

    def test_direct_profile_singleflight_dedupes_concurrent_telemetry_callbacks(self):
        entered = threading.Event()
        release = threading.Event()
        sentinel = object()

        def loader(*_args):
            entered.set()
            self.assertTrue(release.wait(timeout=2))
            return sentinel

        with patch.object(data, '_load_session_granular_cached', side_effect=loader) as mocked_loader:
            with ThreadPoolExecutor(max_workers=2) as executor:
                first = executor.submit(
                    data._load_session_profile_singleflight,
                    2025, 'British Grand Prix', 'Race', True, True, False, False,
                )
                self.assertTrue(entered.wait(timeout=1))
                second = executor.submit(
                    data._load_session_profile_singleflight,
                    2025, 'British Grand Prix', 'Race', True, True, False, False,
                )
                release.set()
                self.assertIs(first.result(timeout=2), sentinel)
                self.assertIs(second.result(timeout=2), sentinel)

        self.assertEqual(mocked_loader.call_count, 1)

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
    def test_root_app_exports_flask_wsgi_app_for_vercel(self):
        import flask
        import app as app_module

        self.assertIsInstance(app_module.app, flask.Flask)

    def test_vercel_runtime_init_uses_lazy_on_demand_setup(self):
        import app as app_module

        old_started = app_module._RUNTIME_INIT_STARTED
        old_done = app_module._RUNTIME_INIT_DONE
        try:
            app_module._RUNTIME_INIT_STARTED = False
            app_module._RUNTIME_INIT_DONE = False
            with patch.dict(os.environ, {"VERCEL": "1"}, clear=False):
                app_module._start_runtime_init_once()

            self.assertFalse(app_module._RUNTIME_INIT_STARTED)
            self.assertTrue(app_module._RUNTIME_INIT_DONE)
        finally:
            app_module._RUNTIME_INIT_STARTED = old_started
            app_module._RUNTIME_INIT_DONE = old_done

    def test_css_assets_revalidate_after_deploy(self):
        import app as app_module
        client = app_module.server.test_client()

        response = client.get("/assets/custom.css")
        try:
            self.assertEqual(response.mimetype, "text/css")
            self.assertEqual(response.headers.get("Cache-Control"), "no-cache, max-age=0, must-revalidate")
        finally:
            response.close()

    def test_runtime_policy_uses_tmp_for_serverless_and_local_by_default(self):
        with patch.dict(os.environ, {"VERCEL": "1"}, clear=False):
            self.assertTrue(runtime.is_serverless())
            self.assertEqual(runtime.runtime_directory("MISSING_CACHE_PATH", "unit-cache"), "/tmp/unit-cache")
            self.assertEqual(runtime.storage_scope(), "ephemeral")

        with patch.dict(os.environ, {"VERCEL": ""}, clear=False):
            self.assertFalse(runtime.is_serverless())
            self.assertEqual(runtime.runtime_directory("MISSING_CACHE_PATH", "unit-cache"), "unit-cache")
            self.assertEqual(runtime.storage_scope(), "local")

    def test_vercel_configuration_uses_native_flask_routing_and_revalidates_shell_assets(self):
        import json

        with open("vercel.json", encoding="utf-8") as config_file:
            config = json.load(config_file)

        # A fixed catch-all rewrite loses the requested Dash asset path, so
        # native Flask routing must receive the original URL unchanged.
        self.assertNotIn("rewrites", config)
        self.assertIn("app.py", config["functions"])
        self.assertTrue(config["fluid"])
        self.assertEqual(config["functions"]["app.py"]["maxDuration"], 300)
        mutable_header = next(
            item for item in config["headers"]
            if item["source"] == "/assets/(custom.css|race-intelligence.css|scripts.js|manifest.json)"
        )
        self.assertEqual(
            mutable_header["headers"][0]["value"],
            "no-cache, max-age=0, must-revalidate",
        )

    def test_renderer_waits_for_the_cross_version_dash_constructor(self):
        with open("app.py", encoding="utf-8") as app_file:
            app_source = app_file.read()

        self.assertIn("typeof DashRenderer !== 'undefined'", app_source)
        self.assertNotIn("new window.DashRenderer", app_source)

    def test_service_worker_does_not_cache_mutable_dash_shell_assets(self):
        with open("assets/service-worker.js", encoding="utf-8") as worker_file:
            worker_source = worker_file.read()

        self.assertNotIn("'/assets/custom.css'", worker_source)
        self.assertNotIn("'/assets/scripts.js'", worker_source)
        self.assertIn("isCacheableStaticAsset", worker_source)

    def test_preload_status_requires_params(self):
        import app as app_module
        client = app_module.server.test_client()
        response = client.get("/api/preload-status")
        self.assertEqual(response.status_code, 400)

    def test_health_cache_probe_is_opt_in(self):
        import app as app_module

        with patch('shared_cache.probe', return_value={'configured': True, 'reachable': True}):
            response = app_module.server.test_client().get('/healthz?cache=1')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.get_json()['shared_cache'],
            {'configured': True, 'reachable': True},
        )

    def test_perf_requires_admin_token_and_returns_snapshot(self):
        import app as app_module
        client = app_module.server.test_client()
        with patch.dict(os.environ, {"FEEDBACK_ADMIN_TOKEN": "secret"}, clear=False):
            response = client.get("/api/perf", headers={"X-Feedback-Admin-Token": "secret"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("perf", response.get_json())


class TestRobustErrorHandling(unittest.TestCase):
    def test_friendly_error_translates_telemetry_and_date_errors(self):
        e1 = KeyError("None of [Index(['Date'], dtype='object')] are in the columns")
        e2 = ValueError("telemetry data is not available")
        
        self.assertEqual(
            ui_utils._friendly_error(e1),
            "Telemetry data is incomplete or has missing timestamps for this session."
        )
        self.assertEqual(
            ui_utils._friendly_error(e2),
            "Telemetry data is not available or is incomplete for this session from the F1 live timing feed."
        )

    def test_clean_pace_laps_with_missing_columns(self):
        # Empty DataFrame without LapTime
        df_empty = pd.DataFrame()
        self.assertTrue(graphs_pace._clean_pace_laps(df_empty).empty)
        
        # DataFrame without LapTime but with other columns
        df_no_laptime = pd.DataFrame({"Driver": ["VER"]})
        self.assertTrue(graphs_pace._clean_pace_laps(df_no_laptime).empty)

    def test_compute_driver_dna_raw_with_missing_columns(self):
        # Missing required telemetry columns
        df_invalid = pd.DataFrame({"Speed": [300.0]})
        dna = graphs_trackmap._compute_driver_dna_raw(df_invalid)
        self.assertEqual(dna, [0.0] * 7)

    def test_telemetry_with_distance_does_not_trust_a_stale_unavailable_flag(self):
        session = MagicMock()
        session._telemetry_unavailable = True
        lap = MagicMock()
        points = list(range(12))
        telemetry = pd.DataFrame({
            "Time": pd.to_timedelta(points, unit="s"),
            "Distance": [float(point * 10) for point in points],
            "Speed": [100.0 + point for point in points],
            "Throttle": [50.0 + point for point in points],
            "Brake": [0.0] * len(points),
            "nGear": [3] * len(points),
        })
        merged_trace = MagicMock()
        merged_trace.add_distance.return_value = telemetry
        lap.get_telemetry.return_value = merged_trace

        result = telemetry_prep._telemetry_with_distance(lap, session=session)

        self.assertEqual(len(result), len(points))
        lap.get_telemetry.assert_called_once()


if __name__ == "__main__":
    unittest.main()
