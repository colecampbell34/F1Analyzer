# OpenF1 Data-Source Migration Plan

**Status:** Complete — provider migration, live coverage audit, and desktop/mobile browser smoke passed  
**Scope:** Replace FastF1 as the required data provider for completed 2023+
sessions while retaining the dashboard’s existing analysis and UX as closely
as the published data supports.

## 1. Goal and success definition

The app must be able to load a completed Formula 1 session from 2023 onward and
provide the existing driver-comparison workflow without requiring F1 TV or
FastF1 authentication. OpenF1 is the primary source for session, timing,
telemetry, position, weather, tyre, pit, race-control, session-result, and
starting-grid data. Jolpica-F1 is an optional fallback/cross-check for fields
or sessions where OpenF1 data is absent or incomplete, not a required source
for the core results/grid workflow.

“Essentially all functionality” means preserving the current analysis views,
their controls, and their URLs—not necessarily preserving FastF1’s Python
objects or every FastF1-derived field. Where exact parity cannot be supported
by documented fields, show an explicit, narrow limitation or a clearly labeled
estimate. Never silently present a reconstructed or missing value as official.

### Requirements for this plan

- **REQ-001 — No paid authentication:** Completed 2023+ sessions load without
  F1 TV credentials or authenticated FastF1 requests.
- **REQ-002 — Session and driver selection:** Users can select a year, event,
  session, and two drivers; the latest completed race and driver shortcuts
  continue to work.
- **REQ-003 — Telemetry comparison:** Preserve lap selection and plots for
  speed, throttle, brake, gear, RPM, delta, and any available DRS channel.
- **REQ-004 — Position and replay:** Preserve the track-position sidecar,
  browser-side lap replay, and replay controls when both selected laps have
  sufficient location samples.
- **REQ-005 — Track Map and Driver DNA:** Preserve dominance, speed/braking
  overlays, and relative driver-trait analysis. Prefer numbered corner
  geometry linked by OpenF1 meetings when it aligns with telemetry; retain a
  disclosed heuristic fallback.
- **REQ-006 — Race & Pace:** Preserve field pace distribution, selected-driver
  race gaps and positions, grid-to-finish summary, pit/strategy-call context,
  and applicable race/sprint behavior.
- **REQ-007 — Strategy and degradation:** Preserve compound/stint timelines,
  tyre degradation analysis, weather overlay, and pit/compound transitions.
- **REQ-008 — Race context and AI:** Continue supplying grounded classification,
  teammate, selected-lap, strategy, weather, and race-control context to AI.
  The model must not infer unsupported telemetry claims.
- **REQ-009 — Resilience and rate safety:** Validate upstream records, cache
  historical responses, bound request volume, handle 429/network/partial-data
  responses explicitly, and keep one provider failure from taking down the
  whole app.
- **REQ-010 — Existing UX contract:** Preserve component IDs, tabs, URL
  parameters, responsive layout, feedback, chart downloads, loading states,
  and unrelated app behavior.
- **REQ-011 — Verifiable parity:** Add provider-level and behavioral tests that
  prove supported features work without invoking FastF1.

## 2. Research basis and constraints

The implementation agent should recheck these sources before coding because
third-party API behavior and limits can change:

- [OpenF1 API documentation](https://openf1.org/docs/) — documented endpoints,
  fields, historical access, and data semantics.
- [OpenF1 API overview](https://openf1.org/) — published FAQ and rate limits.
- [OpenF1 source repository](https://github.com/br-g/openf1) — API
  implementation and endpoint/schema detail where docs are ambiguous.
- [Jolpica-F1 docs](https://github.com/jolpica/jolpica-f1/blob/main/docs/README.md)
  and [rate limits](https://github.com/jolpica/jolpica-f1/blob/main/docs/rate_limits.md).

Current documented operating constraints to design around:

1. OpenF1 historical data from 2023 onward is described as free and available
   without authentication. OpenF1 classifies data as live until 30 minutes
   after a session ends; this app’s supported workflow is completed sessions,
   not live timing.
2. OpenF1 currently publishes free limits of 3 requests/second and 30
   requests/minute. Treat HTTP 429 as an expected condition, not as a reason to
   retry in a tight loop.
3. Car and location data are sampled at approximately 3.7 Hz. This supports
   detailed comparisons and client-side replay, but not sub-sample precision.
   Preserve the existing visual detail, but do not claim greater precision
   than the source supports.
4. OpenF1 documents `session_result` and `starting_grid` in addition to
   meetings, sessions, drivers, laps, car_data, location, intervals, position,
   pit, stints, weather, race_control, and other endpoints. `session_result`
   supplies final position, DNF/DNS/DSQ flags, completed laps, race duration
   and gap; for qualifying it supplies Q1/Q2/Q3 duration and gap arrays.
   `starting_grid`, queried with the qualifying-session key, supplies grid
   position. These endpoints close the main results/grid gap identified in the
   first research pass. OpenF1 should be the primary source for result and
   grid data; Jolpica is fallback/cross-check only.
5. OpenF1 meetings include a `circuit_info_url` pointing to
   `api.multiviewer.app`; a retrieved 2023 Monaco payload contains numbered
   corners with `trackPosition` coordinates, angle, and length. This offers a
   promising replacement for FastF1 circuit markers, but the provider is
   separate and its coordinate alignment with OpenF1 location samples must be
   verified before claiming exact overlay parity. Keep a heuristic fallback.
6. A direct documentation/API spot-check returned incomplete lap fields for a
   historical lap. All records must therefore be validated field-by-field.
7. OpenF1 documents location coordinates as approximate, sampled at about
   3.7 Hz, without lateral placement, and with an arbitrary origin. They
   support relative progress/shape views, but do not imply calibrated absolute
   circuit coordinates. Position/map features must be quality-gated and
   alignment-tested against the circuit payload.
8. Pit `stop_duration` is documented only from the 2024 United States Grand
   Prix onward. For 2023 through that point, `lane_duration` may exist but is
   total pit-lane time, not stationary tyre-service time. Never substitute one
   for the other.
9. OpenF1's free tier publishes 3 requests/second and 30 requests/minute; live
   access is paid, and a session is treated as live through 30 minutes after
   it ends. Completed historical sessions are the intended use.
10. The pre-migration repository had a narrow selected-lap OpenF1 fallback in
    `openf1_fallback.py`, coupled to FastF1 session and lap objects. The
    migration replaced it with the provider-neutral trace loader in
    `session_data.py`.
11. OpenF1 `laps` does not document FastF1's `IsAccurate`, `PitInTime`, or
    per-lap `TrackStatus` columns. Pit endpoint and race-control messages can
    reconstruct useful exclusions/status overlays, but deleted-lap accuracy
    and exact per-lap green/yellow/SC filtering are not guaranteed to match
    FastF1. This is the clearest remaining data-parity limitation for the
    pace/strategy analysis.
12. The linked circuit-info response is a separate MultiViewer API, not an
    OpenF1 endpoint. In this check it returned circuit corner `trackPosition`
    coordinates, but we have not verified the terms, version stability,
    availability across every 2023+ circuit, or coordinate transform against
    OpenF1's arbitrary-origin location stream. Treat circuit geometry as an
    optional dependency with a cache and heuristic fallback, not as a proven
    OpenF1 guarantee.
13. `session_result` is documented to become available a few minutes after
    official results publish. Treat a not-yet-present result as pending or
    unavailable, not as an API failure that prevents telemetry/laps from
    rendering. Do not interpret a 404 for an invalid/nonexistent session key
    as an endpoint coverage failure; validate requested keys against the
    sessions endpoint before diagnosing result availability.
14. OpenF1's `starting_grid` describes the upcoming race's grid and is queried
    using the qualifying session key. Do not assume it is a universal
    per-session starting-position endpoint for every practice, sprint, or
    qualifying view. The sample payload has grid position and qualifying lap
    duration, not penalty explanations or a full classification status.
15. The paced sample measured endpoint row counts and payload sizes for five
    sessions and checked selected-lap car/location timestamp alignment. It did
    not establish completeness for every historic session/lap or maximum
    pagination/response caps. Spatial alignment between circuit corner
    coordinates and OpenF1's arbitrary-origin location data also remains
    unverified. Do not generalize the sample to every session.

### Endpoint checks performed

The read-only probe completed against five historical sessions, paced at a
minimum 0.45 seconds between requests and a maximum of 25 requests per minute
per probe process. The five-session coverage runs made 87 requests. A focused
Monaco trace recheck recorded selected-lap car/location byte sizes below.
Response sizes are JSON bytes; `not found` means the endpoint returned no data
for that session and is handled as optional coverage.

| Session | Drivers | Laps | Result | Stints | Pits | Weather | Position | Intervals | Race control | Grid |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2023 Monaco Race, key 9094 | 20 | 1,516 / 702,382 B | 20 / 3,656 B | 57 / 8,361 B | not found (404) | 176 / 37,791 B | 300 / 34,379 B | 30,074 / 4,259,391 B | 244 / 63,150 B | 20 / 1,886 B |
| 2023 Monaco Qualifying, key 9090 | 20 | 420 / 192,177 B | 20 / 3,904 B | 96 / 13,746 B | not found | 86 / 18,474 B | 1,713 / 195,845 B | not found | 50 / 12,340 B | 20 / 1,886 B |
| 2023 Monaco Practice 3, key 9089 | 20 | 392 / 180,489 B | 20 / 3,359 B | 63 / 9,023 B | not found | 72 / 15,457 B | 693 / 79,258 B | not found | 28 / 6,571 B | 20 / 1,886 B |
| 2024 Bahrain Race, key 9472 | 20 | 1,129 / 563,928 B | 20 / 3,665 B | 63 / 9,036 B | 43 / 7,686 B | 157 / 33,629 B | 698 / 79,876 B | 29,844 / 4,214,545 B | 71 / 18,425 B | 20 / 1,886 B |
| 2024 China Sprint, key 9672 | 20 | 379 / 177,967 B | 20 / 3,668 B | 21 / 3,041 B | 1 / 180 B | 80 / 17,196 B | 209 / 23,936 B | 7,906 / 1,108,820 B | 21 / 5,646 B | 20 / 1,886 B |

`starting_grid` was available via the linked qualifying session key (9090 for
Monaco, 9468 for Bahrain, and sprint qualifying key 9668 for the China sprint).
The Monaco 2023 race had 30,008 interval rows with non-null `gap_to_leader`
and 29,897 with non-null interval values; China Sprint had 7,906 interval
records. Optional endpoint gaps are session-specific: Monaco 2023 pit data was
missing despite stints, and the qualifying/practice sessions returned no pit
or interval rows. Bahrain and China returned pit data. These absences do not
block laps, results, or telemetry.

For the 2023 Monaco Race selected-lap trace, the drivers endpoint returned 20
records / 7,724 B. The selected car/location windows were:

| Driver/lap | Car data records / bytes / rate | Location records / bytes / rate | Car samples with location within 750 ms |
|---|---:|---:|---:|
| VER, lap 23 | 290 / 48,325 B / 3.74 Hz | 293 / 37,388 B / 3.78 Hz | 100% |
| ALO, lap 32 | 296 / 49,334 B / 3.78 Hz | 306 / 39,058 B / 3.91 Hz | 100% |

These are lap-window responses, not full-session car/location downloads.

Selected-lap `car_data` and `location` samples were also compared across the
five sessions. All ten inspected driver-lap pairs had timestamp matches within
750 ms for every car sample that could be paired. Observed rates were about
3.64–3.98 Hz. The probe checked temporal synchronization only: OpenF1
location uses an arbitrary origin, so alignment of MultiViewer corner
coordinates with the location coordinate frame is still unverified. The
heuristic corner-marker fallback remains required until a spatial transform
is independently validated. The circuit payload contained 19 Monaco, 15
Bahrain, and 16 China corner definitions.

Representative direct links:

- [2023 Monaco sessions](https://api.openf1.org/v1/sessions?year=2023&country_name=Monaco)
- [Monaco race result](https://api.openf1.org/v1/session_result?session_key=9094)
- [Monaco qualifying result](https://api.openf1.org/v1/session_result?session_key=9090)
- [Monaco starting grid](https://api.openf1.org/v1/starting_grid?session_key=9090)
- [Monaco 2023 circuit geometry](https://api.multiviewer.app/api/v1/circuits/22/2023)

The OpenF1 overview describes the project as intended for educational,
research, and non-commercial fan engagement; confirm applicable terms before
using it for a commercial service. The probe established representative
historical endpoint coverage, not completeness for every 2023+ session or lap.

### Coverage decision

**The provider migration is implemented with fixture contracts and a
representative live audit.** Five sessions across two seasons and four session
formats verified core endpoint rows, response sizes, selected-lap sampling,
and optional-data gaps. This is not an archive-wide completeness guarantee.
Spatial corner alignment remains unverified and the UI retains the disclosed
heuristic marker fallback. OpenF1 also does not expose FastF1's deleted-lap
accuracy or exact per-lap track-status flags; the app labels derived and
approximate analysis rather than claiming exact FastF1 parity.

## 3. Existing architecture and migration boundary

Pre-migration ownership (kept here to explain the refactor):

- `data.py`: FastF1 schedule/session loading, summaries, driver/result metadata,
  profiles, caches, preloads, and `get_shared_data`.
- `static_schedule.py`: static schedule and latest-race defaults (removed).
- `openf1_fallback.py`: selected-lap OpenF1 normalization coupled to FastF1
  objects (removed after its provider-neutral replacement was added).
- `telemetry_prep.py`: selected-lap selection, trace validation, trace caching,
  and comparison payloads.
- `callbacks.py`: year/event/session/driver selection, latest race, leaderboard,
  URL state, and common loading.
- `callbacks_telemetry.py`: telemetry figure, sidecar position, and playback.
- `callbacks_tabs.py`: track map, strategy, race & pace callbacks.
- `graphs_telemetry.py`, `graphs_trackmap.py`, `graphs_race.py`,
  `graphs_pace.py`, `strategy_insights.py`: graph and derived-analysis logic.
- `callbacks_ai.py`, `ai_utils.py`: selected-lap and whole-session AI context.
- `shared_cache.py`: optional Redis-backed cache for bounded derived traces.
- `layout.py`, `ui_utils.py`: stable UI IDs, empty/error states, and user-facing
  provider/data availability messaging.

### Architectural decision

Create a provider-neutral data boundary and refactor the downstream analysis to
consume explicit normalized records/DataFrames. Do **not** recreate the FastF1
`Session`/`Laps` API in a large compatibility shim. Current graph code depends
on FastF1-only methods (`pick_drivers`, `pick_wo_box`, `pick_track_status`,
`pick_stint`, `get_telemetry`, and `get_circuit_info`); emulating these methods
would hide provider semantics and make partial data look complete.

Prefer a small module such as `session_data.py` (or a clearly separated section
of `data.py` if keeping modules down is more consistent) with:

- `SessionRef`: normalized year, round, event name, country, session name,
  OpenF1 `meeting_key`/`session_key`, start/end timestamps, circuit metadata.
- `SessionBundle`: normalized drivers, optional official results/grid,
  normalized laps, optional weather, optional race-control messages, stints,
  pit stops, positions/intervals as requested, and source/completeness metadata.
- Provider functions for schedules, sessions, driver list, summary, lap data,
  selected-lap trace, weather, messages, stints, and pit stops.
- DataFrames should use dashboard-neutral, documented columns and ordinary
  pandas operations. Avoid a FastF1-shaped pseudo-object.
- Stable driver identity is `driver_number` within a session, mapped to
  `name_acronym` for current UI/graph labels. Do not key historical data only
  by an abbreviation.

Keep callback-facing functions in `data.py` temporarily as compatibility
facades, but have them return normalized data. Migrate consumers one surface
at a time. Remove FastF1-specific imports and dependency only after a repository
search and test prove no runtime path still uses it.

## 4. Provider-to-feature mapping and transformations

| App data need | OpenF1 source | Jolpica/supplement | Required normalization and limitations |
|---|---|---|---|
| Event/session picker | `meetings`, `sessions` | Optional schedule cross-check | Build stable year/event/session options; ignore canceled sessions and sessions not yet historical. Map display event names without assuming country alone uniquely identifies an event. |
| Driver picker/colors | `drivers` filtered by session | None required | Normalize number, acronym, full name, team, and team color. Validate duplicate/absent driver numbers. |
| Lap selector and lap metrics | `laps` | `laps`/qualifying/results for supplementary records | Normalize lap number, lap start, duration, sectors, speed traps, pit-out flag, and available segment data. Missing duration is not a valid fastest-lap candidate. |
| Clean-lap filtering | `laps.is_pit_out_lap`, `pit`, `race_control` | Optional Jolpica pit-stop cross-check | OpenF1 does not document FastF1-equivalent `IsAccurate`, `PitInTime`, or per-lap `TrackStatus` fields. Reconstruct pit and flag exclusions from pit/race-control records where reliable; document that deleted/inaccurate laps and exact yellow/SC/VSC filtering may not match FastF1. |
| Selected-lap telemetry | `car_data` filtered by session, driver, and time window | None | Normalize timestamps and speed/throttle/brake/gear/RPM/DRS. Brake uses 0/100 in OpenF1; convert to 0/1 where existing graph logic expects FastF1 semantics. Retain DRS separately. |
| Selected-lap geometry/replay | `location` filtered by session, driver, and time window | Optional circuit geometry source | Normalize X/Y and timestamps; merge with car samples by time using a bounded nearest-time tolerance. Position is optional for speed analysis but mandatory for position charts/replay. |
| Race positions/intervals | `position`, `intervals` | Jolpica race classification as optional cross-check | Position endpoint records initial placement and subsequent changes; use stepwise timestamp interpretation. Intervals are documented for race sessions and include gap to leader and car ahead; do not assume practice/qualifying coverage. |
| Published session results | `session_result` | Jolpica `results`, `qualifying`, and `sprint` as fallback/cross-check | OpenF1 gives final position, DNF/DNS/DSQ, laps, points where present, race duration/gap; qualifying duration/gap are Q1/Q2/Q3 arrays. Normalize arrays without flattening away the qualifying phase. Validate `+N LAP(S)` strings and nullable durations. |
| Published starting grid | `starting_grid` queried by the qualifying session key | Jolpica grid/result data as fallback/cross-check | OpenF1 returns position and driver number (and qualifying lap duration); join with session drivers. Check race weekend/session mapping, penalty-adjusted grid semantics, pit-lane starts, and missing positions against representative events. |
| Compound/stint/tyre age | `stints` | Optional Jolpica pit-stop cross-check | Normalize `lap_start`, `lap_end`, compound, and tyre age at stint start. Fill per-lap compound/stint via interval join. Stint boundaries can be null or edge-case affected; validate and keep unknowns. |
| Pit events | `pit` | Jolpica `pitstops` | Normalize lap and timing. `stop_duration` is stationary time only from 2024 United States GP onward; `lane_duration` is full pit-lane time. Use pit events plus stint transitions for service-call context and preserve source duration semantics. |
| Weather | `weather` | None required | Normalize timestamp, track/air temperature, humidity, pressure, wind, rainfall. Rainfall may be numeric/bool; normalize explicitly. Missing weather must not block pace/strategy charts. |
| Race-control narrative/status | `race_control` | None required | Normalize event timestamp/category/flag/scope/sector/message. Derive track-status time intervals and lap overlays with explicit heuristics; distinguish “no event found” from “messages unavailable.” |
| Circuit corners | `meetings.circuit_info_url` links to MultiViewer circuit-info JSON | The linked MultiViewer circuit payload | A retrieved Monaco 2023 payload has numbered corners with `trackPosition`, angle, and length. Normalize into the existing corner schema, verify the coordinate transform against OpenF1 location, cache it, and use heuristic speed-dip markers only when missing/unmatched. |

## 5. Normalized data contract

Before migrating consumers, document and test a canonical schema. The initial
schema should cover the following fields; optional values remain nullable.

### Session and driver records

- Session: `year`, `round`, `event_name`, `country_name`, `session_name`,
  `session_key`, `meeting_key`, `date_start`, `date_end`, `circuit_key`,
  `circuit_short_name`, `is_cancelled`.
- Driver: `driver_number` (string-normalized), `abbreviation`, `full_name`,
  `team_name`, `team_colour`.
- Result (optional): `position`, `grid_position`, `status`, `points`,
  `classified_laps`, `race_time`, `gap`, plus session driver identity.
  Prefer OpenF1 `session_result` / `starting_grid`; retain source and distinguish
  official result values from derived order. Preserve qualifying phase-specific
  result arrays instead of treating them as one scalar.

### Lap records

- Identity: `driver_number`, `abbreviation`, `lap_number`.
- Timing: `date_start`, `lap_duration`, `duration_sector_1/2/3`,
  `i1_speed`, `i2_speed`, `st_speed`.
- State: `is_pit_out_lap`, `compound`, `stint_number`, `tyre_age`,
  `pit_in`, `pit_out`, `position`, `track_status` (derived only, with
  provenance).
- Preserve original source columns where useful, but do not leak provider
  naming differences to graph code.

### Telemetry trace

- Required for speed analysis: `Time`, `Distance`, `Speed`.
- Optional car channels: `Throttle`, normalized `Brake`, `nGear`, `RPM`, `DRS`.
- Optional position channels: `X`, `Y`.
- Provenance: `source`, `sample_count`, `position_sample_count`,
  `sampling_hz` when known, and quality flags such as `has_position`,
  `has_throttle`, `has_brake`.
- `Distance` can be approximated by integrating speed over elapsed time if
  absent. Mark it as derived and test drift. Do not claim it equals official
  circuit distance.
- Never interpolate through long gaps or use a nearest-time merge with an
  unbounded tolerance.

### Whole-session supporting data

- Weather frame: timestamp plus the normalized weather fields above.
- Race-control frame: timestamp and normalized category, flag, scope, sector,
  lap number, and message.
- Stints and pits: normalized records from separate endpoints; do not
  fabricate per-lap tyre compound or stop duration when the input is missing.
- `SessionBundle` must expose endpoint availability/completeness metadata so
  callbacks can produce meaningful partial-data UI and AI notes.

## 6. Cache, rate-limit, and failure policy

1. Add a single HTTP client in the provider module with explicit connect/read
   timeout, a descriptive User-Agent, JSON response validation, and bounded
   response sizes. Do not log raw upstream response bodies or credentials.
2. Cache immutable historical metadata and whole-session endpoint payloads
   independently, keyed by provider, schema version, year/session key, and
   endpoint/query. Historical cache TTL can be long (for example, 30 days);
   keep a short configurable TTL for sessions that have only just completed.
3. Cache selected-lap traces by session key, driver number, lap number,
   schema version, and trace profile. Keep the existing bounded JSON-safe
   shared-cache design; never serialize provider objects, pickle DataFrames,
   or put raw session-wide car streams into Redis.
4. Enforce a request budget below the published API ceiling with a shared
   process-local limiter for local hosts and a conservative strategy for
   serverless deployments. Because process-local limits do not coordinate
   Vercel instances, rely on caching, endpoint batching, and `Retry-After`
   where present; do not claim a global limit without a managed shared store.
5. Handle 429 by respecting `Retry-After` if supplied and making at most a
   small number of delayed retries. Do not retry 4xx schema/not-found errors.
   Use bounded exponential backoff for transient 5xx/network errors.
6. Fetch whole-session low-volume records once where needed; fetch high-volume
   car/location data only for the selected drivers/laps, unless a view truly
   requires a bounded full-session stream.
7. On partial data: keep independent views usable. For example, missing weather
   must not block strategy pace; missing location must not block speed/throttle
   graphs; missing official results must not be presented as official
   classification.
8. Surface data limitations in the existing status/figure error UX. Keep
   provider errors sanitized and actionable.

## 7. Ordered implementation phases and executable tasks

Tasks follow dependency order. `[P]` means a task can run in parallel with
other `[P]` tasks in the phase after the preceding contract is agreed.

### Phase 1 — Provider feasibility and fixtures

**Exit gate:** fixtures, provider contracts, and a paced live sample establish
the provider schema and request behavior. The live audit covers five
representative sessions; full archive coverage is outside the guarantee.

- [x] T001 [Plan:1.1] Add sanitized, minimal OpenF1 JSON fixtures for one completed race and one qualifying session in `tests/fixtures/openf1/`; include sessions, drivers, laps, car data, location, stints, pits, weather, positions, intervals, and race-control examples with null/malformed/edge records.
- [x] T002 [Plan:1.1] Add sanitized OpenF1 `session_result` and `starting_grid` fixtures for race, qualifying, practice, and sprint contexts; include Q1/Q2/Q3 arrays, DNF/DNS/DSQ, lapped gaps, missing data, and penalty-adjusted or pit-lane grid cases. Add Jolpica fallback fixtures for matching race, qualifying, sprint, and pit-stop data.
- [x] T003 [P] [Plan:1.2] Create a read-only, deliberately paced endpoint probe script in `scripts/` that checks selected historical sessions’ endpoint availability, field population, response sizes, approximate request count, sample rates, and cross-endpoint timestamps; respect the published limits rather than intentionally generating 429s, and do not make it part of normal startup or tests.
- [x] T004 [P] [Plan:1.2] Add provider contract tests in `tests/` for endpoint response validation, query encoding, timestamps, unknown fields, empty responses, 429/Retry-After, and sanitized error handling.
- [x] T005 [Plan:1.3] Verify endpoint coverage against five completed sessions across two years and four formats (race, sprint, qualifying, practice); record the endpoint/field matrix, response sizes, sparse/missing data, circuit geometry checks, and source-specific exceptions above. **Accepted limitation:** selected car/location traces are temporally synchronized, but MultiViewer corner geometry has not been spatially aligned to OpenF1's arbitrary-origin coordinates; keep heuristic markers and disclose this limitation. The sample does not guarantee every archived session or lap is complete.

### Phase 2 — Provider-neutral data boundary

**Exit gate:** fixtures produce stable normalized session bundles; provider tests
pass with FastF1 absent from the code path.

- [x] T006 [Plan:2.1] Implement the OpenF1 HTTP client and response validators in `session_data.py` (or the agreed provider module), including User-Agent, timeouts, safe query operators, bounded retries, rate-limit handling, and sanitized errors.
- [x] T007 [Plan:2.2] Implement normalized `SessionRef`, `SessionBundle`, and endpoint DataFrame construction in `session_data.py`; document nullability and provenance for the schema in this plan or module docs.
- [x] T008 [Plan:2.3] Implement cached meetings/sessions/drivers retrieval and stable event/session mapping in `session_data.py`; exclude canceled sessions and gate availability to completed 2023+ sessions.
- [x] T009 [Plan:2.4] Implement OpenF1 `session_result` and `starting_grid` normalization in `session_data.py`, preserving qualifying phase arrays and status flags; add Jolpica client functions only as fallback/cross-check, with rate-limit handling, driver ID ↔ OpenF1 number/abbreviation mapping, sprint weekends, and data-not-found distinct from provider outage.
- [x] T010 [Plan:2.5] Implement session laps/stints/pits/weather/race-control/position/interval loading and linked circuit-info retrieval in `session_data.py` with lazy endpoint profiles and endpoint-level caching; avoid loading unrelated high-volume data for every tab and verify circuit/location coordinate alignment with fixture or live evidence.
- [x] T011 [Plan:2.6] Add normalized data-quality reporting (required/optional fields, valid row counts, source and quality notes) in `session_data.py`; distinguish unavailable, empty, malformed, and partially populated endpoint responses.
- [x] T012 [Plan:2.7] Add canonical conversion tests asserting source fixtures map to expected sessions, drivers, results, lap timing, compound/stints, pits, weather, and messages in `tests/`.

### Phase 3 — Selection and common application workflow

**Exit gate:** event/session/driver selection, latest race, leaderboard, and
existing URLs work using the new provider with no FastF1 import or request.

- [x] T013 [Plan:3.1] Replace FastF1 schedule lookup with normalized provider schedule retrieval in `data.py` and `callbacks.py`; ensure historical sessions are only offered once OpenF1 classifies them as historical and preserve existing year/event/session component IDs.
- [x] T014 [Plan:3.2] Adapt latest completed race defaults in `data.py` so the latest race is selected from supported completed OpenF1 sessions, with a clear no-session state and no current/live session selection; remove the obsolete `static_schedule.py`.
- [x] T015 [Plan:3.3] Adapt driver option, team color, teammate selection, top-two/closest shortcuts, and leaderboard callbacks in `data.py`, `callbacks.py`, `callbacks_shared.py`, `ux_helpers.py`, and `ui_utils.py` to consume normalized driver/results/lap tables.
- [x] T016 [Plan:3.4] Preserve the URL serialization/hydration contract and validate old bookmarked URLs for supported 2023+ sessions in `callbacks.py` and `tests/test_core_utils.py`.
- [x] T017 [Plan:3.5] Add callback tests for event selection, sessions with missing results, qualifying/session variants, race default selection, driver identity mapping, and safe error states in `tests/`.

### Phase 4 — Selected-lap telemetry, map, and replay

**Exit gate:** telemetry and position features render for fixture sessions; all
existing replay controls and URLs remain intact; poor/missing trace quality is
explained rather than silently substituted.

- [x] T018 [Plan:4.1] Replace `openf1_fallback.py` with a provider-neutral selected-lap trace loader in `session_data.py`; take `SessionRef` plus a normalized lap record, not FastF1 `Session`/`Lap` objects.
- [x] T019 [Plan:4.2] Normalize OpenF1 car/location samples into the canonical trace in `telemetry_prep.py` or the provider module; convert brake units, retain DRS, derive elapsed `Time`, and integrate speed for derived `Distance` with source-quality flags.
- [x] T020 [Plan:4.3] Update selected-lap choice, fastest-lap validity, exact lap-number behavior, fallback-lap rules, and comparison cache keys in `telemetry_prep.py` and `callbacks_shared.py`; never replace an explicitly selected lap number.
- [x] T021 [Plan:4.4] Update trace cache serialization/schema and invalidation in `telemetry_prep.py` and `shared_cache.py`; cache by session/driver/lap/source/schema and enforce existing bounded JSON-safe payload limits.
- [x] T022 [Plan:4.5] Adapt telemetry figures and playback data assembly in `callbacks_telemetry.py`, `graphs_telemetry.py`, `assets/scripts.js`, and `assets/custom.css` only where necessary; preserve speed, delta, throttle/brake, gear, RPM, position sidecar, play/pause/focus, and mobile behavior.
- [x] T023 [Plan:4.6] Adapt map/DNA and corner marker behavior in `graphs_trackmap.py` and `callbacks_tabs.py`; use the circuit payload linked by `circuit_info_url` for numbered corners when its coordinate frame aligns with the telemetry, otherwise retain explicitly heuristic speed-dip markers.
- [x] T024 [Plan:4.7] Add tests for car-only traces, position-complete traces, unsynchronized/missing location, short traces, null channels, brake normalization, distance integration, and exact lap selection in `tests/`.
- [x] T025 [Plan:4.8] Add regression tests for replay payload serialization and clientside replay state in `tests/` (and browser smoke coverage where practical), including a narrow/mobile and desktop viewport.

### Phase 5 — Strategy, pace, results, and race-status analysis

**Exit gate:** race, sprint, practice, and qualifying views behave correctly for
their applicable data; unsupported official fields remain visibly unavailable.

- [x] T026 [Plan:5.1] Refactor `strategy_insights.py` to consume normalized lap, stint, pit, and position records; preserve stint summary, compound changes, pit transitions, and before/after position context without FastF1 lap methods.
- [x] T027 [Plan:5.2] Refactor strategy and degradation figures in `graphs_race.py` to use normalized laps/stints/weather; preserve clean-lap filtering, tyre-compound visualization, fuel-corrected trend, weather temperature, and rain overlays while explicitly marking approximations.
- [x] T028 [Plan:5.3] Refactor field pace distribution in `graphs_pace.py` to use normalized lap records, session-type rules, OpenF1 `session_result` ordering when available, and derived fastest/median ordering for sessions without results.
- [x] T029 [Plan:5.4] Refactor race gaps, positions, pit markers, and grid-to-finish summary in `graphs_race.py` and `callbacks_tabs.py`; use OpenF1 `session_result` and `starting_grid` as the primary classification/grid source, timestamped position/interval samples as applicable, and Jolpica only as a fallback/cross-check.
- [x] T030 [Plan:5.5] Implement race-control-to-lap status interval derivation in `session_data.py` or `strategy_insights.py`; map message timestamps to lap intervals with documented heuristics for SC, VSC, red flag, and yellow flags, and retain unknown/unmapped events without falsely marking laps.
- [x] T031 [Plan:5.6] Update `get_track_status_events` replacement and all graph consumers to use derived status records; do not retain FastF1 `TrackStatus` semantics implicitly.
- [x] T032 [Plan:5.7] Add strategy/pace/race tests for missing weather, null stint boundaries, pit-entry vs stationary duration, red flag/session interruption, lapped intervals, invalid/deleted laps where no source flag exists, DNS/DNF, sprint, qualifying, and practice in `tests/`.

### Phase 6 — AI context, availability UX, and documentation

**Exit gate:** AI remains grounded in provider evidence and all user-facing
availability/errors explain limits without exposing raw upstream responses.

- [x] T033 [Plan:6.1] Refactor `_build_ai_session_context` in `callbacks_ai.py` and `_gather_session_context` plus helper functions in `ai_utils.py` to consume normalized `SessionBundle` and canonical traces rather than FastF1 objects.
- [x] T034 [Plan:6.2] Preserve AI classification, grid, teammate, tyre stint, pit, race narrative, weather, selected-lap sectors, telemetry, pace, and race context; add explicit provenance/quality notes and the instruction not to infer unsupported telemetry or official result claims.
- [x] T035 [Plan:6.3] Update `_friendly_error`, dashboard provenance/data note, and any affected layout/status rendering in `ui_utils.py`, `layout.py`, and callback modules for 2023+ coverage, historical-only availability, delayed post-session access, and per-view missing data.
- [x] T036 [P] [Plan:6.4] Update `README.md`, `docs/ARCHITECTURE.md`, `docs/DEPLOYMENT.md`, `docs/RENDER.md`, and `AGENTS.md` for OpenF1/Jolpica data flow, attribution/terms, data delays, request budgets, caching, and supported 2023+ range.
- [x] T037 [Plan:6.5] Add AI context tests for full, telemetry-missing, weather-missing, race-control-missing, and results-supplement-missing sessions in `tests/`.

### Phase 7 — Remove FastF1 runtime dependency and validate end-to-end

**Exit gate:** the offline unit suite and Ruff pass, live representative
sessions load, core Flask routes return 200, desktop/mobile browser flows pass,
and normal runtime paths have no FastF1 dependency. Spatial circuit-corner
alignment remains an explicit limitation with a heuristic fallback.

- [x] T038 [Plan:7.1] Search the repository for FastF1 imports, `fastf1.` calls, FastF1 object methods/assumptions, cache setup, worker warmers, and FastF1-specific environment variables; migrate any remaining runtime call sites in `app.py`, `scripts/`, and tests or document intentional developer-only tools.
- [x] T039 [Plan:7.2] Remove `fastf1` from `requirements.txt` and remove obsolete FastF1 cache setup/pruning/warmup configuration in `data.py`, `app.py`, `scripts/warm_fastf1_session.py`, README, deployment docs, and environment examples only after T038 proves it is not needed.
- [x] T040 [Plan:7.3] Add integration tests that replay fixture-backed full workflows through the public data facade and callbacks without live network access; assert all supported views build successfully and missing-data cases return clear errors/partial states.
- [x] T041 [Plan:7.4] Run `python -m unittest discover -s tests -q` and `python -m ruff check .`; fix only migration-caused failures and preserve unrelated baseline behavior.
- [x] T042 [Plan:7.5] Run paced, live, read-only checks against representative historical sessions within OpenF1's published request budget; verify `/`, `/health`, and `/healthz` return 200 and exercise live telemetry plus strategy/race callbacks. Coverage includes 2023 Monaco Race/Qualifying/Practice 3, 2024 Bahrain Race, and 2024 China Sprint; the endpoint matrix and source-specific gaps are recorded above.
- [x] T043 [Plan:7.6] Run opt-in Playwright smoke tests with `RUN_BROWSER_SMOKE=1` at desktop (1440×1000) and mobile (390×844). Both cases passed URL restoration, live telemetry rendering, replay controls, chart download, feedback modal, Track Map, and Race & Pace navigation. Desktop also selected numbered laps and exercised Track Map overlay modes. The run used a temporary Playwright/Chromium install outside the repository; the opt-in dependency is not added to application requirements.
- [x] T044 [Plan:7.7] Review final diff for provider-data leakage, raw API error bodies, secrets, generated cache/fixture dumps, accidental component ID changes, and unnecessary FastF1 leftovers; report remaining parity limitations with evidence.

## 8. Detailed view-by-view acceptance criteria

Implementation status: fixture contracts, representative live sessions, and desktop/mobile browser interactions were verified. These checks are representative, not an archive-wide guarantee. Treat the following as explicit provider limits:

1. **Selection:** The UI offers supported completed events/sessions from 2023
   onward, resolves two drivers consistently by session-specific driver
   number, and maintains the current URL fields and latest-race action.
2. **Telemetry chart:** For two valid selected laps, the chart has aligned
   distance/time and speed traces and shows throttle, brake, gear, and RPM when
   those channels exist. Optional missing channels do not fail the whole chart.
   Brake is scaled correctly. DRS is retained if the current chart/UI exposes
   or later adds it; do not accidentally discard source data.
3. **Lap delta:** The delta chart and browser replay use the selected lap pair,
   preserve sign conventions, and never silently switch a numbered lap.
   Derived distance is identified in internal quality metadata.
4. **Replay/position:** When both laps have adequate X/Y data, the mini-map,
   follow-cars behavior, live values, play/pause, and Replay Focus work without
   Python requests on animation frames. When location is missing, speed
   telemetry remains usable and position-dependent views explain why they
   cannot render.
5. **Track map/DNA:** Dominance and speed/braking overlays render for adequate
   traces; DNA uses equivalent documented channel formulas and labels the
   comparison as relative. Use linked numbered corner definitions when their
   coordinates align; otherwise show explicitly heuristic markers.
6. **Pace:** Practice/qualifying pace distributions use valid lap times and
   appropriate ranking; race pace excludes invalid/in/out/pit laps according
   to an explicit normalized rule. Because OpenF1 does not document FastF1's
   `IsAccurate` or per-lap `TrackStatus`, the app must not claim identical
   exclusion of deleted or neutralized laps. Official result ordering is from
   OpenF1 `session_result` when present, otherwise use Jolpica as fallback or
   label the ranking as derived.
7. **Race gap:** Race/sprint selected-driver gap and position plots render with
   pit and grid context where present. Prefer OpenF1 session results and grid;
   use Jolpica only as fallback/cross-check. No false official grid/result
   claims appear when both sources are unavailable.
8. **Strategy/degradation:** Compound and stint overlays match normalized
   stint lap ranges; degradation uses the current formula and preserves its
   “fuel-corrected estimate” qualification. Temperature/rain overlay appears
   only with valid weather samples.
9. **Pit and race control:** Pit service changes are based on pit/stint evidence
   and duration types are not conflated. SC/VSC/red-flag shaded intervals are
   traceable to race-control events and tested on known sessions.
10. **AI:** Context includes the same categories as supported by available
    sources. Prompt explicitly distinguishes observed, derived, unavailable,
    and approximate data. With no usable trace, AI is instructed not to make
    telemetry-derived claims while non-telemetry context still works.
11. **Resilience/performance:** Reopening the same historical session is served
    from cache; selected-lap views do not repeatedly download entire-session
    telemetry. A 429 does not cause a retry storm, and one failed optional
    endpoint does not take out unrelated views.
12. **No hidden FastF1 dependency:** Automated tests exercise the full data
    facade with FastF1 unavailable/uninstalled, and normal app startup,
    schedule, selection, telemetry, strategy, race, and AI paths do not import
    or call FastF1.
13. **Unchanged UX:** Preserve all stable Dash component IDs and callback
    contracts unless every dependent callback/browser test is updated in the
    same change. Keep responsive layouts, chart download, feedback, and
    bookmarks working.

## 9. Explicit non-goals and decision points

- Live telemetry or immediate post-session data is out of scope.
- Seasons earlier than 2023 are out of scope for this migration.
- Do not add F1 TV login, credentials, session scraping, or an unofficial
  authentication workaround.
- Do not promise exact circuit-marker overlay alignment until the linked
  MultiViewer geometry has been validated against OpenF1 location traces; keep
  its provenance and any coordinate transform explicit.
- Do not introduce a durable database solely for this migration. Keep current
  bounded cache interfaces; a shared cache/rate limiter remains optional and
  must not be required to run locally.
- Do not change product features, visual design, AI provider, or feedback
  storage except where provider availability needs to be communicated.
- Before committing to full rewrite, complete Phase 1 and document any
  endpoint field that cannot support a REQ. Escalate a real parity gap instead
  of silently reducing the feature.

## 10. Requirement-to-plan traceability

| Requirement | Covered by | Completion evidence |
|---|---|---|
| REQ-001 | Phases 1, 2, 7 | Fixture-backed no-auth tests; FastF1 absent/unavailable in application data path; dependency removed only after proof. |
| REQ-002 | Phases 2, 3 | Normalized sessions/drivers and callback/URL/latest-race tests. |
| REQ-003 | Phase 4 | Canonical trace tests and telemetry figure regression tests. |
| REQ-004 | Phase 4 | Location-quality, replay payload, clientside behavior and browser tests. |
| REQ-005 | Phase 4 | Track-map/DNA graph tests; heuristic corner behavior and disclosure. |
| REQ-006 | Phase 5 | OpenF1 result/grid normalization plus optional Jolpica fallback and race/pace/grid/gap callback and graph tests. |
| REQ-007 | Phase 5 | Stint/pit/weather/degradation fixtures and graph tests. |
| REQ-008 | Phase 6 | AI prompt/context tests for all optional source failure modes. |
| REQ-009 | Phases 1, 2, 7 | HTTP-client tests, limiter/cache behavior, retry tests, and live smoke evidence. |
| REQ-010 | Phases 3–7 | Stable ID/URL regression tests, browser smoke, and final diff review. |
| REQ-011 | All phases, especially 7 | Fixture-backed integration suite and acceptance checklist results. |


## 11. Final verification record

- `python3 -m unittest discover -s tests -q`: 39 tests passed.
- Ruff 0.17.1 `ruff check .`: passed.
- `python3 -m compileall -q .` and `git diff --check`: passed.
- Live local Flask server: `/`, `/health`, and `/healthz` each returned HTTP
  200.
- `RUN_BROWSER_SMOKE=1 ... pytest -q tests/test_browser_smoke.py`: 2 passed
  (desktop 1440×1000, mobile 390×844) against 2023 Monaco Race. Verified URL
  restoration, live telemetry traces, replay controls, chart download, the
  feedback modal, Track Map and Race & Pace navigation. Desktop additionally
  selected numbered laps and changed Track Map overlays.
- Paced OpenF1 probe: 87 read-only requests across five completed sessions,
  within the probe's 25 requests/minute cap and 0.45 second minimum interval.
  The endpoint row/byte matrix, ten selected-lap synchronization checks, and
  optional endpoint gaps are recorded above. Spatial corner alignment remains
  unverified.
- Live callback harness built Monaco Race figures: 16 telemetry traces, 14
  strategy traces, and 3 race-gap traces. The browser test then verified chart
  rendering and interactions in the app itself.
- Chromium/Playwright and Ruff were installed only under `/private/tmp`; no
  runtime or development dependency was added to the project.
- URL restoration testing found and fixed a stale click/hydration race. Mobile
  browser testing found and fixed the zero-height telemetry loading wrapper.
- Final cleanup removed obsolete FastF1 fallback/warmup/schedule files and the
  local FastF1 cache. Runtime dependency/configuration searches found no
  FastF1 or SciPy code references; historical migration explanations are
  retained.
- Hosting recommendation: Render paid always-on single-worker service for
  regular use; Vercel remains a viable serverless-first deployment. Render
  Free is best treated as a demo because it sleeps and has ephemeral storage.
