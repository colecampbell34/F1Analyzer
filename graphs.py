"""Compatibility exports for graph builders.

Domain implementations live in graphs_telemetry, graphs_trackmap, graphs_race,
and graphs_pace. Keep this module as the stable import surface for callbacks
and tests.
"""
from graphs_common import _add_driver_legend_entries
from graphs_telemetry import _build_telemetry_fig, _split_delta_by_sign
from graphs_trackmap import (
    _build_dominance_fig,
    _build_driver_radar,
    _compute_driver_dna_raw,
    _compute_driver_dna_summary,
    _driver_dna_legend,
    _identify_corners,
    _identify_corners_from_circuit,
    _normalize_driver_dna,
)
from graphs_race import (
    _build_deg_fig,
    _build_pit_stops_fig,
    _build_race_gaps_fig,
    _build_strategy_fig,
    _is_actual_pit_stop_lap,
    _is_truthy_fastf1_value,
    _normalized_driver_key,
    _pit_driver_lookup,
    _resolve_pit_driver_code,
)
from graphs_pace import (
    _build_grid_pace_fig,
    _clean_pace_laps,
    _coerce_bool_series,
    _filter_lap_times_107,
    _is_dry_session_from_weather,
    _lap_time_seconds,
)

__all__ = [
    '_add_driver_legend_entries',
    '_split_delta_by_sign',
    '_build_telemetry_fig',
    '_identify_corners',
    '_identify_corners_from_circuit',
    '_build_dominance_fig',
    '_driver_dna_legend',
    '_compute_driver_dna_raw',
    '_normalize_driver_dna',
    '_compute_driver_dna_summary',
    '_build_driver_radar',
    '_normalized_driver_key',
    '_pit_driver_lookup',
    '_resolve_pit_driver_code',
    '_is_truthy_fastf1_value',
    '_is_actual_pit_stop_lap',
    '_build_strategy_fig',
    '_build_deg_fig',
    '_build_race_gaps_fig',
    '_build_pit_stops_fig',
    '_coerce_bool_series',
    '_is_dry_session_from_weather',
    '_clean_pace_laps',
    '_lap_time_seconds',
    '_filter_lap_times_107',
    '_build_grid_pace_fig',
]
