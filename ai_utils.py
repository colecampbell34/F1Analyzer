import os
import json
import time
import hashlib
import threading
from datetime import datetime, timezone
from collections import defaultdict
from dotenv import load_dotenv
from data import get_track_status_events, get_best_lap, get_pit_stop_data, get_driver_info, get_teammate_from_info

# --- GEMINI API SETUP ---
load_dotenv()
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
AI_ENABLED = bool(GEMINI_API_KEY)

# --- Model Configuration ---
GEMINI_MODELS = [
    'gemini-3-flash-preview',
    'gemini-3.1-flash-lite-preview',
    'gemini-2.5-flash-lite',
    'gemini-2.5-flash'
]

# --- Thread lock for all rate-limiting state ---
_RATE_LIMIT_LOCK = threading.Lock()

# --- Rate Limiting (User-Specific Daily Limit) ---
_USER_DAILY_USAGE = defaultdict(int)  # IP → count
USER_DAILY_LIMIT = 10
_daily_reset_date = None

# --- Response Cache (disk-backed for persistence across restarts) ---
_AI_CACHE_DIR = 'ai_cache'
_AI_CACHE_FILE = os.path.join(_AI_CACHE_DIR, 'responses.json')
_AI_CACHE_LOCK = threading.Lock()
_AI_RESPONSE_CACHE = {}  # cache_key → response_text
MAX_CACHE_SIZE = 100


def _load_cache_from_disk():
    """Load the AI response cache from disk on startup."""
    global _AI_RESPONSE_CACHE
    try:
        if os.path.exists(_AI_CACHE_FILE):
            with open(_AI_CACHE_FILE, 'r', encoding='utf-8') as f:
                _AI_RESPONSE_CACHE = json.load(f)
            # Enforce max size
            if len(_AI_RESPONSE_CACHE) > MAX_CACHE_SIZE:
                keys = list(_AI_RESPONSE_CACHE.keys())
                for k in keys[:len(keys) - MAX_CACHE_SIZE]:
                    del _AI_RESPONSE_CACHE[k]
    except (json.JSONDecodeError, IOError):
        _AI_RESPONSE_CACHE = {}


def _save_cache_to_disk():
    """Persist the AI response cache to disk."""
    try:
        os.makedirs(_AI_CACHE_DIR, exist_ok=True)
        with open(_AI_CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(_AI_RESPONSE_CACHE, f, ensure_ascii=False)
    except IOError:
        pass


# Load cache from disk on module import
_load_cache_from_disk()


def check_user_limit(ip):
    """Checks and increments the daily request count for a specific IP.
    
    Returns (allowed, current_count).
    """
    global _daily_reset_date
    today = datetime.now(timezone.utc).date()

    with _RATE_LIMIT_LOCK:
        # Reset all users' daily counts at midnight UTC
        if _daily_reset_date != today:
            _USER_DAILY_USAGE.clear()
            _daily_reset_date = today

        current_usage = _USER_DAILY_USAGE[ip]
        if current_usage >= USER_DAILY_LIMIT:
            return False, current_usage

        _USER_DAILY_USAGE[ip] += 1
        return True, _USER_DAILY_USAGE[ip]


def _cache_key(session_context, question):
    """Generate a cache key from full session context + normalized question.

    Uses SHA-256 of the full context string to avoid collisions between
    sessions with similar headers (e.g. same drivers at consecutive races).
    """
    q_normalized = question.lower().strip()
    raw = (session_context or '') + '||' + q_normalized
    return hashlib.sha256(raw.encode()).hexdigest()


def get_cached_response(session_context, question):
    """Returns cached response if an exact normalized match exists, else None."""
    key = _cache_key(session_context, question)
    with _AI_CACHE_LOCK:
        return _AI_RESPONSE_CACHE.get(key)


def store_cached_response(session_context, question, response):
    """Store a response in the cache and persist to disk. Evicts oldest entries if cache is full."""
    with _AI_CACHE_LOCK:
        if len(_AI_RESPONSE_CACHE) >= MAX_CACHE_SIZE:
            # Evict the oldest entry (first inserted key)
            oldest_key = next(iter(_AI_RESPONSE_CACHE))
            del _AI_RESPONSE_CACHE[oldest_key]
        key = _cache_key(session_context, question)
        _AI_RESPONSE_CACHE[key] = response
        _save_cache_to_disk()


def build_ai_prompt(session_context, question, history=None):
    """Builds the complete prompt for the Gemini API call.
    
    Keeps prompt engineering logic centralized in the AI module.
    """
    # Build conversation context from history
    history_text = ""
    if history:
        history_text = "\n\n=== PREVIOUS Q&A ===\n"
        for h in history[-3:]:  # last 3 exchanges for context
            history_text += f"Q: {h['question']}\nA: {h['answer'][:1500]}...\n\n"

    prompt = (
        "You are an expert Formula 1 data analyst. "
        "Try to sound a little bit smarter than you are but dont make any wild claims. "
        "The session data below is the AUTHORITATIVE source of truth. "
        "Do not make any claims that are not supported by the data. "
        "IMPORTANT: The driver-team assignments at the top of the session data are definitive — "
        "do NOT override them with your training knowledge. "
        "Teams and driver lineups change every season; always trust the data, not your priors.\n\n"
        
        "=== ANALYSIS GUIDELINES ===\n"
        "Terminology: Use proper F1 terms like 'undercut', 'overcut', 'tyre delta', 'drop-off', 'cliff', and 'track evolution'.\n"
        "Strategy & Pace: Note that tyre degradation rates provided are already fuel-corrected (0.06s/lap factor implies positive numbers mean degradation). "
        "Exclude laps affected by Safety Cars, VSCs, or Red Flags from pure performance comparisons, as they artificially inflate times. "
        "Use the 'Teammate Benchmarks' to distinguish between a driver's individual performance and the car's inherent pace.\n"
        "Contextual Awareness: Consult the 'Session Narrative' to explain sudden pace changes or strategic shifts (e.g., 'the pace dropped after the incident at [00:45]'). "
        "Use the 'Full Field Classification' to provide context on where the drivers finished relative to the winner and the rest of the field.\n"
        "Weather: If rain is detected, explicitly account for it when analyzing sudden drops in pace or strategies (like switching to Inters/Wets).\n"
        "State limitations plainly: If data is missing (N/A), say so. Don't speculate.\n"
        "Handle Safety Car transits: If multiple 'pit visits' occur in consecutive laps under a Safety Car without a tire compound change, treat them as pit lane transits (incident avoidance), not strategic stops.\n"
        "Formatting: Use bullet points for driver comparisons and bold key metrics (like lap times and Deltas) for readability. "
        "Do not start with filler phrases like 'Based on the data...'; get straight to the analysis.\n\n"
        
        "Answer the user's question with detailed, data-driven analysis, reference specific numbers, and be thorough and conclusive.\n\n"
        "=== SESSION DATA ===\n"
        f"{session_context}\n"
        f"{history_text}\n"
        "=== USER QUESTION ===\n"
        f"{question}"
    )
    return prompt



def _get_field_summary(session):
    """Returns a text summary of the full finishing order and key field stats."""
    import pandas as pd 
    lines = ["=== FULL FIELD CLASSIFICATION ==="]
    try:
        if getattr(session, 'results', None) is not None and not session.results.empty:
            res = session.results.sort_values('Position')
            for _, row in res.iterrows():
                pos = row.get('Position')
                abbr = row.get('Abbreviation', '')
                team = row.get('TeamName', '')
                status = row.get('Status', 'Finished')
                
                # Gap to leader
                time_val = row.get('Time')
                if pd.notna(time_val) and isinstance(time_val, pd.Timedelta):
                    gap = f"+{time_val.total_seconds():.3f}s" if pos > 1 else "LEADER"
                else:
                    gap = status if status != 'Finished' else ""

                # Pit stops for this driver
                pits = 0
                try:
                    pits = len(session.laps.pick_drivers(abbr).pick_wo_box().pick_pit_stops())
                except Exception:
                    pass

                line = f"P{int(pos) if pd.notna(pos) else 'N/A'}: {abbr} ({team}) | {gap}"
                if pits > 0:
                    line += f" | {pits} stops"
                lines.append(line)
        else:
            lines.append("Full classification data unavailable.")
    except Exception:
        lines.append("Error fetching full classification.")
    return "\n".join(lines)


def _get_starting_grid(session):
    """Extracts official starting grid positions for all drivers."""
    import pandas as pd
    lines = ["=== OFFICIAL STARTING GRID ==="]
    try:
        if getattr(session, 'results', None) is not None and not session.results.empty:
            # Sort by GridPosition (handles cases where they started from pits etc)
            res = session.results.sort_values('GridPosition')
            for _, row in res.iterrows():
                grid_pos = row.get('GridPosition')
                if pd.isna(grid_pos) or grid_pos <= 0:
                    continue
                abbr = row.get('Abbreviation', '')
                lines.append(f"P{int(grid_pos)}: {abbr}")
        else:
            lines.append("Starting grid data unavailable.")
    except Exception:
        lines.append("Error fetching starting grid.")
    return "\n".join(lines)


def _get_teammate_benchmark(session, driver_abbr):
    """Returns key performance stats for a driver's teammate to provide car-performance baseline."""
    import pandas as pd  
    try:
        driver_info = get_driver_info(session)
        teammate = get_teammate_from_info(driver_abbr, driver_info)
        if not teammate:
            return f"No teammate data found for {driver_abbr}."

        res = session.results[session.results['Abbreviation'] == teammate]
        if res.empty:
            return f"Teammate {teammate} data unavailable."
        
        row = res.iloc[0]
        pos = row.get('Position')
        p_str = f"P{int(pos)}" if pd.notna(pos) else "DNF/Unknown"
        
        best_lap = get_best_lap(session, teammate)
        bl_str = f"{best_lap['LapTime'].total_seconds():.3f}s" if best_lap is not None and pd.notna(best_lap['LapTime']) else "N/A"
        
        # Avg Pace
        avg_pace = "N/A"
        try:
            tl = session.laps.pick_drivers(teammate).pick_wo_box().pick_track_status('1')
            if not tl.empty:
                avg_pace = f"{tl['LapTime'].dt.total_seconds().mean():.3f}s"
        except Exception:
            pass

        return f"Teammate {teammate} Baseline: Finished {p_str}, Best Lap {bl_str}, Avg Pace {avg_pace}"
    except Exception:
        return f"Error fetching teammate benchmark for {driver_abbr}."


def _get_session_narrative(session):
    """Extracts high-level race events from session messages (Overtakes, Flags, Retirements)."""
    import pandas as pd  
    lines = ["=== SESSION NARRATIVE (High-Level Events) ==="]
    try:
        if not hasattr(session, 'messages') or session.messages is None or session.messages.empty:
            return ""
        
        # Filter for interesting categories
        # FastF1 messages usually have 'Category' and 'Message'
        # Categories: 'Flag', 'Safety Car', 'Decision', 'Incident', 'Other'
        interesting = session.messages.copy()
        
        # Heuristic: exclude repetitive/low-info messages
        exclude_keywords = ['DRS ENABLED', 'DRS DISABLED', 'TRACK LIMITS', 'METEOROLOGICAL', 'WIND']
        
        for _, row in interesting.iterrows():
            msg = str(row.get('Message', '')).upper()
            if any(k in msg for k in exclude_keywords):
                continue
            
            # Focus on Flags, Overtakes (rare in messages but sometimes noted), Incidents, decisions
            cat = str(row.get('Category', '')).lower()
            if cat in ['flag', 'safety car', 'incident', 'decision']:
                # Format time if possible
                time_val = row.get('Time')
                t_str = ""
                if pd.notna(time_val):
                    if isinstance(time_val, pd.Timedelta):
                        total_secs = time_val.total_seconds()
                        mins = int(total_secs // 60)
                        secs = int(total_secs % 60)
                        t_str = f"[{mins:02d}:{secs:02d}] "
                    else:
                        t_str = f"[{str(time_val)}] "
                
                lines.append(f"{t_str}{msg}")
        
        if len(lines) == 1:
            return "" # No interesting events found
            
        # Limit to last 50 events to avoid bloating if race was chaotic
        if len(lines) > 51:
            lines = lines[:1] + lines[-50:]
            
    except Exception:
        pass
    return "\n".join(lines)


def _gather_session_context(session, session_type, driver1, driver2):
    """Builds a comprehensive text summary of the session data to feed to the LLM as context."""
    import pandas as pd
    import numpy as np
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

    # Teammate Context (Benchmark)
    lines.append("=== TEAMMATE BENCHMARKS ===")
    lines.append(_get_teammate_benchmark(session, driver1))
    lines.append(_get_teammate_benchmark(session, driver2))
    lines.append("")

    # Full Field Classification
    lines.append(_get_field_summary(session))
    lines.append("")
    
    # Starting Grid
    lines.append(_get_starting_grid(session))
    lines.append("")

    # Session Narrative
    narrative = _get_session_narrative(session)
    if narrative:
        lines.append(narrative)
        lines.append("")

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
