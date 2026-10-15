"""Estimated G-force helpers for the Telemetry sidecar.

FastF1 does not expose chassis accelerometers. Longitudinal load is estimated
from the speed trace and lateral load from the change in position heading.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


GRAVITY_TO_G = 0.101971621


def _smooth(values, window=11):
    """Return a conservative, NaN-safe telemetry smoothing pass."""
    series = (
        pd.Series(values, dtype=float)
        .replace([np.inf, -np.inf], np.nan)
        .interpolate(limit_direction='both')
        .ffill()
        .bfill()
    )
    if series.empty or series.isna().all():
        return np.zeros(len(series), dtype=float)
    return (
        series.rolling(window=window, center=True, min_periods=1).median()
        .rolling(window=window, center=True, min_periods=1).mean()
        .to_numpy(dtype=float)
    )


def calculate_g_series(telemetry):
    """Estimate time, distance, lateral G and longitudinal G for a trace."""
    required = ('Time', 'Distance', 'Speed', 'X', 'Y')
    if telemetry is None or telemetry.empty or not all(col in telemetry.columns for col in required):
        raise ValueError('G-force traces need position, speed, distance, and time samples.')

    frame = telemetry.loc[:, list(required)].copy()
    frame['Time'] = pd.to_timedelta(frame['Time'], errors='coerce')
    for column in ('Distance', 'Speed', 'X', 'Y'):
        frame[column] = pd.to_numeric(frame[column], errors='coerce')
    frame = frame.dropna(subset=list(required))
    if len(frame) < 5:
        raise ValueError('G-force traces need at least five valid position samples.')

    t_sec = frame['Time'].dt.total_seconds().to_numpy(dtype=float)
    t_sec = t_sec - t_sec[0]
    for index in range(1, len(t_sec)):
        if not np.isfinite(t_sec[index]) or t_sec[index] <= t_sec[index - 1]:
            t_sec[index] = t_sec[index - 1] + 1e-3

    v_ms = _smooth(frame['Speed'].to_numpy(dtype=float) / 3.6, window=9)
    x = _smooth(frame['X'].to_numpy(dtype=float), window=7)
    y = _smooth(frame['Y'].to_numpy(dtype=float), window=7)
    long_g = _smooth(np.gradient(v_ms, t_sec, edge_order=1) * GRAVITY_TO_G, window=13)
    heading = np.unwrap(np.arctan2(
        np.gradient(y, t_sec, edge_order=1),
        np.gradient(x, t_sec, edge_order=1),
    ))
    lat_g = _smooth((v_ms * np.gradient(heading, t_sec, edge_order=1)) * GRAVITY_TO_G, window=13)
    return (
        t_sec,
        frame['Distance'].to_numpy(dtype=float),
        np.clip(lat_g, -5.5, 5.5),
        np.clip(long_g, -5.5, 5.5),
    )

