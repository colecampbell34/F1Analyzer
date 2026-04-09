import pandas as pd
import numpy as np
import os
from google import genai
from dotenv import load_dotenv
from data import get_track_status_events

# --- GEMINI API SETUP ---
load_dotenv()
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

def _gather_session_context(session, session_type, driver1, driver2):
    """Builds a comprehensive text summary of the session data to feed to the LLM as context."""
    lines = [f"Session Type: {session_type}", f"Drivers being compared: {driver1} vs {driver2}", ""]

    # Fastest lap comparison
    try:
        lap1 = session.laps.pick_drivers(driver1).pick_fastest()
        lap2 = session.laps.pick_drivers(driver2).pick_fastest()
        t1 = lap1['LapTime'].total_seconds()
        t2 = lap2['LapTime'].total_seconds()
        lines.append(f"Fastest Lap: {driver1} = {t1:.3f}s, {driver2} = {t2:.3f}s (Δ {abs(t1-t2):.3f}s)")

        # Sector times
        for s in [1, 2, 3]:
            s1 = lap1.get(f'Sector{s}Time')
            s2 = lap2.get(f'Sector{s}Time')
            if pd.notna(s1) and pd.notna(s2):
                lines.append(f"  Sector {s}: {driver1} = {s1.total_seconds():.3f}s, {driver2} = {s2.total_seconds():.3f}s")
    except Exception:
        lines.append("Fastest lap data: unavailable")

    # Race/Sprint specific data
    if session_type in ['Race', 'Sprint']:
        for drv in [driver1, driver2]:
            try:
                all_laps = session.laps.pick_drivers(drv).reset_index(drop=True)
                total_laps = int(all_laps['LapNumber'].max()) if not all_laps.empty else 0

                rl = all_laps.pick_wo_box().pick_track_status('1').loc[all_laps['LapNumber'] > 1].reset_index(drop=True)
                rl['LapTime_Sec'] = rl['LapTime'].dt.total_seconds()
                rl = rl.dropna(subset=['LapTime_Sec'])

                lines.append(f"\n=== {drv} ===")
                lines.append(f"Total laps completed: {total_laps}")

                if not rl.empty:
                    lines.append(f"Racing laps (excl. pit/SC/lap 1): {len(rl)}")
                    lines.append(f"  Average pace: {rl['LapTime_Sec'].mean():.3f}s")
                    lines.append(f"  Median pace: {rl['LapTime_Sec'].median():.3f}s")
                    lines.append(f"  Best lap: {rl['LapTime_Sec'].min():.3f}s")
                    lines.append(f"  Worst lap: {rl['LapTime_Sec'].max():.3f}s")

                # Pit stops (explicit lap numbers)
                pit_laps = all_laps[all_laps['PitOutTime'].notna()]['LapNumber'].tolist()
                if pit_laps:
                    lines.append(f"  Pit stop(s) on lap(s): {', '.join(str(int(l)) for l in pit_laps)}")
                else:
                    lines.append("  Pit stops: None")

                # Stint & tyre data with lap ranges
                if 'Stint' in all_laps.columns:
                    stints = sorted(all_laps['Stint'].dropna().unique())
                    lines.append(f"  Number of stints: {len(stints)}")
                    for stint in stints:
                        stint_all = all_laps[all_laps['Stint'] == stint].sort_values('LapNumber')
                        if stint_all.empty:
                            continue
                        lap_start = int(stint_all['LapNumber'].min())
                        lap_end = int(stint_all['LapNumber'].max())
                        comp = stint_all['Compound'].iloc[0] if 'Compound' in stint_all.columns else '?'
                        total_stint_laps = len(stint_all)

                        stint_racing = rl[rl['Stint'] == stint].sort_values('LapNumber').reset_index(drop=True)
                        if len(stint_racing) >= 3:
                            stint_racing['StintLap'] = range(1, len(stint_racing) + 1)
                            slope = np.polyfit(stint_racing['StintLap'].values.astype(float),
                                             stint_racing['LapTime_Sec'].values, 1)[0]
                            lines.append(f"    Stint {int(stint)}: {comp} tyres, laps {lap_start}-{lap_end} "
                                       f"({total_stint_laps} laps), deg rate: {slope:+.3f}s/lap")
                        else:
                            lines.append(f"    Stint {int(stint)}: {comp} tyres, laps {lap_start}-{lap_end} "
                                       f"({total_stint_laps} laps)")

                # Position changes
                if 'Position' in all_laps.columns and not all_laps.empty:
                    start_p = all_laps['Position'].iloc[0]
                    end_p = all_laps['Position'].iloc[-1]
                    if pd.notna(start_p) and pd.notna(end_p):
                        lines.append(f"  Grid position: P{int(start_p)} → Finish: P{int(end_p)}")

            except Exception:
                lines.append(f"\n{drv}: lap data unavailable")

        # Track status events (SC, VSC, Red Flag)
        lines.append("\n=== Track Status Events ===")
        sc_laps, vsc_laps, red_laps = get_track_status_events(session)

        if sc_laps:
            lines.append(f"Safety Car on lap(s): {', '.join(str(int(l)) for l in sorted(sc_laps))}")
        if vsc_laps:
            lines.append(f"Virtual Safety Car on lap(s): {', '.join(str(int(l)) for l in sorted(vsc_laps))}")
        if red_laps:
            lines.append(f"Red Flag on lap(s): {', '.join(str(int(l)) for l in sorted(red_laps))}")
        if not sc_laps and not vsc_laps and not red_laps:
            lines.append("No Safety Car, VSC, or Red Flag incidents during the session.")

        try:
            weather = session.weather_data
            if not weather.empty:
                lines.append(f"\n=== Weather ===")
                lines.append(f"Track Temp: {weather['TrackTemp'].min():.1f}°C - {weather['TrackTemp'].max():.1f}°C")
                lines.append(f"Air Temp: {weather['AirTemp'].min():.1f}°C - {weather['AirTemp'].max():.1f}°C")
                if weather['Rainfall'].any():
                    lines.append("Rain: Yes (rain detected during session)")
                else:
                    lines.append("Rain: No")
        except Exception:
            pass

        try:
            lines.append("\n=== Detailed Lap Data (Selected Drivers) ===")
            lines.append("Driver, Lap, LapTime(s), S1(s), S2(s), S3(s), Tyres, Status")
            for drv in [driver1, driver2]:
                all_laps = session.laps.pick_drivers(drv)
                for _, lap in all_laps.iterrows():
                    lt = f"{lap['LapTime'].total_seconds():.3f}" if pd.notna(lap['LapTime']) else "N/A"
                    s1 = f"{lap['Sector1Time'].total_seconds():.3f}" if pd.notna(lap.get('Sector1Time')) else "N/A"
                    s2 = f"{lap['Sector2Time'].total_seconds():.3f}" if pd.notna(lap.get('Sector2Time')) else "N/A"
                    s3 = f"{lap['Sector3Time'].total_seconds():.3f}" if pd.notna(lap.get('Sector3Time')) else "N/A"
                    comp = lap.get('Compound', 'N/A')
                    stat = lap.get('TrackStatus', 'N/A')
                    lines.append(f"{drv}, {lap['LapNumber']}, {lt}, {s1}, {s2}, {s3}, {comp}, {stat}")
        except Exception:
            pass

    return "\n".join(lines)

