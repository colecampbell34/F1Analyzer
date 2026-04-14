import pandas as pd
import numpy as np
import os
import time
import hashlib
from datetime import datetime, timezone
from collections import defaultdict
from dotenv import load_dotenv
from data import get_track_status_events, get_best_lap, get_pit_stop_data

# --- GEMINI API SETUP ---
load_dotenv()
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
AI_ENABLED = bool(GEMINI_API_KEY)

# --- Model Configuration ---
GEMINI_MODEL = 'gemini-3.1-flash-lite-preview'

# --- Rate Limiting (per IP) ---
_AI_RATE_LIMIT = defaultdict(list)  # IP → list of timestamps
MAX_REQUESTS_PER_MINUTE = 2
MAX_REQUESTS_PER_HOUR = 10

# --- Daily Budget (global, across all users) ---
_daily_request_count = 0
_daily_reset_date = None
DAILY_REQUEST_LIMIT = 400  # Hard cap (API limit is 500 rpd for flash-lite)

# --- Response Cache (exact normalized match) ---
_AI_RESPONSE_CACHE = {}  # cache_key → response_text
MAX_CACHE_SIZE = 100


def check_rate_limit(ip):
    """Check if the given IP is within rate limits. Returns (allowed, wait_message)."""
    now = time.time()

    # Clean entries older than 1 hour
    _AI_RATE_LIMIT[ip] = [t for t in _AI_RATE_LIMIT[ip] if now - t < 3600]

    recent_minute = sum(1 for t in _AI_RATE_LIMIT[ip] if now - t < 60)
    recent_hour = len(_AI_RATE_LIMIT[ip])

    if recent_minute >= MAX_REQUESTS_PER_MINUTE:
        return False, "You've reached the limit of 2 questions per minute. Please wait a moment before asking again."
    if recent_hour >= MAX_REQUESTS_PER_HOUR:
        return False, "You've reached the limit of 10 questions per hour. Please take a break and come back shortly."

    _AI_RATE_LIMIT[ip].append(now)
    return True, None


def check_daily_budget():
    """Check if the global daily request budget allows another call. Returns True if allowed."""
    global _daily_request_count, _daily_reset_date
    today = datetime.now(timezone.utc).date()

    if _daily_reset_date != today:
        _daily_request_count = 0
        _daily_reset_date = today

    if _daily_request_count >= DAILY_REQUEST_LIMIT:
        return False

    _daily_request_count += 1
    return True


def _cache_key(session_context, question):
    """Generate a cache key from session context + normalized question.

    Only matches EXACT same questions (after lowering + stripping) for the same session.
    Similar-but-different questions will miss the cache intentionally — we don't want
    to return a wrong answer for a different question.
    """
    q_normalized = question.lower().strip()
    # Use first 200 chars of context to identify the session uniquely
    ctx_prefix = session_context[:200] if session_context else ''
    raw = ctx_prefix + '||' + q_normalized
    return hashlib.md5(raw.encode()).hexdigest()


def get_cached_response(session_context, question):
    """Returns cached response if an exact normalized match exists, else None."""
    key = _cache_key(session_context, question)
    return _AI_RESPONSE_CACHE.get(key)


def store_cached_response(session_context, question, response):
    """Store a response in the cache. Evicts oldest entries if cache is full."""
    if len(_AI_RESPONSE_CACHE) >= MAX_CACHE_SIZE:
        # Evict the oldest entry (first inserted key)
        oldest_key = next(iter(_AI_RESPONSE_CACHE))
        del _AI_RESPONSE_CACHE[oldest_key]
    key = _cache_key(session_context, question)
    _AI_RESPONSE_CACHE[key] = response


def _gather_session_context(session, session_type, driver1, driver2):
    """Builds a comprehensive text summary of the session data to feed to the LLM as context."""
    lines = ["=== AUTHORITATIVE DRIVER-TEAM ASSIGNMENTS ===",
             "CRITICAL: Use ONLY the team assignments listed here. "
             "Do NOT rely on prior training knowledge for any driver's team or car number."]

    try:
        if getattr(session, 'results', None) is not None and not session.results.empty:
            for _, row in session.results.iterrows():
                abbr = row.get('Abbreviation', '')
                team = row.get('TeamName', '')
                first = str(row.get('FirstName', '')).strip()
                last = str(row.get('LastName', '')).strip()
                if isinstance(abbr, str) and len(abbr) == 3 and isinstance(team, str) and team:
                    full_name = f"{first} {last}".strip()
                    lines.append(f"  {abbr} ({full_name}) → {team}")
        else:
            lines.append("  (Team data unavailable for this session)")
    except Exception:
        lines.append("  (Team data unavailable for this session)")
    lines.append("")

    lines += [f"Session Type: {session_type}", f"Drivers being compared: {driver1} vs {driver2}", ""]

    # Fastest lap comparison
    try:
        lap1 = get_best_lap(session, driver1)
        lap2 = get_best_lap(session, driver2)
        
        if lap1 is not None and lap2 is not None and pd.notna(lap1['LapTime']) and pd.notna(lap2['LapTime']):
            t1 = lap1['LapTime'].total_seconds()
            t2 = lap2['LapTime'].total_seconds()
            lines.append(f"Fastest Lap: {driver1} = {t1:.3f}s, {driver2} = {t2:.3f}s (Δ {abs(t1 - t2):.3f}s)")

            # Sector times
            for s in [1, 2, 3]:
                s1 = lap1.get(f'Sector{s}Time')
                s2 = lap2.get(f'Sector{s}Time')
                if pd.notna(s1) and pd.notna(s2):
                    lines.append(
                        f"  Sector {s}: {driver1} = {s1.total_seconds():.3f}s, {driver2} = {s2.total_seconds():.3f}s")
            
            # Telemetry Aggregation
            for drv, l in [(driver1, lap1), (driver2, lap2)]:
                try:
                    tel = l.get_telemetry()
                    if not tel.empty:
                        max_spd = tel['Speed'].max()
                        min_spd = tel['Speed'].min()
                        full_thr = (tel['Throttle'] == 100).mean() * 100
                        brk = (tel['Brake'] > 0).mean() * 100
                        lines.append(f"  {drv} Telemetry (Fastest Lap): Max Speed = {max_spd} km/h, Min Speed = {min_spd} km/h, Full Throttle = {full_thr:.1f}%, Braking = {brk:.1f}%")
                except Exception:
                    pass

        else:
            lines.append("Fastest lap comparison: data incomplete for one or both drivers")
    except Exception:
        lines.append("Fastest lap data: unavailable")

    # Race/Sprint specific data
    if session_type in ['Race', 'Sprint']:
        try:
            pit_stops_df = get_pit_stop_data(session.event.year, session.event.RoundNumber)
        except Exception:
            pit_stops_df = pd.DataFrame()

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

                # Pit stops (explicit lap numbers and duration)
                pit_laps = all_laps[all_laps['PitInTime'].notna()]['LapNumber'].tolist()
                if pit_laps:
                    pit_info = []
                    for pl in pit_laps:
                        dur_str = ""
                        if not pit_stops_df.empty:
                            try:
                                for _, stop in pit_stops_df.iterrows():
                                    c = stop.get('driverCode') or str(stop.get('driverId', '')).upper()[:3]
                                    if c == drv and str(stop.get('lap')) == str(int(pl)):
                                        dur = stop.get('duration')
                                        if pd.notna(dur):
                                            dur_str = f" ({dur.total_seconds():.1f}s in pit lane)"
                                        break
                            except Exception:
                                pass
                        pit_info.append(f"Lap {int(pl)}{dur_str}")
                    lines.append(f"  Pit stop(s): {', '.join(pit_info)}")
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
                            FUEL_CORRECTION = 0.06
                            stint_racing['CorrectedTime'] = stint_racing['LapTime_Sec'] + FUEL_CORRECTION * stint_racing['StintLap']
                            slope = np.polyfit(stint_racing['StintLap'].values.astype(float),
                                               stint_racing['CorrectedTime'].values, 1)[0]
                            lines.append(f"    Stint {int(stint)}: {comp} tyres, laps {lap_start}-{lap_end} "
                                         f"({total_stint_laps} laps), deg rate: {slope:+.3f}s/lap (fuel-corrected)")
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
            lines.append("\n=== Detailed Head-to-Head Lap Data (Comparing Selected Drivers) ===")
            lines.append(f"Lap, Gap ({driver1} minus {driver2}), {driver1}_Pos, {driver2}_Pos, {driver1}_LapTime, {driver2}_LapTime, {driver1}_Tyres, {driver2}_Tyres, Status")
            lines.append(f"(Note: A negative Gap means {driver1} is AHEAD by that margin. A positive Gap means {driver2} is AHEAD. Gap < 1.5s implies dirty air trailing.)")
            
            laps1 = session.laps.pick_drivers(driver1).dropna(subset=['Time']).set_index('LapNumber')
            laps2 = session.laps.pick_drivers(driver2).dropna(subset=['Time']).set_index('LapNumber')
            
            all_lap_nums = sorted(set(laps1.index).union(set(laps2.index)))
            
            for ln in all_lap_nums:
                has_1 = ln in laps1.index
                has_2 = ln in laps2.index
                
                lt1 = f"{laps1.loc[ln, 'LapTime'].total_seconds():.3f}s" if has_1 and pd.notna(laps1.loc[ln, 'LapTime']) else "N/A"
                lt2 = f"{laps2.loc[ln, 'LapTime'].total_seconds():.3f}s" if has_2 and pd.notna(laps2.loc[ln, 'LapTime']) else "N/A"
                
                pos1 = f"P{int(laps1.loc[ln, 'Position'])}" if has_1 and pd.notna(laps1.loc[ln, 'Position']) else "N/A"
                pos2 = f"P{int(laps2.loc[ln, 'Position'])}" if has_2 and pd.notna(laps2.loc[ln, 'Position']) else "N/A"
                
                gap = "N/A"
                if has_1 and has_2:
                    t1 = laps1.loc[ln, 'Time']
                    t2 = laps2.loc[ln, 'Time']
                    if pd.notna(t1) and pd.notna(t2):
                        gap = f"{(t1 - t2).total_seconds():.3f}s"
                
                comp1 = str(laps1.loc[ln, 'Compound']) if has_1 else "N/A"
                comp2 = str(laps2.loc[ln, 'Compound']) if has_2 else "N/A"
                
                stat = "1"
                if has_1: stat = laps1.loc[ln, 'TrackStatus']
                elif has_2: stat = laps2.loc[ln, 'TrackStatus']
                
                lines.append(f"{int(ln)}, {gap}, {pos1}, {pos2}, {lt1}, {lt2}, {comp1}, {comp2}, {stat}")
        except Exception:
            pass

    try:
        all_laps_session = session.laps.dropna(subset=['LapTime'])
        if not all_laps_session.empty:
            max_lap = all_laps_session['LapNumber'].max()
            if max_lap > 10:
                first_quarter_lap = max_lap * 0.25
                last_quarter_lap = max_lap * 0.75
                early_laps = all_laps_session[all_laps_session['LapNumber'] <= first_quarter_lap]
                late_laps = all_laps_session[all_laps_session['LapNumber'] >= last_quarter_lap]
                
                if not early_laps.empty and not late_laps.empty:
                    early_best = early_laps['LapTime'].dt.total_seconds().min()
                    late_best = late_laps['LapTime'].dt.total_seconds().min()
                    
                    if pd.notna(early_best) and pd.notna(late_best):
                        lines.append(f"\n=== Track Evolution ===")
                        lines.append(f"Early session best lap (first 25% laps): {early_best:.3f}s")
                        lines.append(f"Late session best lap (last 25% laps): {late_best:.3f}s")
                        diff = early_best - late_best
                        
                        if diff > 0:
                            lines.append(f"Track/Pace improved by ~{diff:.3f}s over the session.")
                        else:
                            lines.append(f"Track/Pace worsened by ~{-diff:.3f}s over the session.")
    except Exception:
        pass

    return "\n".join(lines)
