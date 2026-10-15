"""Seed the Vercel shared cache from a network where FastF1 can load a session.

Use this only with the Vercel KV environment variables loaded locally. It
stores bounded derived lap/trace payloads, never FastF1's raw cache files or a
serialized Session object.
"""
from __future__ import annotations

import argparse
import os
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('year', type=int)
    parser.add_argument('race')
    parser.add_argument('session')
    parser.add_argument('driver1', help='Three-letter driver abbreviation')
    parser.add_argument('driver2', help='Three-letter driver abbreviation')
    args = parser.parse_args()

    if not (os.getenv('KV_REST_API_URL') and os.getenv('KV_REST_API_TOKEN')):
        parser.error('load the Vercel KV variables first, e.g. `vercel env pull .env.local`.')

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
