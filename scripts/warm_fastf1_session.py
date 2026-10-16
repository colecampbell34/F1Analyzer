"""Seed the shared cache from a network where FastF1 can load a session.

Load a supported Upstash REST credential pair locally first. It stores bounded
derived lap/trace payloads, never FastF1's raw cache files or a serialized
Session object.
"""
from __future__ import annotations

import argparse
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('year', type=int)
    parser.add_argument('race')
    parser.add_argument('session')
    parser.add_argument('driver1', nargs='?', help='Optional three-letter driver abbreviation')
    parser.add_argument('driver2', nargs='?', help='Optional three-letter driver abbreviation')
    args = parser.parse_args()

    from shared_cache import is_configured
    if not is_configured():
        parser.error(
            'set UPSTASH_REDIS_REST_URL and UPSTASH_REDIS_REST_TOKEN '
            '(or the supported KV_REST_API_* aliases) first.'
        )
    if bool(args.driver1) != bool(args.driver2):
        parser.error('provide both drivers to warm a telemetry comparison, or neither to warm session laps only.')

    if not args.driver1:
        # This is enough for the leaderboard, pace, strategy and other
        # timing-based charts. It deliberately remains FastF1-only.
        from data import load_session_with_preload
        load_session_with_preload(
            args.year, args.race, args.session,
            laps=True, telemetry=False, weather=False, messages=False,
        )
        print(
            f"Seeded FastF1-derived laps for {args.year} {args.race} "
            f"{args.session}."
        )
        return

    from telemetry_prep import prepare_selected_lap_comparison

    payload = prepare_selected_lap_comparison({
        'year': args.year,
        'race': args.race,
        'session_type': args.session,
        'driver1': args.driver1.upper(),
        'driver2': args.driver2.upper(),
    })
    print(
        f"Seeded FastF1-derived laps and traces for {args.year} {args.race} "
        f"{args.session}: {payload['d1']} vs {payload['d2']}."
    )


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(f'Warm failed: {exc}', file=sys.stderr)
        raise SystemExit(1)
