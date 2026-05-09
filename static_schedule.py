# Generated from FastF1 event schedules. Keep this file static at runtime.
from datetime import datetime, timezone


def _parse_static_timestamp(value):
    if not value:
        return None
    try:
        text = str(value)
        if text.endswith('Z'):
            text = text[:-1] + '+00:00'
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        return None


def get_static_years():
    return tuple(sorted(int(year) for year in STATIC_SCHEDULE))


def get_static_races(year):
    return tuple(event['race'] for event in STATIC_SCHEDULE.get(str(int(year)), ()))


def get_static_sessions(year, race):
    for event in STATIC_SCHEDULE.get(str(int(year)), ()):
        if event.get('race') == str(race):
            return tuple(session['name'] for session in event.get('sessions', ()))
    return tuple()


def get_latest_static_race_session(now=None, first_year=2018):
    if now is None:
        now_dt = datetime.now(timezone.utc)
    elif isinstance(now, datetime):
        now_dt = now.astimezone(timezone.utc) if now.tzinfo else now.replace(tzinfo=timezone.utc)
    else:
        now_dt = _parse_static_timestamp(now)
    if now_dt is None:
        now_dt = datetime.now(timezone.utc)

    candidates = []
    for year in get_static_years():
        if year < int(first_year):
            continue
        for event in STATIC_SCHEDULE.get(str(year), ()):
            race_date = None
            for session in event.get('sessions', ()):
                if session.get('name') == 'Race':
                    race_date = (
                        _parse_static_timestamp(session.get('date_utc'))
                        or _parse_static_timestamp(session.get('date'))
                    )
                    break
            if race_date is None:
                race_date = _parse_static_timestamp(event.get('event_date'))
            if race_date is not None and race_date <= now_dt:
                candidates.append((race_date, year, event.get('race'), 'Race'))

    if not candidates:
        return None
    _, year, race, session_type = max(candidates, key=lambda item: item[0])
    return {'year': year, 'race': race, 'session_type': session_type}


STATIC_SCHEDULE = {
    "2018": [
        {
            "event_date": "2018-03-25",
            "race": "Australian Grand Prix",
            "sessions": [
                {
                    "date": "2018-03-23T12:00:00+11:00",
                    "date_utc": "2018-03-23T01:00:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2018-03-23T16:00:00+11:00",
                    "date_utc": "2018-03-23T05:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2018-03-24T14:00:00+11:00",
                    "date_utc": "2018-03-24T03:00:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2018-03-24T17:00:00+11:00",
                    "date_utc": "2018-03-24T06:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2018-03-25T16:10:00+11:00",
                    "date_utc": "2018-03-25T05:10:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2018-04-08",
            "race": "Bahrain Grand Prix",
            "sessions": [
                {
                    "date": "2018-04-06T14:00:00+03:00",
                    "date_utc": "2018-04-06T11:00:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2018-04-06T18:00:00+03:00",
                    "date_utc": "2018-04-06T15:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2018-04-07T15:00:00+03:00",
                    "date_utc": "2018-04-07T12:00:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2018-04-07T18:00:00+03:00",
                    "date_utc": "2018-04-07T15:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2018-04-08T18:10:00+03:00",
                    "date_utc": "2018-04-08T15:10:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2018-04-15",
            "race": "Chinese Grand Prix",
            "sessions": [
                {
                    "date": "2018-04-13T10:00:00+08:00",
                    "date_utc": "2018-04-13T02:00:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2018-04-13T14:00:00+08:00",
                    "date_utc": "2018-04-13T06:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2018-04-14T11:00:00+08:00",
                    "date_utc": "2018-04-14T03:00:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2018-04-14T14:00:00+08:00",
                    "date_utc": "2018-04-14T06:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2018-04-15T14:10:00+08:00",
                    "date_utc": "2018-04-15T06:10:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2018-04-29",
            "race": "Azerbaijan Grand Prix",
            "sessions": [
                {
                    "date": "2018-04-27T13:00:00+04:00",
                    "date_utc": "2018-04-27T09:00:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2018-04-27T17:00:00+04:00",
                    "date_utc": "2018-04-27T13:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2018-04-28T14:00:00+04:00",
                    "date_utc": "2018-04-28T10:00:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2018-04-28T17:00:00+04:00",
                    "date_utc": "2018-04-28T13:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2018-04-29T16:10:00+04:00",
                    "date_utc": "2018-04-29T12:10:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2018-05-13",
            "race": "Spanish Grand Prix",
            "sessions": [
                {
                    "date": "2018-05-11T11:00:00+02:00",
                    "date_utc": "2018-05-11T09:00:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2018-05-11T15:00:00+02:00",
                    "date_utc": "2018-05-11T13:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2018-05-12T12:00:00+02:00",
                    "date_utc": "2018-05-12T10:00:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2018-05-12T15:00:00+02:00",
                    "date_utc": "2018-05-12T13:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2018-05-13T15:10:00+02:00",
                    "date_utc": "2018-05-13T13:10:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2018-05-27",
            "race": "Monaco Grand Prix",
            "sessions": [
                {
                    "date": "2018-05-24T11:00:00+02:00",
                    "date_utc": "2018-05-24T09:00:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2018-05-24T15:00:00+02:00",
                    "date_utc": "2018-05-24T13:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2018-05-26T12:00:00+02:00",
                    "date_utc": "2018-05-26T10:00:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2018-05-26T15:00:00+02:00",
                    "date_utc": "2018-05-26T13:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2018-05-27T15:10:00+02:00",
                    "date_utc": "2018-05-27T13:10:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2018-06-10",
            "race": "Canadian Grand Prix",
            "sessions": [
                {
                    "date": "2018-06-08T10:00:00-04:00",
                    "date_utc": "2018-06-08T14:00:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2018-06-08T14:00:00-04:00",
                    "date_utc": "2018-06-08T18:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2018-06-09T11:00:00-04:00",
                    "date_utc": "2018-06-09T15:00:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2018-06-09T14:00:00-04:00",
                    "date_utc": "2018-06-09T18:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2018-06-10T14:10:00-04:00",
                    "date_utc": "2018-06-10T18:10:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2018-06-24",
            "race": "French Grand Prix",
            "sessions": [
                {
                    "date": "2018-06-22T12:00:00+02:00",
                    "date_utc": "2018-06-22T10:00:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2018-06-22T16:00:00+02:00",
                    "date_utc": "2018-06-22T14:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2018-06-23T13:00:00+02:00",
                    "date_utc": "2018-06-23T11:00:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2018-06-23T16:00:00+02:00",
                    "date_utc": "2018-06-23T14:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2018-06-24T16:10:00+02:00",
                    "date_utc": "2018-06-24T14:10:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2018-07-01",
            "race": "Austrian Grand Prix",
            "sessions": [
                {
                    "date": "2018-06-29T11:00:00+02:00",
                    "date_utc": "2018-06-29T09:00:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2018-06-29T15:00:00+02:00",
                    "date_utc": "2018-06-29T13:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2018-06-30T12:00:00+02:00",
                    "date_utc": "2018-06-30T10:00:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2018-06-30T15:00:00+02:00",
                    "date_utc": "2018-06-30T13:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2018-07-01T15:10:00+02:00",
                    "date_utc": "2018-07-01T13:10:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2018-07-08",
            "race": "British Grand Prix",
            "sessions": [
                {
                    "date": "2018-07-06T10:00:00+01:00",
                    "date_utc": "2018-07-06T09:00:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2018-07-06T14:00:00+01:00",
                    "date_utc": "2018-07-06T13:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2018-07-07T11:00:00+01:00",
                    "date_utc": "2018-07-07T10:00:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2018-07-07T14:00:00+01:00",
                    "date_utc": "2018-07-07T13:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2018-07-08T14:10:00+01:00",
                    "date_utc": "2018-07-08T13:10:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2018-07-22",
            "race": "German Grand Prix",
            "sessions": [
                {
                    "date": "2018-07-20T11:00:00+02:00",
                    "date_utc": "2018-07-20T09:00:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2018-07-20T15:00:00+02:00",
                    "date_utc": "2018-07-20T13:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2018-07-21T12:00:00+02:00",
                    "date_utc": "2018-07-21T10:00:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2018-07-21T15:00:00+02:00",
                    "date_utc": "2018-07-21T13:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2018-07-22T15:10:00+02:00",
                    "date_utc": "2018-07-22T13:10:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2018-07-29",
            "race": "Hungarian Grand Prix",
            "sessions": [
                {
                    "date": "2018-07-27T11:00:00+02:00",
                    "date_utc": "2018-07-27T09:00:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2018-07-27T15:00:00+02:00",
                    "date_utc": "2018-07-27T13:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2018-07-28T12:00:00+02:00",
                    "date_utc": "2018-07-28T10:00:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2018-07-28T15:00:00+02:00",
                    "date_utc": "2018-07-28T13:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2018-07-29T15:10:00+02:00",
                    "date_utc": "2018-07-29T13:10:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2018-08-26",
            "race": "Belgian Grand Prix",
            "sessions": [
                {
                    "date": "2018-08-24T11:00:00+02:00",
                    "date_utc": "2018-08-24T09:00:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2018-08-24T15:00:00+02:00",
                    "date_utc": "2018-08-24T13:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2018-08-25T12:00:00+02:00",
                    "date_utc": "2018-08-25T10:00:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2018-08-25T15:00:00+02:00",
                    "date_utc": "2018-08-25T13:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2018-08-26T15:10:00+02:00",
                    "date_utc": "2018-08-26T13:10:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2018-09-02",
            "race": "Italian Grand Prix",
            "sessions": [
                {
                    "date": "2018-08-31T11:00:00+02:00",
                    "date_utc": "2018-08-31T09:00:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2018-08-31T15:00:00+02:00",
                    "date_utc": "2018-08-31T13:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2018-09-01T12:00:00+02:00",
                    "date_utc": "2018-09-01T10:00:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2018-09-01T15:00:00+02:00",
                    "date_utc": "2018-09-01T13:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2018-09-02T15:10:00+02:00",
                    "date_utc": "2018-09-02T13:10:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2018-09-16",
            "race": "Singapore Grand Prix",
            "sessions": [
                {
                    "date": "2018-09-14T16:30:00+08:00",
                    "date_utc": "2018-09-14T08:30:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2018-09-14T20:30:00+08:00",
                    "date_utc": "2018-09-14T12:30:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2018-09-15T18:00:00+08:00",
                    "date_utc": "2018-09-15T10:00:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2018-09-15T21:00:00+08:00",
                    "date_utc": "2018-09-15T13:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2018-09-16T20:10:00+08:00",
                    "date_utc": "2018-09-16T12:10:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2018-09-30",
            "race": "Russian Grand Prix",
            "sessions": [
                {
                    "date": "2018-09-28T11:00:00+03:00",
                    "date_utc": "2018-09-28T08:00:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2018-09-28T15:00:00+03:00",
                    "date_utc": "2018-09-28T12:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2018-09-29T12:00:00+03:00",
                    "date_utc": "2018-09-29T09:00:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2018-09-29T15:00:00+03:00",
                    "date_utc": "2018-09-29T12:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2018-09-30T14:10:00+03:00",
                    "date_utc": "2018-09-30T11:10:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2018-10-07",
            "race": "Japanese Grand Prix",
            "sessions": [
                {
                    "date": "2018-10-05T10:00:00+09:00",
                    "date_utc": "2018-10-05T01:00:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2018-10-05T14:00:00+09:00",
                    "date_utc": "2018-10-05T05:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2018-10-06T12:00:00+09:00",
                    "date_utc": "2018-10-06T03:00:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2018-10-06T15:00:00+09:00",
                    "date_utc": "2018-10-06T06:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2018-10-07T14:10:00+09:00",
                    "date_utc": "2018-10-07T05:10:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2018-10-21",
            "race": "United States Grand Prix",
            "sessions": [
                {
                    "date": "2018-10-19T10:00:00-05:00",
                    "date_utc": "2018-10-19T15:00:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2018-10-19T14:00:00-05:00",
                    "date_utc": "2018-10-19T19:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2018-10-20T13:00:00-05:00",
                    "date_utc": "2018-10-20T18:00:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2018-10-20T16:00:00-05:00",
                    "date_utc": "2018-10-20T21:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2018-10-21T13:10:00-05:00",
                    "date_utc": "2018-10-21T18:10:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2018-10-28",
            "race": "Mexican Grand Prix",
            "sessions": [
                {
                    "date": "2018-10-26T10:00:00-06:00",
                    "date_utc": "2018-10-26T16:00:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2018-10-26T14:00:00-06:00",
                    "date_utc": "2018-10-26T20:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2018-10-27T10:00:00-06:00",
                    "date_utc": "2018-10-27T16:00:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2018-10-27T13:00:00-06:00",
                    "date_utc": "2018-10-27T19:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2018-10-28T13:10:00-06:00",
                    "date_utc": "2018-10-28T19:10:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2018-11-11",
            "race": "Brazilian Grand Prix",
            "sessions": [
                {
                    "date": "2018-11-09T11:00:00-02:00",
                    "date_utc": "2018-11-09T13:00:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2018-11-09T15:00:00-02:00",
                    "date_utc": "2018-11-09T17:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2018-11-10T12:00:00-02:00",
                    "date_utc": "2018-11-10T14:00:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2018-11-10T15:00:00-02:00",
                    "date_utc": "2018-11-10T17:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2018-11-11T15:10:00-02:00",
                    "date_utc": "2018-11-11T17:10:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2018-11-25",
            "race": "Abu Dhabi Grand Prix",
            "sessions": [
                {
                    "date": "2018-11-23T13:00:00+04:00",
                    "date_utc": "2018-11-23T09:00:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2018-11-23T17:00:00+04:00",
                    "date_utc": "2018-11-23T13:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2018-11-24T14:00:00+04:00",
                    "date_utc": "2018-11-24T10:00:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2018-11-24T17:00:00+04:00",
                    "date_utc": "2018-11-24T13:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2018-11-25T17:10:00+04:00",
                    "date_utc": "2018-11-25T13:10:00",
                    "name": "Race"
                }
            ]
        }
    ],
    "2019": [
        {
            "event_date": "2019-03-17",
            "race": "Australian Grand Prix",
            "sessions": [
                {
                    "date": "2019-03-15T12:00:00+11:00",
                    "date_utc": "2019-03-15T01:00:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2019-03-15T16:00:00+11:00",
                    "date_utc": "2019-03-15T05:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2019-03-16T14:00:00+11:00",
                    "date_utc": "2019-03-16T03:00:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2019-03-16T17:00:00+11:00",
                    "date_utc": "2019-03-16T06:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2019-03-17T16:10:00+11:00",
                    "date_utc": "2019-03-17T05:10:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2019-03-31",
            "race": "Bahrain Grand Prix",
            "sessions": [
                {
                    "date": "2019-03-29T14:00:00+03:00",
                    "date_utc": "2019-03-29T11:00:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2019-03-29T18:00:00+03:00",
                    "date_utc": "2019-03-29T15:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2019-03-30T15:00:00+03:00",
                    "date_utc": "2019-03-30T12:00:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2019-03-30T18:00:00+03:00",
                    "date_utc": "2019-03-30T15:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2019-03-31T18:10:00+03:00",
                    "date_utc": "2019-03-31T15:10:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2019-04-14",
            "race": "Chinese Grand Prix",
            "sessions": [
                {
                    "date": "2019-04-12T10:00:00+08:00",
                    "date_utc": "2019-04-12T02:00:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2019-04-12T14:00:00+08:00",
                    "date_utc": "2019-04-12T06:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2019-04-13T11:00:00+08:00",
                    "date_utc": "2019-04-13T03:00:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2019-04-13T14:00:00+08:00",
                    "date_utc": "2019-04-13T06:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2019-04-14T14:10:00+08:00",
                    "date_utc": "2019-04-14T06:10:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2019-04-28",
            "race": "Azerbaijan Grand Prix",
            "sessions": [
                {
                    "date": "2019-04-26T13:00:00+04:00",
                    "date_utc": "2019-04-26T09:00:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2019-04-26T17:00:00+04:00",
                    "date_utc": "2019-04-26T13:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2019-04-27T14:00:00+04:00",
                    "date_utc": "2019-04-27T10:00:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2019-04-27T17:00:00+04:00",
                    "date_utc": "2019-04-27T13:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2019-04-28T16:10:00+04:00",
                    "date_utc": "2019-04-28T12:10:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2019-05-12",
            "race": "Spanish Grand Prix",
            "sessions": [
                {
                    "date": "2019-05-10T11:00:00+02:00",
                    "date_utc": "2019-05-10T09:00:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2019-05-10T15:00:00+02:00",
                    "date_utc": "2019-05-10T13:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2019-05-11T12:00:00+02:00",
                    "date_utc": "2019-05-11T10:00:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2019-05-11T15:00:00+02:00",
                    "date_utc": "2019-05-11T13:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2019-05-12T15:10:00+02:00",
                    "date_utc": "2019-05-12T13:10:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2019-05-26",
            "race": "Monaco Grand Prix",
            "sessions": [
                {
                    "date": "2019-05-23T11:00:00+02:00",
                    "date_utc": "2019-05-23T09:00:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2019-05-23T15:00:00+02:00",
                    "date_utc": "2019-05-23T13:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2019-05-25T12:00:00+02:00",
                    "date_utc": "2019-05-25T10:00:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2019-05-25T15:00:00+02:00",
                    "date_utc": "2019-05-25T13:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2019-05-26T15:10:00+02:00",
                    "date_utc": "2019-05-26T13:10:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2019-06-09",
            "race": "Canadian Grand Prix",
            "sessions": [
                {
                    "date": "2019-06-07T10:00:00-04:00",
                    "date_utc": "2019-06-07T14:00:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2019-06-07T14:00:00-04:00",
                    "date_utc": "2019-06-07T18:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2019-06-08T11:00:00-04:00",
                    "date_utc": "2019-06-08T15:00:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2019-06-08T14:00:00-04:00",
                    "date_utc": "2019-06-08T18:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2019-06-09T14:10:00-04:00",
                    "date_utc": "2019-06-09T18:10:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2019-06-23",
            "race": "French Grand Prix",
            "sessions": [
                {
                    "date": "2019-06-21T11:00:00+02:00",
                    "date_utc": "2019-06-21T09:00:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2019-06-21T15:00:00+02:00",
                    "date_utc": "2019-06-21T13:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2019-06-22T12:00:00+02:00",
                    "date_utc": "2019-06-22T10:00:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2019-06-22T15:00:00+02:00",
                    "date_utc": "2019-06-22T13:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2019-06-23T15:10:00+02:00",
                    "date_utc": "2019-06-23T13:10:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2019-06-30",
            "race": "Austrian Grand Prix",
            "sessions": [
                {
                    "date": "2019-06-28T11:00:00+02:00",
                    "date_utc": "2019-06-28T09:00:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2019-06-28T15:00:00+02:00",
                    "date_utc": "2019-06-28T13:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2019-06-29T12:00:00+02:00",
                    "date_utc": "2019-06-29T10:00:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2019-06-29T15:00:00+02:00",
                    "date_utc": "2019-06-29T13:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2019-06-30T15:10:00+02:00",
                    "date_utc": "2019-06-30T13:10:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2019-07-14",
            "race": "British Grand Prix",
            "sessions": [
                {
                    "date": "2019-07-12T10:00:00+01:00",
                    "date_utc": "2019-07-12T09:00:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2019-07-12T14:00:00+01:00",
                    "date_utc": "2019-07-12T13:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2019-07-13T11:00:00+01:00",
                    "date_utc": "2019-07-13T10:00:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2019-07-13T14:00:00+01:00",
                    "date_utc": "2019-07-13T13:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2019-07-14T14:10:00+01:00",
                    "date_utc": "2019-07-14T13:10:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2019-07-28",
            "race": "German Grand Prix",
            "sessions": [
                {
                    "date": "2019-07-26T11:00:00+02:00",
                    "date_utc": "2019-07-26T09:00:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2019-07-26T15:00:00+02:00",
                    "date_utc": "2019-07-26T13:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2019-07-27T12:00:00+02:00",
                    "date_utc": "2019-07-27T10:00:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2019-07-27T15:00:00+02:00",
                    "date_utc": "2019-07-27T13:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2019-07-28T15:10:00+02:00",
                    "date_utc": "2019-07-28T13:10:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2019-08-04",
            "race": "Hungarian Grand Prix",
            "sessions": [
                {
                    "date": "2019-08-02T11:00:00+02:00",
                    "date_utc": "2019-08-02T09:00:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2019-08-02T15:00:00+02:00",
                    "date_utc": "2019-08-02T13:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2019-08-03T12:00:00+02:00",
                    "date_utc": "2019-08-03T10:00:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2019-08-03T15:00:00+02:00",
                    "date_utc": "2019-08-03T13:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2019-08-04T15:10:00+02:00",
                    "date_utc": "2019-08-04T13:10:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2019-09-01",
            "race": "Belgian Grand Prix",
            "sessions": [
                {
                    "date": "2019-08-30T11:00:00+02:00",
                    "date_utc": "2019-08-30T09:00:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2019-08-30T15:00:00+02:00",
                    "date_utc": "2019-08-30T13:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2019-08-31T12:00:00+02:00",
                    "date_utc": "2019-08-31T10:00:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2019-08-31T15:00:00+02:00",
                    "date_utc": "2019-08-31T13:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2019-09-01T15:10:00+02:00",
                    "date_utc": "2019-09-01T13:10:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2019-09-08",
            "race": "Italian Grand Prix",
            "sessions": [
                {
                    "date": "2019-09-06T11:00:00+02:00",
                    "date_utc": "2019-09-06T09:00:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2019-09-06T15:00:00+02:00",
                    "date_utc": "2019-09-06T13:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2019-09-07T12:00:00+02:00",
                    "date_utc": "2019-09-07T10:00:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2019-09-07T15:00:00+02:00",
                    "date_utc": "2019-09-07T13:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2019-09-08T15:10:00+02:00",
                    "date_utc": "2019-09-08T13:10:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2019-09-22",
            "race": "Singapore Grand Prix",
            "sessions": [
                {
                    "date": "2019-09-20T16:30:00+08:00",
                    "date_utc": "2019-09-20T08:30:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2019-09-20T20:30:00+08:00",
                    "date_utc": "2019-09-20T12:30:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2019-09-21T18:00:00+08:00",
                    "date_utc": "2019-09-21T10:00:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2019-09-21T21:00:00+08:00",
                    "date_utc": "2019-09-21T13:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2019-09-22T20:10:00+08:00",
                    "date_utc": "2019-09-22T12:10:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2019-09-29",
            "race": "Russian Grand Prix",
            "sessions": [
                {
                    "date": "2019-09-27T11:00:00+03:00",
                    "date_utc": "2019-09-27T08:00:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2019-09-27T15:00:00+03:00",
                    "date_utc": "2019-09-27T12:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2019-09-28T12:00:00+03:00",
                    "date_utc": "2019-09-28T09:00:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2019-09-28T15:00:00+03:00",
                    "date_utc": "2019-09-28T12:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2019-09-29T14:10:00+03:00",
                    "date_utc": "2019-09-29T11:10:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2019-10-13",
            "race": "Japanese Grand Prix",
            "sessions": [
                {
                    "date": "2019-10-11T10:00:00+09:00",
                    "date_utc": "2019-10-11T01:00:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2019-10-11T14:00:00+09:00",
                    "date_utc": "2019-10-11T05:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2019-10-12T12:00:00+09:00",
                    "date_utc": "2019-10-12T03:00:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2019-10-13T10:00:00+09:00",
                    "date_utc": "2019-10-13T01:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2019-10-13T14:10:00+09:00",
                    "date_utc": "2019-10-13T05:10:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2019-10-27",
            "race": "Mexican Grand Prix",
            "sessions": [
                {
                    "date": "2019-10-25T10:00:00-06:00",
                    "date_utc": "2019-10-25T16:00:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2019-10-25T14:00:00-06:00",
                    "date_utc": "2019-10-25T20:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2019-10-26T10:00:00-06:00",
                    "date_utc": "2019-10-26T16:00:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2019-10-26T13:00:00-06:00",
                    "date_utc": "2019-10-26T19:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2019-10-27T13:10:00-06:00",
                    "date_utc": "2019-10-27T19:10:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2019-11-03",
            "race": "United States Grand Prix",
            "sessions": [
                {
                    "date": "2019-11-01T11:00:00-06:00",
                    "date_utc": "2019-11-01T17:00:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2019-11-01T15:00:00-06:00",
                    "date_utc": "2019-11-01T21:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2019-11-02T13:00:00-06:00",
                    "date_utc": "2019-11-02T19:00:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2019-11-02T16:00:00-06:00",
                    "date_utc": "2019-11-02T22:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2019-11-03T13:10:00-06:00",
                    "date_utc": "2019-11-03T19:10:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2019-11-17",
            "race": "Brazilian Grand Prix",
            "sessions": [
                {
                    "date": "2019-11-15T11:00:00-03:00",
                    "date_utc": "2019-11-15T14:00:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2019-11-15T15:00:00-03:00",
                    "date_utc": "2019-11-15T18:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2019-11-16T12:00:00-03:00",
                    "date_utc": "2019-11-16T15:00:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2019-11-16T15:00:00-03:00",
                    "date_utc": "2019-11-16T18:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2019-11-17T14:10:00-03:00",
                    "date_utc": "2019-11-17T17:10:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2019-12-01",
            "race": "Abu Dhabi Grand Prix",
            "sessions": [
                {
                    "date": "2019-11-29T13:00:00+04:00",
                    "date_utc": "2019-11-29T09:00:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2019-11-29T17:00:00+04:00",
                    "date_utc": "2019-11-29T13:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2019-11-30T14:00:00+04:00",
                    "date_utc": "2019-11-30T10:00:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2019-11-30T17:00:00+04:00",
                    "date_utc": "2019-11-30T13:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2019-12-01T17:10:00+04:00",
                    "date_utc": "2019-12-01T13:10:00",
                    "name": "Race"
                }
            ]
        }
    ],
    "2020": [
        {
            "event_date": "2020-07-05",
            "race": "Austrian Grand Prix",
            "sessions": [
                {
                    "date": "2020-07-03T11:00:00+02:00",
                    "date_utc": "2020-07-03T09:00:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2020-07-03T15:00:00+02:00",
                    "date_utc": "2020-07-03T13:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2020-07-04T12:00:00+02:00",
                    "date_utc": "2020-07-04T10:00:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2020-07-04T15:00:00+02:00",
                    "date_utc": "2020-07-04T13:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2020-07-05T15:10:00+02:00",
                    "date_utc": "2020-07-05T13:10:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2020-07-12",
            "race": "Styrian Grand Prix",
            "sessions": [
                {
                    "date": "2020-07-10T11:00:00+02:00",
                    "date_utc": "2020-07-10T09:00:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2020-07-10T15:00:00+02:00",
                    "date_utc": "2020-07-10T13:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2020-07-11T12:00:00+02:00",
                    "date_utc": "2020-07-11T10:00:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2020-07-11T15:00:00+02:00",
                    "date_utc": "2020-07-11T13:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2020-07-12T15:10:00+02:00",
                    "date_utc": "2020-07-12T13:10:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2020-07-19",
            "race": "Hungarian Grand Prix",
            "sessions": [
                {
                    "date": "2020-07-17T11:00:00+02:00",
                    "date_utc": "2020-07-17T09:00:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2020-07-17T15:00:00+02:00",
                    "date_utc": "2020-07-17T13:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2020-07-18T12:00:00+02:00",
                    "date_utc": "2020-07-18T10:00:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2020-07-18T15:00:00+02:00",
                    "date_utc": "2020-07-18T13:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2020-07-19T15:10:00+02:00",
                    "date_utc": "2020-07-19T13:10:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2020-08-02",
            "race": "British Grand Prix",
            "sessions": [
                {
                    "date": "2020-07-31T11:00:00+01:00",
                    "date_utc": "2020-07-31T10:00:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2020-07-31T15:00:00+01:00",
                    "date_utc": "2020-07-31T14:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2020-08-01T11:00:00+01:00",
                    "date_utc": "2020-08-01T10:00:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2020-08-01T14:00:00+01:00",
                    "date_utc": "2020-08-01T13:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2020-08-02T14:10:00+01:00",
                    "date_utc": "2020-08-02T13:10:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2020-08-09",
            "race": "70th Anniversary Grand Prix",
            "sessions": [
                {
                    "date": "2020-08-07T11:00:00+01:00",
                    "date_utc": "2020-08-07T10:00:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2020-08-07T15:00:00+01:00",
                    "date_utc": "2020-08-07T14:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2020-08-08T11:00:00+01:00",
                    "date_utc": "2020-08-08T10:00:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2020-08-08T14:00:00+01:00",
                    "date_utc": "2020-08-08T13:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2020-08-09T14:10:00+01:00",
                    "date_utc": "2020-08-09T13:10:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2020-08-16",
            "race": "Spanish Grand Prix",
            "sessions": [
                {
                    "date": "2020-08-14T11:00:00+02:00",
                    "date_utc": "2020-08-14T09:00:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2020-08-14T15:00:00+02:00",
                    "date_utc": "2020-08-14T13:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2020-08-15T12:00:00+02:00",
                    "date_utc": "2020-08-15T10:00:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2020-08-15T15:00:00+02:00",
                    "date_utc": "2020-08-15T13:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2020-08-16T15:10:00+02:00",
                    "date_utc": "2020-08-16T13:10:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2020-08-30",
            "race": "Belgian Grand Prix",
            "sessions": [
                {
                    "date": "2020-08-28T11:00:00+02:00",
                    "date_utc": "2020-08-28T09:00:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2020-08-28T15:00:00+02:00",
                    "date_utc": "2020-08-28T13:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2020-08-29T12:00:00+02:00",
                    "date_utc": "2020-08-29T10:00:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2020-08-29T15:00:00+02:00",
                    "date_utc": "2020-08-29T13:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2020-08-30T15:10:00+02:00",
                    "date_utc": "2020-08-30T13:10:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2020-09-06",
            "race": "Italian Grand Prix",
            "sessions": [
                {
                    "date": "2020-09-04T11:00:00+02:00",
                    "date_utc": "2020-09-04T09:00:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2020-09-04T15:00:00+02:00",
                    "date_utc": "2020-09-04T13:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2020-09-05T12:00:00+02:00",
                    "date_utc": "2020-09-05T10:00:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2020-09-05T15:00:00+02:00",
                    "date_utc": "2020-09-05T13:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2020-09-06T15:10:00+02:00",
                    "date_utc": "2020-09-06T13:10:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2020-09-13",
            "race": "Tuscan Grand Prix",
            "sessions": [
                {
                    "date": "2020-09-11T11:00:00+02:00",
                    "date_utc": "2020-09-11T09:00:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2020-09-11T15:00:00+02:00",
                    "date_utc": "2020-09-11T13:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2020-09-12T12:00:00+02:00",
                    "date_utc": "2020-09-12T10:00:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2020-09-12T15:00:00+02:00",
                    "date_utc": "2020-09-12T13:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2020-09-13T15:10:00+02:00",
                    "date_utc": "2020-09-13T13:10:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2020-09-27",
            "race": "Russian Grand Prix",
            "sessions": [
                {
                    "date": "2020-09-25T11:00:00+03:00",
                    "date_utc": "2020-09-25T08:00:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2020-09-25T15:00:00+03:00",
                    "date_utc": "2020-09-25T12:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2020-09-26T12:00:00+03:00",
                    "date_utc": "2020-09-26T09:00:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2020-09-26T15:00:00+03:00",
                    "date_utc": "2020-09-26T12:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2020-09-27T14:10:00+03:00",
                    "date_utc": "2020-09-27T11:10:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2020-10-11",
            "race": "Eifel Grand Prix",
            "sessions": [
                {
                    "date": "2020-10-09T11:00:00+02:00",
                    "date_utc": "2020-10-09T09:00:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2020-10-09T15:00:00+02:00",
                    "date_utc": "2020-10-09T13:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2020-10-10T12:00:00+02:00",
                    "date_utc": "2020-10-10T10:00:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2020-10-10T15:00:00+02:00",
                    "date_utc": "2020-10-10T13:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2020-10-11T14:10:00+02:00",
                    "date_utc": "2020-10-11T12:10:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2020-10-25",
            "race": "Portuguese Grand Prix",
            "sessions": [
                {
                    "date": "2020-10-23T11:00:00+00:00",
                    "date_utc": "2020-10-23T11:00:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2020-10-23T15:00:00+00:00",
                    "date_utc": "2020-10-23T15:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2020-10-24T11:00:00+00:00",
                    "date_utc": "2020-10-24T11:00:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2020-10-24T14:00:00+00:00",
                    "date_utc": "2020-10-24T14:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2020-10-25T13:10:00+00:00",
                    "date_utc": "2020-10-25T13:10:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2020-11-01",
            "race": "Emilia Romagna Grand Prix",
            "sessions": [
                {
                    "date": "2020-10-31T10:00:00+01:00",
                    "date_utc": "2020-10-31T09:00:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2020-10-31T14:00:00+01:00",
                    "date_utc": "2020-10-31T13:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2020-11-01T13:10:00+01:00",
                    "date_utc": "2020-11-01T12:10:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2020-11-15",
            "race": "Turkish Grand Prix",
            "sessions": [
                {
                    "date": "2020-11-13T11:00:00+03:00",
                    "date_utc": "2020-11-13T08:00:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2020-11-13T15:00:00+03:00",
                    "date_utc": "2020-11-13T12:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2020-11-14T12:00:00+03:00",
                    "date_utc": "2020-11-14T09:00:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2020-11-14T15:00:00+03:00",
                    "date_utc": "2020-11-14T12:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2020-11-15T13:10:00+03:00",
                    "date_utc": "2020-11-15T10:10:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2020-11-29",
            "race": "Bahrain Grand Prix",
            "sessions": [
                {
                    "date": "2020-11-27T14:00:00+03:00",
                    "date_utc": "2020-11-27T11:00:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2020-11-27T18:00:00+03:00",
                    "date_utc": "2020-11-27T15:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2020-11-28T14:00:00+03:00",
                    "date_utc": "2020-11-28T11:00:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2020-11-28T17:00:00+03:00",
                    "date_utc": "2020-11-28T14:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2020-11-29T17:10:00+03:00",
                    "date_utc": "2020-11-29T14:10:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2020-12-06",
            "race": "Sakhir Grand Prix",
            "sessions": [
                {
                    "date": "2020-12-04T16:30:00+03:00",
                    "date_utc": "2020-12-04T13:30:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2020-12-04T20:30:00+03:00",
                    "date_utc": "2020-12-04T17:30:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2020-12-05T17:00:00+03:00",
                    "date_utc": "2020-12-05T14:00:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2020-12-05T20:00:00+03:00",
                    "date_utc": "2020-12-05T17:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2020-12-06T20:10:00+03:00",
                    "date_utc": "2020-12-06T17:10:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2020-12-13",
            "race": "Abu Dhabi Grand Prix",
            "sessions": [
                {
                    "date": "2020-12-11T13:00:00+04:00",
                    "date_utc": "2020-12-11T09:00:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2020-12-11T17:00:00+04:00",
                    "date_utc": "2020-12-11T13:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2020-12-12T14:00:00+04:00",
                    "date_utc": "2020-12-12T10:00:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2020-12-12T17:00:00+04:00",
                    "date_utc": "2020-12-12T13:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2020-12-13T17:10:00+04:00",
                    "date_utc": "2020-12-13T13:10:00",
                    "name": "Race"
                }
            ]
        }
    ],
    "2021": [
        {
            "event_date": "2021-03-28",
            "race": "Bahrain Grand Prix",
            "sessions": [
                {
                    "date": "2021-03-26T14:30:00+03:00",
                    "date_utc": "2021-03-26T11:30:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2021-03-26T18:00:00+03:00",
                    "date_utc": "2021-03-26T15:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2021-03-27T15:00:00+03:00",
                    "date_utc": "2021-03-27T12:00:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2021-03-27T18:00:00+03:00",
                    "date_utc": "2021-03-27T15:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2021-03-28T18:00:00+03:00",
                    "date_utc": "2021-03-28T15:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2021-04-18",
            "race": "Emilia Romagna Grand Prix",
            "sessions": [
                {
                    "date": "2021-04-16T11:00:00+02:00",
                    "date_utc": "2021-04-16T09:00:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2021-04-16T14:30:00+02:00",
                    "date_utc": "2021-04-16T12:30:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2021-04-17T11:00:00+02:00",
                    "date_utc": "2021-04-17T09:00:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2021-04-17T14:00:00+02:00",
                    "date_utc": "2021-04-17T12:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2021-04-18T15:00:00+02:00",
                    "date_utc": "2021-04-18T13:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2021-05-02",
            "race": "Portuguese Grand Prix",
            "sessions": [
                {
                    "date": "2021-04-30T11:30:00+01:00",
                    "date_utc": "2021-04-30T10:30:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2021-04-30T15:00:00+01:00",
                    "date_utc": "2021-04-30T14:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2021-05-01T12:00:00+01:00",
                    "date_utc": "2021-05-01T11:00:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2021-05-01T15:00:00+01:00",
                    "date_utc": "2021-05-01T14:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2021-05-02T15:00:00+01:00",
                    "date_utc": "2021-05-02T14:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2021-05-09",
            "race": "Spanish Grand Prix",
            "sessions": [
                {
                    "date": "2021-05-07T11:30:00+02:00",
                    "date_utc": "2021-05-07T09:30:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2021-05-07T15:00:00+02:00",
                    "date_utc": "2021-05-07T13:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2021-05-08T12:00:00+02:00",
                    "date_utc": "2021-05-08T10:00:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2021-05-08T15:00:00+02:00",
                    "date_utc": "2021-05-08T13:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2021-05-09T15:00:00+02:00",
                    "date_utc": "2021-05-09T13:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2021-05-23",
            "race": "Monaco Grand Prix",
            "sessions": [
                {
                    "date": "2021-05-20T11:30:00+02:00",
                    "date_utc": "2021-05-20T09:30:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2021-05-20T15:00:00+02:00",
                    "date_utc": "2021-05-20T13:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2021-05-22T12:00:00+02:00",
                    "date_utc": "2021-05-22T10:00:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2021-05-22T15:00:00+02:00",
                    "date_utc": "2021-05-22T13:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2021-05-23T15:00:00+02:00",
                    "date_utc": "2021-05-23T13:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2021-06-06",
            "race": "Azerbaijan Grand Prix",
            "sessions": [
                {
                    "date": "2021-06-04T12:30:00+04:00",
                    "date_utc": "2021-06-04T08:30:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2021-06-04T16:00:00+04:00",
                    "date_utc": "2021-06-04T12:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2021-06-05T13:00:00+04:00",
                    "date_utc": "2021-06-05T09:00:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2021-06-05T16:00:00+04:00",
                    "date_utc": "2021-06-05T12:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2021-06-06T16:00:00+04:00",
                    "date_utc": "2021-06-06T12:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2021-06-20",
            "race": "French Grand Prix",
            "sessions": [
                {
                    "date": "2021-06-18T11:30:00+02:00",
                    "date_utc": "2021-06-18T09:30:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2021-06-18T15:00:00+02:00",
                    "date_utc": "2021-06-18T13:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2021-06-19T12:00:00+02:00",
                    "date_utc": "2021-06-19T10:00:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2021-06-19T15:00:00+02:00",
                    "date_utc": "2021-06-19T13:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2021-06-20T15:00:00+02:00",
                    "date_utc": "2021-06-20T13:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2021-06-27",
            "race": "Styrian Grand Prix",
            "sessions": [
                {
                    "date": "2021-06-25T11:30:00+02:00",
                    "date_utc": "2021-06-25T09:30:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2021-06-25T15:00:00+02:00",
                    "date_utc": "2021-06-25T13:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2021-06-26T12:00:00+02:00",
                    "date_utc": "2021-06-26T10:00:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2021-06-26T15:00:00+02:00",
                    "date_utc": "2021-06-26T13:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2021-06-27T15:00:00+02:00",
                    "date_utc": "2021-06-27T13:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2021-07-04",
            "race": "Austrian Grand Prix",
            "sessions": [
                {
                    "date": "2021-07-02T11:30:00+02:00",
                    "date_utc": "2021-07-02T09:30:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2021-07-02T15:00:00+02:00",
                    "date_utc": "2021-07-02T13:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2021-07-03T12:00:00+02:00",
                    "date_utc": "2021-07-03T10:00:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2021-07-03T15:00:00+02:00",
                    "date_utc": "2021-07-03T13:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2021-07-04T15:00:00+02:00",
                    "date_utc": "2021-07-04T13:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2021-07-18",
            "race": "British Grand Prix",
            "sessions": [
                {
                    "date": "2021-07-16T14:30:00+01:00",
                    "date_utc": "2021-07-16T13:30:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2021-07-16T18:00:00+01:00",
                    "date_utc": "2021-07-16T17:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2021-07-17T12:00:00+01:00",
                    "date_utc": "2021-07-17T11:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2021-07-17T16:30:00+01:00",
                    "date_utc": "2021-07-17T15:30:00",
                    "name": "Sprint"
                },
                {
                    "date": "2021-07-18T15:00:00+01:00",
                    "date_utc": "2021-07-18T14:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2021-08-01",
            "race": "Hungarian Grand Prix",
            "sessions": [
                {
                    "date": "2021-07-30T11:30:00+02:00",
                    "date_utc": "2021-07-30T09:30:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2021-07-30T15:00:00+02:00",
                    "date_utc": "2021-07-30T13:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2021-07-31T12:00:00+02:00",
                    "date_utc": "2021-07-31T10:00:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2021-07-31T15:00:00+02:00",
                    "date_utc": "2021-07-31T13:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2021-08-01T15:00:00+02:00",
                    "date_utc": "2021-08-01T13:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2021-08-29",
            "race": "Belgian Grand Prix",
            "sessions": [
                {
                    "date": "2021-08-27T11:30:00+02:00",
                    "date_utc": "2021-08-27T09:30:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2021-08-27T15:00:00+02:00",
                    "date_utc": "2021-08-27T13:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2021-08-28T12:00:00+02:00",
                    "date_utc": "2021-08-28T10:00:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2021-08-28T15:00:00+02:00",
                    "date_utc": "2021-08-28T13:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2021-08-29T15:00:00+02:00",
                    "date_utc": "2021-08-29T13:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2021-09-05",
            "race": "Dutch Grand Prix",
            "sessions": [
                {
                    "date": "2021-09-03T11:30:00+02:00",
                    "date_utc": "2021-09-03T09:30:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2021-09-03T15:00:00+02:00",
                    "date_utc": "2021-09-03T13:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2021-09-04T12:00:00+02:00",
                    "date_utc": "2021-09-04T10:00:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2021-09-04T15:00:00+02:00",
                    "date_utc": "2021-09-04T13:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2021-09-05T15:00:00+02:00",
                    "date_utc": "2021-09-05T13:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2021-09-12",
            "race": "Italian Grand Prix",
            "sessions": [
                {
                    "date": "2021-09-10T14:30:00+02:00",
                    "date_utc": "2021-09-10T12:30:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2021-09-10T18:00:00+02:00",
                    "date_utc": "2021-09-10T16:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2021-09-11T12:00:00+02:00",
                    "date_utc": "2021-09-11T10:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2021-09-11T16:30:00+02:00",
                    "date_utc": "2021-09-11T14:30:00",
                    "name": "Sprint"
                },
                {
                    "date": "2021-09-12T15:00:00+02:00",
                    "date_utc": "2021-09-12T13:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2021-09-26",
            "race": "Russian Grand Prix",
            "sessions": [
                {
                    "date": "2021-09-24T11:30:00+03:00",
                    "date_utc": "2021-09-24T08:30:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2021-09-24T15:00:00+03:00",
                    "date_utc": "2021-09-24T12:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2021-09-25T12:00:00+03:00",
                    "date_utc": "2021-09-25T09:00:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2021-09-25T15:00:00+03:00",
                    "date_utc": "2021-09-25T12:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2021-09-26T15:00:00+03:00",
                    "date_utc": "2021-09-26T12:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2021-10-10",
            "race": "Turkish Grand Prix",
            "sessions": [
                {
                    "date": "2021-10-08T11:30:00+03:00",
                    "date_utc": "2021-10-08T08:30:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2021-10-08T15:00:00+03:00",
                    "date_utc": "2021-10-08T12:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2021-10-09T12:00:00+03:00",
                    "date_utc": "2021-10-09T09:00:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2021-10-09T15:00:00+03:00",
                    "date_utc": "2021-10-09T12:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2021-10-10T15:00:00+03:00",
                    "date_utc": "2021-10-10T12:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2021-10-24",
            "race": "United States Grand Prix",
            "sessions": [
                {
                    "date": "2021-10-22T11:30:00-05:00",
                    "date_utc": "2021-10-22T16:30:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2021-10-22T15:00:00-05:00",
                    "date_utc": "2021-10-22T20:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2021-10-23T13:00:00-05:00",
                    "date_utc": "2021-10-23T18:00:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2021-10-23T16:00:00-05:00",
                    "date_utc": "2021-10-23T21:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2021-10-24T14:00:00-05:00",
                    "date_utc": "2021-10-24T19:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2021-11-07",
            "race": "Mexico City Grand Prix",
            "sessions": [
                {
                    "date": "2021-11-05T11:30:00-06:00",
                    "date_utc": "2021-11-05T17:30:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2021-11-05T15:00:00-06:00",
                    "date_utc": "2021-11-05T21:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2021-11-06T11:00:00-06:00",
                    "date_utc": "2021-11-06T17:00:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2021-11-06T14:00:00-06:00",
                    "date_utc": "2021-11-06T20:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2021-11-07T13:00:00-06:00",
                    "date_utc": "2021-11-07T19:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2021-11-14",
            "race": "S\u00e3o Paulo Grand Prix",
            "sessions": [
                {
                    "date": "2021-11-12T12:30:00-03:00",
                    "date_utc": "2021-11-12T15:30:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2021-11-12T16:00:00-03:00",
                    "date_utc": "2021-11-12T19:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2021-11-13T12:00:00-03:00",
                    "date_utc": "2021-11-13T15:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2021-11-13T16:30:00-03:00",
                    "date_utc": "2021-11-13T19:30:00",
                    "name": "Sprint"
                },
                {
                    "date": "2021-11-14T14:00:00-03:00",
                    "date_utc": "2021-11-14T17:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2021-11-21",
            "race": "Qatar Grand Prix",
            "sessions": [
                {
                    "date": "2021-11-19T13:30:00+03:00",
                    "date_utc": "2021-11-19T10:30:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2021-11-19T17:00:00+03:00",
                    "date_utc": "2021-11-19T14:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2021-11-20T14:00:00+03:00",
                    "date_utc": "2021-11-20T11:00:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2021-11-20T17:00:00+03:00",
                    "date_utc": "2021-11-20T14:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2021-11-21T17:00:00+03:00",
                    "date_utc": "2021-11-21T14:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2021-12-05",
            "race": "Saudi Arabian Grand Prix",
            "sessions": [
                {
                    "date": "2021-12-03T16:30:00+03:00",
                    "date_utc": "2021-12-03T13:30:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2021-12-03T20:00:00+03:00",
                    "date_utc": "2021-12-03T17:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2021-12-04T17:00:00+03:00",
                    "date_utc": "2021-12-04T14:00:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2021-12-04T20:00:00+03:00",
                    "date_utc": "2021-12-04T17:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2021-12-05T20:30:00+03:00",
                    "date_utc": "2021-12-05T17:30:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2021-12-12",
            "race": "Abu Dhabi Grand Prix",
            "sessions": [
                {
                    "date": "2021-12-10T13:30:00+04:00",
                    "date_utc": "2021-12-10T09:30:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2021-12-10T17:00:00+04:00",
                    "date_utc": "2021-12-10T13:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2021-12-11T14:00:00+04:00",
                    "date_utc": "2021-12-11T10:00:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2021-12-11T17:00:00+04:00",
                    "date_utc": "2021-12-11T13:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2021-12-12T17:00:00+04:00",
                    "date_utc": "2021-12-12T13:00:00",
                    "name": "Race"
                }
            ]
        }
    ],
    "2022": [
        {
            "event_date": "2022-03-20",
            "race": "Bahrain Grand Prix",
            "sessions": [
                {
                    "date": "2022-03-18T15:00:00+03:00",
                    "date_utc": "2022-03-18T12:00:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2022-03-18T18:00:00+03:00",
                    "date_utc": "2022-03-18T15:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2022-03-19T15:00:00+03:00",
                    "date_utc": "2022-03-19T12:00:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2022-03-19T18:00:00+03:00",
                    "date_utc": "2022-03-19T15:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2022-03-20T18:00:00+03:00",
                    "date_utc": "2022-03-20T15:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2022-03-27",
            "race": "Saudi Arabian Grand Prix",
            "sessions": [
                {
                    "date": "2022-03-25T17:00:00+03:00",
                    "date_utc": "2022-03-25T14:00:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2022-03-25T20:00:00+03:00",
                    "date_utc": "2022-03-25T17:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2022-03-26T17:00:00+03:00",
                    "date_utc": "2022-03-26T14:00:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2022-03-26T20:00:00+03:00",
                    "date_utc": "2022-03-26T17:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2022-03-27T20:00:00+03:00",
                    "date_utc": "2022-03-27T17:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2022-04-10",
            "race": "Australian Grand Prix",
            "sessions": [
                {
                    "date": "2022-04-08T13:00:00+10:00",
                    "date_utc": "2022-04-08T03:00:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2022-04-08T16:00:00+10:00",
                    "date_utc": "2022-04-08T06:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2022-04-09T13:00:00+10:00",
                    "date_utc": "2022-04-09T03:00:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2022-04-09T16:00:00+10:00",
                    "date_utc": "2022-04-09T06:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2022-04-10T15:00:00+10:00",
                    "date_utc": "2022-04-10T05:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2022-04-24",
            "race": "Emilia Romagna Grand Prix",
            "sessions": [
                {
                    "date": "2022-04-22T13:30:00+02:00",
                    "date_utc": "2022-04-22T11:30:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2022-04-22T17:00:00+02:00",
                    "date_utc": "2022-04-22T15:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2022-04-23T12:30:00+02:00",
                    "date_utc": "2022-04-23T10:30:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2022-04-23T16:30:00+02:00",
                    "date_utc": "2022-04-23T14:30:00",
                    "name": "Sprint"
                },
                {
                    "date": "2022-04-24T15:00:00+02:00",
                    "date_utc": "2022-04-24T13:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2022-05-08",
            "race": "Miami Grand Prix",
            "sessions": [
                {
                    "date": "2022-05-06T14:30:00-04:00",
                    "date_utc": "2022-05-06T18:30:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2022-05-06T17:30:00-04:00",
                    "date_utc": "2022-05-06T21:30:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2022-05-07T13:00:00-04:00",
                    "date_utc": "2022-05-07T17:00:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2022-05-07T16:00:00-04:00",
                    "date_utc": "2022-05-07T20:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2022-05-08T15:30:00-04:00",
                    "date_utc": "2022-05-08T19:30:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2022-05-22",
            "race": "Spanish Grand Prix",
            "sessions": [
                {
                    "date": "2022-05-20T14:00:00+02:00",
                    "date_utc": "2022-05-20T12:00:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2022-05-20T17:00:00+02:00",
                    "date_utc": "2022-05-20T15:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2022-05-21T13:00:00+02:00",
                    "date_utc": "2022-05-21T11:00:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2022-05-21T16:00:00+02:00",
                    "date_utc": "2022-05-21T14:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2022-05-22T15:00:00+02:00",
                    "date_utc": "2022-05-22T13:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2022-05-29",
            "race": "Monaco Grand Prix",
            "sessions": [
                {
                    "date": "2022-05-27T14:00:00+02:00",
                    "date_utc": "2022-05-27T12:00:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2022-05-27T17:00:00+02:00",
                    "date_utc": "2022-05-27T15:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2022-05-28T13:00:00+02:00",
                    "date_utc": "2022-05-28T11:00:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2022-05-28T16:00:00+02:00",
                    "date_utc": "2022-05-28T14:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2022-05-29T15:00:00+02:00",
                    "date_utc": "2022-05-29T13:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2022-06-12",
            "race": "Azerbaijan Grand Prix",
            "sessions": [
                {
                    "date": "2022-06-10T15:00:00+04:00",
                    "date_utc": "2022-06-10T11:00:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2022-06-10T18:00:00+04:00",
                    "date_utc": "2022-06-10T14:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2022-06-11T15:00:00+04:00",
                    "date_utc": "2022-06-11T11:00:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2022-06-11T18:00:00+04:00",
                    "date_utc": "2022-06-11T14:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2022-06-12T15:00:00+04:00",
                    "date_utc": "2022-06-12T11:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2022-06-19",
            "race": "Canadian Grand Prix",
            "sessions": [
                {
                    "date": "2022-06-17T14:00:00-04:00",
                    "date_utc": "2022-06-17T18:00:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2022-06-17T17:00:00-04:00",
                    "date_utc": "2022-06-17T21:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2022-06-18T13:00:00-04:00",
                    "date_utc": "2022-06-18T17:00:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2022-06-18T16:00:00-04:00",
                    "date_utc": "2022-06-18T20:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2022-06-19T14:00:00-04:00",
                    "date_utc": "2022-06-19T18:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2022-07-03",
            "race": "British Grand Prix",
            "sessions": [
                {
                    "date": "2022-07-01T13:00:00+01:00",
                    "date_utc": "2022-07-01T12:00:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2022-07-01T16:00:00+01:00",
                    "date_utc": "2022-07-01T15:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2022-07-02T12:00:00+01:00",
                    "date_utc": "2022-07-02T11:00:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2022-07-02T15:00:00+01:00",
                    "date_utc": "2022-07-02T14:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2022-07-03T15:00:00+01:00",
                    "date_utc": "2022-07-03T14:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2022-07-10",
            "race": "Austrian Grand Prix",
            "sessions": [
                {
                    "date": "2022-07-08T13:30:00+02:00",
                    "date_utc": "2022-07-08T11:30:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2022-07-08T17:00:00+02:00",
                    "date_utc": "2022-07-08T15:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2022-07-09T12:30:00+02:00",
                    "date_utc": "2022-07-09T10:30:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2022-07-09T16:30:00+02:00",
                    "date_utc": "2022-07-09T14:30:00",
                    "name": "Sprint"
                },
                {
                    "date": "2022-07-10T15:00:00+02:00",
                    "date_utc": "2022-07-10T13:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2022-07-24",
            "race": "French Grand Prix",
            "sessions": [
                {
                    "date": "2022-07-22T14:00:00+02:00",
                    "date_utc": "2022-07-22T12:00:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2022-07-22T17:00:00+02:00",
                    "date_utc": "2022-07-22T15:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2022-07-23T13:00:00+02:00",
                    "date_utc": "2022-07-23T11:00:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2022-07-23T16:00:00+02:00",
                    "date_utc": "2022-07-23T14:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2022-07-24T15:00:00+02:00",
                    "date_utc": "2022-07-24T13:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2022-07-31",
            "race": "Hungarian Grand Prix",
            "sessions": [
                {
                    "date": "2022-07-29T14:00:00+02:00",
                    "date_utc": "2022-07-29T12:00:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2022-07-29T17:00:00+02:00",
                    "date_utc": "2022-07-29T15:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2022-07-30T13:00:00+02:00",
                    "date_utc": "2022-07-30T11:00:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2022-07-30T16:00:00+02:00",
                    "date_utc": "2022-07-30T14:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2022-07-31T15:00:00+02:00",
                    "date_utc": "2022-07-31T13:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2022-08-28",
            "race": "Belgian Grand Prix",
            "sessions": [
                {
                    "date": "2022-08-26T14:00:00+02:00",
                    "date_utc": "2022-08-26T12:00:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2022-08-26T17:00:00+02:00",
                    "date_utc": "2022-08-26T15:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2022-08-27T13:00:00+02:00",
                    "date_utc": "2022-08-27T11:00:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2022-08-27T16:00:00+02:00",
                    "date_utc": "2022-08-27T14:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2022-08-28T15:00:00+02:00",
                    "date_utc": "2022-08-28T13:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2022-09-04",
            "race": "Dutch Grand Prix",
            "sessions": [
                {
                    "date": "2022-09-02T12:30:00+02:00",
                    "date_utc": "2022-09-02T10:30:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2022-09-02T16:00:00+02:00",
                    "date_utc": "2022-09-02T14:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2022-09-03T12:00:00+02:00",
                    "date_utc": "2022-09-03T10:00:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2022-09-03T15:00:00+02:00",
                    "date_utc": "2022-09-03T13:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2022-09-04T15:00:00+02:00",
                    "date_utc": "2022-09-04T13:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2022-09-11",
            "race": "Italian Grand Prix",
            "sessions": [
                {
                    "date": "2022-09-09T14:00:00+02:00",
                    "date_utc": "2022-09-09T12:00:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2022-09-09T17:00:00+02:00",
                    "date_utc": "2022-09-09T15:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2022-09-10T13:00:00+02:00",
                    "date_utc": "2022-09-10T11:00:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2022-09-10T16:00:00+02:00",
                    "date_utc": "2022-09-10T14:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2022-09-11T15:00:00+02:00",
                    "date_utc": "2022-09-11T13:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2022-10-02",
            "race": "Singapore Grand Prix",
            "sessions": [
                {
                    "date": "2022-09-30T18:00:00+08:00",
                    "date_utc": "2022-09-30T10:00:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2022-09-30T21:00:00+08:00",
                    "date_utc": "2022-09-30T13:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2022-10-01T18:00:00+08:00",
                    "date_utc": "2022-10-01T10:00:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2022-10-01T21:00:00+08:00",
                    "date_utc": "2022-10-01T13:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2022-10-02T20:00:00+08:00",
                    "date_utc": "2022-10-02T12:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2022-10-09",
            "race": "Japanese Grand Prix",
            "sessions": [
                {
                    "date": "2022-10-07T12:00:00+09:00",
                    "date_utc": "2022-10-07T03:00:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2022-10-07T15:00:00+09:00",
                    "date_utc": "2022-10-07T06:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2022-10-08T12:00:00+09:00",
                    "date_utc": "2022-10-08T03:00:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2022-10-08T15:00:00+09:00",
                    "date_utc": "2022-10-08T06:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2022-10-09T14:00:00+09:00",
                    "date_utc": "2022-10-09T05:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2022-10-23",
            "race": "United States Grand Prix",
            "sessions": [
                {
                    "date": "2022-10-21T14:00:00-05:00",
                    "date_utc": "2022-10-21T19:00:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2022-10-21T17:00:00-05:00",
                    "date_utc": "2022-10-21T22:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2022-10-22T14:00:00-05:00",
                    "date_utc": "2022-10-22T19:00:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2022-10-22T17:00:00-05:00",
                    "date_utc": "2022-10-22T22:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2022-10-23T14:00:00-05:00",
                    "date_utc": "2022-10-23T19:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2022-10-30",
            "race": "Mexico City Grand Prix",
            "sessions": [
                {
                    "date": "2022-10-28T13:00:00-06:00",
                    "date_utc": "2022-10-28T19:00:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2022-10-28T16:00:00-06:00",
                    "date_utc": "2022-10-28T22:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2022-10-29T12:00:00-06:00",
                    "date_utc": "2022-10-29T18:00:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2022-10-29T15:00:00-06:00",
                    "date_utc": "2022-10-29T21:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2022-10-30T14:00:00-06:00",
                    "date_utc": "2022-10-30T20:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2022-11-13",
            "race": "S\u00e3o Paulo Grand Prix",
            "sessions": [
                {
                    "date": "2022-11-11T12:30:00-03:00",
                    "date_utc": "2022-11-11T15:30:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2022-11-11T16:00:00-03:00",
                    "date_utc": "2022-11-11T19:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2022-11-12T12:30:00-03:00",
                    "date_utc": "2022-11-12T15:30:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2022-11-12T16:30:00-03:00",
                    "date_utc": "2022-11-12T19:30:00",
                    "name": "Sprint"
                },
                {
                    "date": "2022-11-13T15:00:00-03:00",
                    "date_utc": "2022-11-13T18:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2022-11-20",
            "race": "Abu Dhabi Grand Prix",
            "sessions": [
                {
                    "date": "2022-11-18T14:00:00+04:00",
                    "date_utc": "2022-11-18T10:00:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2022-11-18T17:00:00+04:00",
                    "date_utc": "2022-11-18T13:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2022-11-19T14:30:00+04:00",
                    "date_utc": "2022-11-19T10:30:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2022-11-19T18:00:00+04:00",
                    "date_utc": "2022-11-19T14:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2022-11-20T17:00:00+04:00",
                    "date_utc": "2022-11-20T13:00:00",
                    "name": "Race"
                }
            ]
        }
    ],
    "2023": [
        {
            "event_date": "2023-03-05",
            "race": "Bahrain Grand Prix",
            "sessions": [
                {
                    "date": "2023-03-03T14:30:00+03:00",
                    "date_utc": "2023-03-03T11:30:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2023-03-03T18:00:00+03:00",
                    "date_utc": "2023-03-03T15:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2023-03-04T14:30:00+03:00",
                    "date_utc": "2023-03-04T11:30:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2023-03-04T18:00:00+03:00",
                    "date_utc": "2023-03-04T15:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2023-03-05T18:00:00+03:00",
                    "date_utc": "2023-03-05T15:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2023-03-19",
            "race": "Saudi Arabian Grand Prix",
            "sessions": [
                {
                    "date": "2023-03-17T16:30:00+03:00",
                    "date_utc": "2023-03-17T13:30:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2023-03-17T20:00:00+03:00",
                    "date_utc": "2023-03-17T17:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2023-03-18T16:30:00+03:00",
                    "date_utc": "2023-03-18T13:30:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2023-03-18T20:00:00+03:00",
                    "date_utc": "2023-03-18T17:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2023-03-19T20:00:00+03:00",
                    "date_utc": "2023-03-19T17:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2023-04-02",
            "race": "Australian Grand Prix",
            "sessions": [
                {
                    "date": "2023-03-31T12:30:00+10:00",
                    "date_utc": "2023-03-31T02:30:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2023-03-31T16:00:00+10:00",
                    "date_utc": "2023-03-31T06:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2023-04-01T12:30:00+10:00",
                    "date_utc": "2023-04-01T02:30:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2023-04-01T16:00:00+10:00",
                    "date_utc": "2023-04-01T06:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2023-04-02T15:00:00+10:00",
                    "date_utc": "2023-04-02T05:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2023-04-30",
            "race": "Azerbaijan Grand Prix",
            "sessions": [
                {
                    "date": "2023-04-28T13:30:00+04:00",
                    "date_utc": "2023-04-28T09:30:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2023-04-28T17:00:00+04:00",
                    "date_utc": "2023-04-28T13:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2023-04-29T12:30:00+04:00",
                    "date_utc": "2023-04-29T08:30:00",
                    "name": "Sprint Shootout"
                },
                {
                    "date": "2023-04-29T17:30:00+04:00",
                    "date_utc": "2023-04-29T13:30:00",
                    "name": "Sprint"
                },
                {
                    "date": "2023-04-30T15:00:00+04:00",
                    "date_utc": "2023-04-30T11:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2023-05-07",
            "race": "Miami Grand Prix",
            "sessions": [
                {
                    "date": "2023-05-05T14:00:00-04:00",
                    "date_utc": "2023-05-05T18:00:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2023-05-05T17:30:00-04:00",
                    "date_utc": "2023-05-05T21:30:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2023-05-06T12:30:00-04:00",
                    "date_utc": "2023-05-06T16:30:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2023-05-06T16:00:00-04:00",
                    "date_utc": "2023-05-06T20:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2023-05-07T15:30:00-04:00",
                    "date_utc": "2023-05-07T19:30:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2023-05-28",
            "race": "Monaco Grand Prix",
            "sessions": [
                {
                    "date": "2023-05-26T13:30:00+02:00",
                    "date_utc": "2023-05-26T11:30:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2023-05-26T17:00:00+02:00",
                    "date_utc": "2023-05-26T15:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2023-05-27T12:30:00+02:00",
                    "date_utc": "2023-05-27T10:30:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2023-05-27T16:00:00+02:00",
                    "date_utc": "2023-05-27T14:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2023-05-28T15:00:00+02:00",
                    "date_utc": "2023-05-28T13:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2023-06-04",
            "race": "Spanish Grand Prix",
            "sessions": [
                {
                    "date": "2023-06-02T13:30:00+02:00",
                    "date_utc": "2023-06-02T11:30:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2023-06-02T17:00:00+02:00",
                    "date_utc": "2023-06-02T15:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2023-06-03T12:30:00+02:00",
                    "date_utc": "2023-06-03T10:30:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2023-06-03T16:00:00+02:00",
                    "date_utc": "2023-06-03T14:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2023-06-04T15:00:00+02:00",
                    "date_utc": "2023-06-04T13:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2023-06-18",
            "race": "Canadian Grand Prix",
            "sessions": [
                {
                    "date": "2023-06-16T13:30:00-04:00",
                    "date_utc": "2023-06-16T17:30:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2023-06-16T16:30:00-04:00",
                    "date_utc": "2023-06-16T20:30:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2023-06-17T12:30:00-04:00",
                    "date_utc": "2023-06-17T16:30:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2023-06-17T16:00:00-04:00",
                    "date_utc": "2023-06-17T20:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2023-06-18T14:00:00-04:00",
                    "date_utc": "2023-06-18T18:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2023-07-02",
            "race": "Austrian Grand Prix",
            "sessions": [
                {
                    "date": "2023-06-30T13:30:00+02:00",
                    "date_utc": "2023-06-30T11:30:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2023-06-30T17:00:00+02:00",
                    "date_utc": "2023-06-30T15:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2023-07-01T12:00:00+02:00",
                    "date_utc": "2023-07-01T10:00:00",
                    "name": "Sprint Shootout"
                },
                {
                    "date": "2023-07-01T16:30:00+02:00",
                    "date_utc": "2023-07-01T14:30:00",
                    "name": "Sprint"
                },
                {
                    "date": "2023-07-02T15:00:00+02:00",
                    "date_utc": "2023-07-02T13:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2023-07-09",
            "race": "British Grand Prix",
            "sessions": [
                {
                    "date": "2023-07-07T12:30:00+01:00",
                    "date_utc": "2023-07-07T11:30:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2023-07-07T16:00:00+01:00",
                    "date_utc": "2023-07-07T15:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2023-07-08T11:30:00+01:00",
                    "date_utc": "2023-07-08T10:30:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2023-07-08T15:00:00+01:00",
                    "date_utc": "2023-07-08T14:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2023-07-09T15:00:00+01:00",
                    "date_utc": "2023-07-09T14:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2023-07-23",
            "race": "Hungarian Grand Prix",
            "sessions": [
                {
                    "date": "2023-07-21T13:30:00+02:00",
                    "date_utc": "2023-07-21T11:30:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2023-07-21T17:00:00+02:00",
                    "date_utc": "2023-07-21T15:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2023-07-22T12:30:00+02:00",
                    "date_utc": "2023-07-22T10:30:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2023-07-22T16:00:00+02:00",
                    "date_utc": "2023-07-22T14:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2023-07-23T15:00:00+02:00",
                    "date_utc": "2023-07-23T13:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2023-07-30",
            "race": "Belgian Grand Prix",
            "sessions": [
                {
                    "date": "2023-07-28T13:30:00+02:00",
                    "date_utc": "2023-07-28T11:30:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2023-07-28T17:00:00+02:00",
                    "date_utc": "2023-07-28T15:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2023-07-29T12:00:00+02:00",
                    "date_utc": "2023-07-29T10:00:00",
                    "name": "Sprint Shootout"
                },
                {
                    "date": "2023-07-29T17:05:00+02:00",
                    "date_utc": "2023-07-29T15:05:00",
                    "name": "Sprint"
                },
                {
                    "date": "2023-07-30T15:00:00+02:00",
                    "date_utc": "2023-07-30T13:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2023-08-27",
            "race": "Dutch Grand Prix",
            "sessions": [
                {
                    "date": "2023-08-25T12:30:00+02:00",
                    "date_utc": "2023-08-25T10:30:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2023-08-25T16:00:00+02:00",
                    "date_utc": "2023-08-25T14:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2023-08-26T11:30:00+02:00",
                    "date_utc": "2023-08-26T09:30:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2023-08-26T15:00:00+02:00",
                    "date_utc": "2023-08-26T13:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2023-08-27T15:00:00+02:00",
                    "date_utc": "2023-08-27T13:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2023-09-03",
            "race": "Italian Grand Prix",
            "sessions": [
                {
                    "date": "2023-09-01T13:30:00+02:00",
                    "date_utc": "2023-09-01T11:30:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2023-09-01T17:00:00+02:00",
                    "date_utc": "2023-09-01T15:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2023-09-02T12:30:00+02:00",
                    "date_utc": "2023-09-02T10:30:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2023-09-02T16:00:00+02:00",
                    "date_utc": "2023-09-02T14:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2023-09-03T15:00:00+02:00",
                    "date_utc": "2023-09-03T13:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2023-09-17",
            "race": "Singapore Grand Prix",
            "sessions": [
                {
                    "date": "2023-09-15T17:30:00+08:00",
                    "date_utc": "2023-09-15T09:30:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2023-09-15T21:00:00+08:00",
                    "date_utc": "2023-09-15T13:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2023-09-16T17:30:00+08:00",
                    "date_utc": "2023-09-16T09:30:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2023-09-16T21:00:00+08:00",
                    "date_utc": "2023-09-16T13:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2023-09-17T20:00:00+08:00",
                    "date_utc": "2023-09-17T12:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2023-09-24",
            "race": "Japanese Grand Prix",
            "sessions": [
                {
                    "date": "2023-09-22T11:30:00+09:00",
                    "date_utc": "2023-09-22T02:30:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2023-09-22T15:00:00+09:00",
                    "date_utc": "2023-09-22T06:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2023-09-23T11:30:00+09:00",
                    "date_utc": "2023-09-23T02:30:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2023-09-23T15:00:00+09:00",
                    "date_utc": "2023-09-23T06:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2023-09-24T14:00:00+09:00",
                    "date_utc": "2023-09-24T05:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2023-10-08",
            "race": "Qatar Grand Prix",
            "sessions": [
                {
                    "date": "2023-10-06T16:30:00+03:00",
                    "date_utc": "2023-10-06T13:30:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2023-10-06T20:00:00+03:00",
                    "date_utc": "2023-10-06T17:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2023-10-07T16:20:00+03:00",
                    "date_utc": "2023-10-07T13:20:00",
                    "name": "Sprint Shootout"
                },
                {
                    "date": "2023-10-07T20:30:00+03:00",
                    "date_utc": "2023-10-07T17:30:00",
                    "name": "Sprint"
                },
                {
                    "date": "2023-10-08T20:00:00+03:00",
                    "date_utc": "2023-10-08T17:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2023-10-22",
            "race": "United States Grand Prix",
            "sessions": [
                {
                    "date": "2023-10-20T12:30:00-05:00",
                    "date_utc": "2023-10-20T17:30:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2023-10-20T16:00:00-05:00",
                    "date_utc": "2023-10-20T21:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2023-10-21T12:30:00-05:00",
                    "date_utc": "2023-10-21T17:30:00",
                    "name": "Sprint Shootout"
                },
                {
                    "date": "2023-10-21T17:00:00-05:00",
                    "date_utc": "2023-10-21T22:00:00",
                    "name": "Sprint"
                },
                {
                    "date": "2023-10-22T14:00:00-05:00",
                    "date_utc": "2023-10-22T19:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2023-10-29",
            "race": "Mexico City Grand Prix",
            "sessions": [
                {
                    "date": "2023-10-27T12:30:00-06:00",
                    "date_utc": "2023-10-27T18:30:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2023-10-27T16:00:00-06:00",
                    "date_utc": "2023-10-27T22:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2023-10-28T11:30:00-06:00",
                    "date_utc": "2023-10-28T17:30:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2023-10-28T15:00:00-06:00",
                    "date_utc": "2023-10-28T21:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2023-10-29T14:00:00-06:00",
                    "date_utc": "2023-10-29T20:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2023-11-05",
            "race": "S\u00e3o Paulo Grand Prix",
            "sessions": [
                {
                    "date": "2023-11-03T11:30:00-03:00",
                    "date_utc": "2023-11-03T14:30:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2023-11-03T15:00:00-03:00",
                    "date_utc": "2023-11-03T18:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2023-11-04T11:00:00-03:00",
                    "date_utc": "2023-11-04T14:00:00",
                    "name": "Sprint Shootout"
                },
                {
                    "date": "2023-11-04T15:30:00-03:00",
                    "date_utc": "2023-11-04T18:30:00",
                    "name": "Sprint"
                },
                {
                    "date": "2023-11-05T14:00:00-03:00",
                    "date_utc": "2023-11-05T17:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2023-11-18",
            "race": "Las Vegas Grand Prix",
            "sessions": [
                {
                    "date": "2023-11-16T20:30:00-08:00",
                    "date_utc": "2023-11-17T04:30:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2023-11-17T02:30:00-08:00",
                    "date_utc": "2023-11-17T10:30:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2023-11-17T20:30:00-08:00",
                    "date_utc": "2023-11-18T04:30:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2023-11-18T00:00:00-08:00",
                    "date_utc": "2023-11-18T08:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2023-11-18T22:00:00-08:00",
                    "date_utc": "2023-11-19T06:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2023-11-26",
            "race": "Abu Dhabi Grand Prix",
            "sessions": [
                {
                    "date": "2023-11-24T13:30:00+04:00",
                    "date_utc": "2023-11-24T09:30:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2023-11-24T17:00:00+04:00",
                    "date_utc": "2023-11-24T13:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2023-11-25T14:30:00+04:00",
                    "date_utc": "2023-11-25T10:30:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2023-11-25T18:00:00+04:00",
                    "date_utc": "2023-11-25T14:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2023-11-26T17:00:00+04:00",
                    "date_utc": "2023-11-26T13:00:00",
                    "name": "Race"
                }
            ]
        }
    ],
    "2024": [
        {
            "event_date": "2024-03-02",
            "race": "Bahrain Grand Prix",
            "sessions": [
                {
                    "date": "2024-02-29T14:30:00+03:00",
                    "date_utc": "2024-02-29T11:30:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2024-02-29T18:00:00+03:00",
                    "date_utc": "2024-02-29T15:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2024-03-01T15:30:00+03:00",
                    "date_utc": "2024-03-01T12:30:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2024-03-01T19:00:00+03:00",
                    "date_utc": "2024-03-01T16:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2024-03-02T18:00:00+03:00",
                    "date_utc": "2024-03-02T15:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2024-03-09",
            "race": "Saudi Arabian Grand Prix",
            "sessions": [
                {
                    "date": "2024-03-07T16:30:00+03:00",
                    "date_utc": "2024-03-07T13:30:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2024-03-07T20:10:00+03:00",
                    "date_utc": "2024-03-07T17:10:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2024-03-08T16:30:00+03:00",
                    "date_utc": "2024-03-08T13:30:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2024-03-08T20:00:00+03:00",
                    "date_utc": "2024-03-08T17:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2024-03-09T20:00:00+03:00",
                    "date_utc": "2024-03-09T17:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2024-03-24",
            "race": "Australian Grand Prix",
            "sessions": [
                {
                    "date": "2024-03-22T12:30:00+11:00",
                    "date_utc": "2024-03-22T01:30:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2024-03-22T16:00:00+11:00",
                    "date_utc": "2024-03-22T05:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2024-03-23T12:30:00+11:00",
                    "date_utc": "2024-03-23T01:30:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2024-03-23T16:00:00+11:00",
                    "date_utc": "2024-03-23T05:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2024-03-24T15:00:00+11:00",
                    "date_utc": "2024-03-24T04:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2024-04-07",
            "race": "Japanese Grand Prix",
            "sessions": [
                {
                    "date": "2024-04-05T11:30:00+09:00",
                    "date_utc": "2024-04-05T02:30:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2024-04-05T15:00:00+09:00",
                    "date_utc": "2024-04-05T06:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2024-04-06T11:30:00+09:00",
                    "date_utc": "2024-04-06T02:30:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2024-04-06T15:00:00+09:00",
                    "date_utc": "2024-04-06T06:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2024-04-07T14:00:00+09:00",
                    "date_utc": "2024-04-07T05:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2024-04-21",
            "race": "Chinese Grand Prix",
            "sessions": [
                {
                    "date": "2024-04-19T11:30:00+08:00",
                    "date_utc": "2024-04-19T03:30:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2024-04-19T15:30:00+08:00",
                    "date_utc": "2024-04-19T07:30:00",
                    "name": "Sprint Qualifying"
                },
                {
                    "date": "2024-04-20T11:00:00+08:00",
                    "date_utc": "2024-04-20T03:00:00",
                    "name": "Sprint"
                },
                {
                    "date": "2024-04-20T15:00:00+08:00",
                    "date_utc": "2024-04-20T07:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2024-04-21T15:00:00+08:00",
                    "date_utc": "2024-04-21T07:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2024-05-05",
            "race": "Miami Grand Prix",
            "sessions": [
                {
                    "date": "2024-05-03T12:30:00-04:00",
                    "date_utc": "2024-05-03T16:30:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2024-05-03T16:30:00-04:00",
                    "date_utc": "2024-05-03T20:30:00",
                    "name": "Sprint Qualifying"
                },
                {
                    "date": "2024-05-04T12:00:00-04:00",
                    "date_utc": "2024-05-04T16:00:00",
                    "name": "Sprint"
                },
                {
                    "date": "2024-05-04T16:00:00-04:00",
                    "date_utc": "2024-05-04T20:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2024-05-05T16:00:00-04:00",
                    "date_utc": "2024-05-05T20:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2024-05-19",
            "race": "Emilia Romagna Grand Prix",
            "sessions": [
                {
                    "date": "2024-05-17T13:30:00+02:00",
                    "date_utc": "2024-05-17T11:30:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2024-05-17T17:00:00+02:00",
                    "date_utc": "2024-05-17T15:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2024-05-18T12:30:00+02:00",
                    "date_utc": "2024-05-18T10:30:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2024-05-18T16:00:00+02:00",
                    "date_utc": "2024-05-18T14:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2024-05-19T15:00:00+02:00",
                    "date_utc": "2024-05-19T13:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2024-05-26",
            "race": "Monaco Grand Prix",
            "sessions": [
                {
                    "date": "2024-05-24T13:30:00+02:00",
                    "date_utc": "2024-05-24T11:30:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2024-05-24T17:00:00+02:00",
                    "date_utc": "2024-05-24T15:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2024-05-25T12:30:00+02:00",
                    "date_utc": "2024-05-25T10:30:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2024-05-25T16:00:00+02:00",
                    "date_utc": "2024-05-25T14:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2024-05-26T15:00:00+02:00",
                    "date_utc": "2024-05-26T13:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2024-06-09",
            "race": "Canadian Grand Prix",
            "sessions": [
                {
                    "date": "2024-06-07T13:30:00-04:00",
                    "date_utc": "2024-06-07T17:30:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2024-06-07T17:00:00-04:00",
                    "date_utc": "2024-06-07T21:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2024-06-08T12:30:00-04:00",
                    "date_utc": "2024-06-08T16:30:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2024-06-08T16:00:00-04:00",
                    "date_utc": "2024-06-08T20:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2024-06-09T14:00:00-04:00",
                    "date_utc": "2024-06-09T18:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2024-06-23",
            "race": "Spanish Grand Prix",
            "sessions": [
                {
                    "date": "2024-06-21T13:30:00+02:00",
                    "date_utc": "2024-06-21T11:30:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2024-06-21T17:00:00+02:00",
                    "date_utc": "2024-06-21T15:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2024-06-22T12:30:00+02:00",
                    "date_utc": "2024-06-22T10:30:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2024-06-22T16:00:00+02:00",
                    "date_utc": "2024-06-22T14:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2024-06-23T15:00:00+02:00",
                    "date_utc": "2024-06-23T13:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2024-06-30",
            "race": "Austrian Grand Prix",
            "sessions": [
                {
                    "date": "2024-06-28T12:30:00+02:00",
                    "date_utc": "2024-06-28T10:30:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2024-06-28T16:30:00+02:00",
                    "date_utc": "2024-06-28T14:30:00",
                    "name": "Sprint Qualifying"
                },
                {
                    "date": "2024-06-29T12:00:00+02:00",
                    "date_utc": "2024-06-29T10:00:00",
                    "name": "Sprint"
                },
                {
                    "date": "2024-06-29T16:00:00+02:00",
                    "date_utc": "2024-06-29T14:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2024-06-30T15:00:00+02:00",
                    "date_utc": "2024-06-30T13:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2024-07-07",
            "race": "British Grand Prix",
            "sessions": [
                {
                    "date": "2024-07-05T12:30:00+01:00",
                    "date_utc": "2024-07-05T11:30:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2024-07-05T16:00:00+01:00",
                    "date_utc": "2024-07-05T15:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2024-07-06T11:30:00+01:00",
                    "date_utc": "2024-07-06T10:30:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2024-07-06T15:00:00+01:00",
                    "date_utc": "2024-07-06T14:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2024-07-07T15:00:00+01:00",
                    "date_utc": "2024-07-07T14:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2024-07-21",
            "race": "Hungarian Grand Prix",
            "sessions": [
                {
                    "date": "2024-07-19T13:30:00+02:00",
                    "date_utc": "2024-07-19T11:30:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2024-07-19T17:00:00+02:00",
                    "date_utc": "2024-07-19T15:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2024-07-20T12:30:00+02:00",
                    "date_utc": "2024-07-20T10:30:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2024-07-20T16:00:00+02:00",
                    "date_utc": "2024-07-20T14:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2024-07-21T15:00:00+02:00",
                    "date_utc": "2024-07-21T13:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2024-07-28",
            "race": "Belgian Grand Prix",
            "sessions": [
                {
                    "date": "2024-07-26T13:30:00+02:00",
                    "date_utc": "2024-07-26T11:30:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2024-07-26T17:00:00+02:00",
                    "date_utc": "2024-07-26T15:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2024-07-27T12:30:00+02:00",
                    "date_utc": "2024-07-27T10:30:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2024-07-27T16:00:00+02:00",
                    "date_utc": "2024-07-27T14:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2024-07-28T15:00:00+02:00",
                    "date_utc": "2024-07-28T13:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2024-08-25",
            "race": "Dutch Grand Prix",
            "sessions": [
                {
                    "date": "2024-08-23T12:30:00+02:00",
                    "date_utc": "2024-08-23T10:30:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2024-08-23T16:00:00+02:00",
                    "date_utc": "2024-08-23T14:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2024-08-24T11:30:00+02:00",
                    "date_utc": "2024-08-24T09:30:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2024-08-24T15:00:00+02:00",
                    "date_utc": "2024-08-24T13:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2024-08-25T15:00:00+02:00",
                    "date_utc": "2024-08-25T13:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2024-09-01",
            "race": "Italian Grand Prix",
            "sessions": [
                {
                    "date": "2024-08-30T13:30:00+02:00",
                    "date_utc": "2024-08-30T11:30:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2024-08-30T17:00:00+02:00",
                    "date_utc": "2024-08-30T15:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2024-08-31T12:30:00+02:00",
                    "date_utc": "2024-08-31T10:30:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2024-08-31T16:00:00+02:00",
                    "date_utc": "2024-08-31T14:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2024-09-01T15:00:00+02:00",
                    "date_utc": "2024-09-01T13:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2024-09-15",
            "race": "Azerbaijan Grand Prix",
            "sessions": [
                {
                    "date": "2024-09-13T13:30:00+04:00",
                    "date_utc": "2024-09-13T09:30:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2024-09-13T17:00:00+04:00",
                    "date_utc": "2024-09-13T13:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2024-09-14T12:30:00+04:00",
                    "date_utc": "2024-09-14T08:30:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2024-09-14T16:00:00+04:00",
                    "date_utc": "2024-09-14T12:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2024-09-15T15:00:00+04:00",
                    "date_utc": "2024-09-15T11:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2024-09-22",
            "race": "Singapore Grand Prix",
            "sessions": [
                {
                    "date": "2024-09-20T17:30:00+08:00",
                    "date_utc": "2024-09-20T09:30:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2024-09-20T21:00:00+08:00",
                    "date_utc": "2024-09-20T13:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2024-09-21T17:30:00+08:00",
                    "date_utc": "2024-09-21T09:30:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2024-09-21T21:00:00+08:00",
                    "date_utc": "2024-09-21T13:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2024-09-22T20:00:00+08:00",
                    "date_utc": "2024-09-22T12:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2024-10-20",
            "race": "United States Grand Prix",
            "sessions": [
                {
                    "date": "2024-10-18T12:30:00-05:00",
                    "date_utc": "2024-10-18T17:30:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2024-10-18T16:30:00-05:00",
                    "date_utc": "2024-10-18T21:30:00",
                    "name": "Sprint Qualifying"
                },
                {
                    "date": "2024-10-19T13:00:00-05:00",
                    "date_utc": "2024-10-19T18:00:00",
                    "name": "Sprint"
                },
                {
                    "date": "2024-10-19T17:00:00-05:00",
                    "date_utc": "2024-10-19T22:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2024-10-20T14:00:00-05:00",
                    "date_utc": "2024-10-20T19:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2024-10-27",
            "race": "Mexico City Grand Prix",
            "sessions": [
                {
                    "date": "2024-10-25T12:30:00-06:00",
                    "date_utc": "2024-10-25T18:30:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2024-10-25T16:00:00-06:00",
                    "date_utc": "2024-10-25T22:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2024-10-26T11:30:00-06:00",
                    "date_utc": "2024-10-26T17:30:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2024-10-26T15:00:00-06:00",
                    "date_utc": "2024-10-26T21:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2024-10-27T14:00:00-06:00",
                    "date_utc": "2024-10-27T20:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2024-11-03",
            "race": "S\u00e3o Paulo Grand Prix",
            "sessions": [
                {
                    "date": "2024-11-01T11:30:00-03:00",
                    "date_utc": "2024-11-01T14:30:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2024-11-01T15:30:00-03:00",
                    "date_utc": "2024-11-01T18:30:00",
                    "name": "Sprint Qualifying"
                },
                {
                    "date": "2024-11-02T11:00:00-03:00",
                    "date_utc": "2024-11-02T14:00:00",
                    "name": "Sprint"
                },
                {
                    "date": "2024-11-03T07:30:00-03:00",
                    "date_utc": "2024-11-03T10:30:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2024-11-03T12:30:00-03:00",
                    "date_utc": "2024-11-03T15:30:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2024-11-23",
            "race": "Las Vegas Grand Prix",
            "sessions": [
                {
                    "date": "2024-11-21T18:30:00-08:00",
                    "date_utc": "2024-11-22T02:30:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2024-11-21T22:00:00-08:00",
                    "date_utc": "2024-11-22T06:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2024-11-22T18:30:00-08:00",
                    "date_utc": "2024-11-23T02:30:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2024-11-22T22:00:00-08:00",
                    "date_utc": "2024-11-23T06:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2024-11-23T22:00:00-08:00",
                    "date_utc": "2024-11-24T06:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2024-12-01",
            "race": "Qatar Grand Prix",
            "sessions": [
                {
                    "date": "2024-11-29T16:30:00+03:00",
                    "date_utc": "2024-11-29T13:30:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2024-11-29T20:30:00+03:00",
                    "date_utc": "2024-11-29T17:30:00",
                    "name": "Sprint Qualifying"
                },
                {
                    "date": "2024-11-30T17:00:00+03:00",
                    "date_utc": "2024-11-30T14:00:00",
                    "name": "Sprint"
                },
                {
                    "date": "2024-11-30T21:00:00+03:00",
                    "date_utc": "2024-11-30T18:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2024-12-01T19:00:00+03:00",
                    "date_utc": "2024-12-01T16:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2024-12-08",
            "race": "Abu Dhabi Grand Prix",
            "sessions": [
                {
                    "date": "2024-12-06T13:30:00+04:00",
                    "date_utc": "2024-12-06T09:30:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2024-12-06T17:00:00+04:00",
                    "date_utc": "2024-12-06T13:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2024-12-07T14:30:00+04:00",
                    "date_utc": "2024-12-07T10:30:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2024-12-07T18:00:00+04:00",
                    "date_utc": "2024-12-07T14:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2024-12-08T17:00:00+04:00",
                    "date_utc": "2024-12-08T13:00:00",
                    "name": "Race"
                }
            ]
        }
    ],
    "2025": [
        {
            "event_date": "2025-03-16",
            "race": "Australian Grand Prix",
            "sessions": [
                {
                    "date": "2025-03-14T12:30:00+11:00",
                    "date_utc": "2025-03-14T01:30:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2025-03-14T16:00:00+11:00",
                    "date_utc": "2025-03-14T05:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2025-03-15T12:30:00+11:00",
                    "date_utc": "2025-03-15T01:30:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2025-03-15T16:00:00+11:00",
                    "date_utc": "2025-03-15T05:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2025-03-16T15:00:00+11:00",
                    "date_utc": "2025-03-16T04:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2025-03-23",
            "race": "Chinese Grand Prix",
            "sessions": [
                {
                    "date": "2025-03-21T11:30:00+08:00",
                    "date_utc": "2025-03-21T03:30:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2025-03-21T15:30:00+08:00",
                    "date_utc": "2025-03-21T07:30:00",
                    "name": "Sprint Qualifying"
                },
                {
                    "date": "2025-03-22T11:00:00+08:00",
                    "date_utc": "2025-03-22T03:00:00",
                    "name": "Sprint"
                },
                {
                    "date": "2025-03-22T15:00:00+08:00",
                    "date_utc": "2025-03-22T07:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2025-03-23T15:00:00+08:00",
                    "date_utc": "2025-03-23T07:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2025-04-06",
            "race": "Japanese Grand Prix",
            "sessions": [
                {
                    "date": "2025-04-04T11:30:00+09:00",
                    "date_utc": "2025-04-04T02:30:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2025-04-04T15:00:00+09:00",
                    "date_utc": "2025-04-04T06:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2025-04-05T11:30:00+09:00",
                    "date_utc": "2025-04-05T02:30:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2025-04-05T15:00:00+09:00",
                    "date_utc": "2025-04-05T06:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2025-04-06T14:00:00+09:00",
                    "date_utc": "2025-04-06T05:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2025-04-13",
            "race": "Bahrain Grand Prix",
            "sessions": [
                {
                    "date": "2025-04-11T14:30:00+03:00",
                    "date_utc": "2025-04-11T11:30:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2025-04-11T18:00:00+03:00",
                    "date_utc": "2025-04-11T15:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2025-04-12T15:30:00+03:00",
                    "date_utc": "2025-04-12T12:30:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2025-04-12T19:00:00+03:00",
                    "date_utc": "2025-04-12T16:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2025-04-13T18:00:00+03:00",
                    "date_utc": "2025-04-13T15:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2025-04-20",
            "race": "Saudi Arabian Grand Prix",
            "sessions": [
                {
                    "date": "2025-04-18T16:30:00+03:00",
                    "date_utc": "2025-04-18T13:30:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2025-04-18T20:00:00+03:00",
                    "date_utc": "2025-04-18T17:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2025-04-19T16:30:00+03:00",
                    "date_utc": "2025-04-19T13:30:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2025-04-19T20:00:00+03:00",
                    "date_utc": "2025-04-19T17:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2025-04-20T20:00:00+03:00",
                    "date_utc": "2025-04-20T17:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2025-05-04",
            "race": "Miami Grand Prix",
            "sessions": [
                {
                    "date": "2025-05-02T12:30:00-04:00",
                    "date_utc": "2025-05-02T16:30:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2025-05-02T16:30:00-04:00",
                    "date_utc": "2025-05-02T20:30:00",
                    "name": "Sprint Qualifying"
                },
                {
                    "date": "2025-05-03T12:00:00-04:00",
                    "date_utc": "2025-05-03T16:00:00",
                    "name": "Sprint"
                },
                {
                    "date": "2025-05-03T16:00:00-04:00",
                    "date_utc": "2025-05-03T20:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2025-05-04T16:00:00-04:00",
                    "date_utc": "2025-05-04T20:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2025-05-18",
            "race": "Emilia Romagna Grand Prix",
            "sessions": [
                {
                    "date": "2025-05-16T13:30:00+02:00",
                    "date_utc": "2025-05-16T11:30:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2025-05-16T17:00:00+02:00",
                    "date_utc": "2025-05-16T15:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2025-05-17T12:30:00+02:00",
                    "date_utc": "2025-05-17T10:30:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2025-05-17T16:00:00+02:00",
                    "date_utc": "2025-05-17T14:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2025-05-18T15:00:00+02:00",
                    "date_utc": "2025-05-18T13:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2025-05-25",
            "race": "Monaco Grand Prix",
            "sessions": [
                {
                    "date": "2025-05-23T13:30:00+02:00",
                    "date_utc": "2025-05-23T11:30:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2025-05-23T17:00:00+02:00",
                    "date_utc": "2025-05-23T15:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2025-05-24T12:30:00+02:00",
                    "date_utc": "2025-05-24T10:30:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2025-05-24T16:00:00+02:00",
                    "date_utc": "2025-05-24T14:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2025-05-25T15:00:00+02:00",
                    "date_utc": "2025-05-25T13:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2025-06-01",
            "race": "Spanish Grand Prix",
            "sessions": [
                {
                    "date": "2025-05-30T13:30:00+02:00",
                    "date_utc": "2025-05-30T11:30:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2025-05-30T17:00:00+02:00",
                    "date_utc": "2025-05-30T15:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2025-05-31T12:30:00+02:00",
                    "date_utc": "2025-05-31T10:30:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2025-05-31T16:00:00+02:00",
                    "date_utc": "2025-05-31T14:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2025-06-01T15:00:00+02:00",
                    "date_utc": "2025-06-01T13:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2025-06-15",
            "race": "Canadian Grand Prix",
            "sessions": [
                {
                    "date": "2025-06-13T13:30:00-04:00",
                    "date_utc": "2025-06-13T17:30:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2025-06-13T17:00:00-04:00",
                    "date_utc": "2025-06-13T21:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2025-06-14T12:30:00-04:00",
                    "date_utc": "2025-06-14T16:30:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2025-06-14T16:00:00-04:00",
                    "date_utc": "2025-06-14T20:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2025-06-15T14:00:00-04:00",
                    "date_utc": "2025-06-15T18:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2025-06-29",
            "race": "Austrian Grand Prix",
            "sessions": [
                {
                    "date": "2025-06-27T13:30:00+02:00",
                    "date_utc": "2025-06-27T11:30:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2025-06-27T17:00:00+02:00",
                    "date_utc": "2025-06-27T15:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2025-06-28T12:30:00+02:00",
                    "date_utc": "2025-06-28T10:30:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2025-06-28T16:00:00+02:00",
                    "date_utc": "2025-06-28T14:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2025-06-29T15:00:00+02:00",
                    "date_utc": "2025-06-29T13:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2025-07-06",
            "race": "British Grand Prix",
            "sessions": [
                {
                    "date": "2025-07-04T12:30:00+01:00",
                    "date_utc": "2025-07-04T11:30:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2025-07-04T16:00:00+01:00",
                    "date_utc": "2025-07-04T15:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2025-07-05T11:30:00+01:00",
                    "date_utc": "2025-07-05T10:30:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2025-07-05T15:00:00+01:00",
                    "date_utc": "2025-07-05T14:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2025-07-06T15:00:00+01:00",
                    "date_utc": "2025-07-06T14:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2025-07-27",
            "race": "Belgian Grand Prix",
            "sessions": [
                {
                    "date": "2025-07-25T12:30:00+02:00",
                    "date_utc": "2025-07-25T10:30:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2025-07-25T16:30:00+02:00",
                    "date_utc": "2025-07-25T14:30:00",
                    "name": "Sprint Qualifying"
                },
                {
                    "date": "2025-07-26T12:00:00+02:00",
                    "date_utc": "2025-07-26T10:00:00",
                    "name": "Sprint"
                },
                {
                    "date": "2025-07-26T16:00:00+02:00",
                    "date_utc": "2025-07-26T14:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2025-07-27T15:00:00+02:00",
                    "date_utc": "2025-07-27T13:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2025-08-03",
            "race": "Hungarian Grand Prix",
            "sessions": [
                {
                    "date": "2025-08-01T13:30:00+02:00",
                    "date_utc": "2025-08-01T11:30:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2025-08-01T17:00:00+02:00",
                    "date_utc": "2025-08-01T15:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2025-08-02T12:30:00+02:00",
                    "date_utc": "2025-08-02T10:30:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2025-08-02T16:00:00+02:00",
                    "date_utc": "2025-08-02T14:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2025-08-03T15:00:00+02:00",
                    "date_utc": "2025-08-03T13:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2025-08-31",
            "race": "Dutch Grand Prix",
            "sessions": [
                {
                    "date": "2025-08-29T12:30:00+02:00",
                    "date_utc": "2025-08-29T10:30:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2025-08-29T16:00:00+02:00",
                    "date_utc": "2025-08-29T14:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2025-08-30T11:30:00+02:00",
                    "date_utc": "2025-08-30T09:30:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2025-08-30T15:00:00+02:00",
                    "date_utc": "2025-08-30T13:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2025-08-31T15:00:00+02:00",
                    "date_utc": "2025-08-31T13:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2025-09-07",
            "race": "Italian Grand Prix",
            "sessions": [
                {
                    "date": "2025-09-05T13:30:00+02:00",
                    "date_utc": "2025-09-05T11:30:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2025-09-05T17:00:00+02:00",
                    "date_utc": "2025-09-05T15:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2025-09-06T12:30:00+02:00",
                    "date_utc": "2025-09-06T10:30:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2025-09-06T16:00:00+02:00",
                    "date_utc": "2025-09-06T14:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2025-09-07T15:00:00+02:00",
                    "date_utc": "2025-09-07T13:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2025-09-21",
            "race": "Azerbaijan Grand Prix",
            "sessions": [
                {
                    "date": "2025-09-19T12:30:00+04:00",
                    "date_utc": "2025-09-19T08:30:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2025-09-19T16:00:00+04:00",
                    "date_utc": "2025-09-19T12:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2025-09-20T12:30:00+04:00",
                    "date_utc": "2025-09-20T08:30:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2025-09-20T16:00:00+04:00",
                    "date_utc": "2025-09-20T12:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2025-09-21T15:00:00+04:00",
                    "date_utc": "2025-09-21T11:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2025-10-05",
            "race": "Singapore Grand Prix",
            "sessions": [
                {
                    "date": "2025-10-03T17:30:00+08:00",
                    "date_utc": "2025-10-03T09:30:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2025-10-03T21:00:00+08:00",
                    "date_utc": "2025-10-03T13:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2025-10-04T17:30:00+08:00",
                    "date_utc": "2025-10-04T09:30:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2025-10-04T21:00:00+08:00",
                    "date_utc": "2025-10-04T13:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2025-10-05T20:00:00+08:00",
                    "date_utc": "2025-10-05T12:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2025-10-19",
            "race": "United States Grand Prix",
            "sessions": [
                {
                    "date": "2025-10-17T12:30:00-05:00",
                    "date_utc": "2025-10-17T17:30:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2025-10-17T16:30:00-05:00",
                    "date_utc": "2025-10-17T21:30:00",
                    "name": "Sprint Qualifying"
                },
                {
                    "date": "2025-10-18T12:00:00-05:00",
                    "date_utc": "2025-10-18T17:00:00",
                    "name": "Sprint"
                },
                {
                    "date": "2025-10-18T16:00:00-05:00",
                    "date_utc": "2025-10-18T21:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2025-10-19T14:00:00-05:00",
                    "date_utc": "2025-10-19T19:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2025-10-26",
            "race": "Mexico City Grand Prix",
            "sessions": [
                {
                    "date": "2025-10-24T12:30:00-06:00",
                    "date_utc": "2025-10-24T18:30:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2025-10-24T16:00:00-06:00",
                    "date_utc": "2025-10-24T22:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2025-10-25T11:30:00-06:00",
                    "date_utc": "2025-10-25T17:30:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2025-10-25T15:00:00-06:00",
                    "date_utc": "2025-10-25T21:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2025-10-26T14:00:00-06:00",
                    "date_utc": "2025-10-26T20:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2025-11-09",
            "race": "S\u00e3o Paulo Grand Prix",
            "sessions": [
                {
                    "date": "2025-11-07T11:30:00-03:00",
                    "date_utc": "2025-11-07T14:30:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2025-11-07T15:30:00-03:00",
                    "date_utc": "2025-11-07T18:30:00",
                    "name": "Sprint Qualifying"
                },
                {
                    "date": "2025-11-08T11:00:00-03:00",
                    "date_utc": "2025-11-08T14:00:00",
                    "name": "Sprint"
                },
                {
                    "date": "2025-11-08T15:00:00-03:00",
                    "date_utc": "2025-11-08T18:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2025-11-09T14:00:00-03:00",
                    "date_utc": "2025-11-09T17:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2025-11-22",
            "race": "Las Vegas Grand Prix",
            "sessions": [
                {
                    "date": "2025-11-20T16:30:00-08:00",
                    "date_utc": "2025-11-21T00:30:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2025-11-20T20:00:00-08:00",
                    "date_utc": "2025-11-21T04:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2025-11-21T16:30:00-08:00",
                    "date_utc": "2025-11-22T00:30:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2025-11-21T20:00:00-08:00",
                    "date_utc": "2025-11-22T04:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2025-11-22T20:00:00-08:00",
                    "date_utc": "2025-11-23T04:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2025-11-30",
            "race": "Qatar Grand Prix",
            "sessions": [
                {
                    "date": "2025-11-28T16:30:00+03:00",
                    "date_utc": "2025-11-28T13:30:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2025-11-28T20:30:00+03:00",
                    "date_utc": "2025-11-28T17:30:00",
                    "name": "Sprint Qualifying"
                },
                {
                    "date": "2025-11-29T17:00:00+03:00",
                    "date_utc": "2025-11-29T14:00:00",
                    "name": "Sprint"
                },
                {
                    "date": "2025-11-29T21:00:00+03:00",
                    "date_utc": "2025-11-29T18:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2025-11-30T19:00:00+03:00",
                    "date_utc": "2025-11-30T16:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2025-12-07",
            "race": "Abu Dhabi Grand Prix",
            "sessions": [
                {
                    "date": "2025-12-05T13:30:00+04:00",
                    "date_utc": "2025-12-05T09:30:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2025-12-05T17:00:00+04:00",
                    "date_utc": "2025-12-05T13:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2025-12-06T14:30:00+04:00",
                    "date_utc": "2025-12-06T10:30:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2025-12-06T18:00:00+04:00",
                    "date_utc": "2025-12-06T14:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2025-12-07T17:00:00+04:00",
                    "date_utc": "2025-12-07T13:00:00",
                    "name": "Race"
                }
            ]
        }
    ],
    "2026": [
        {
            "event_date": "2026-03-08",
            "race": "Australian Grand Prix",
            "sessions": [
                {
                    "date": "2026-03-06T12:30:00+11:00",
                    "date_utc": "2026-03-06T01:30:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2026-03-06T16:00:00+11:00",
                    "date_utc": "2026-03-06T05:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2026-03-07T12:30:00+11:00",
                    "date_utc": "2026-03-07T01:30:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2026-03-07T16:00:00+11:00",
                    "date_utc": "2026-03-07T05:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2026-03-08T15:00:00+11:00",
                    "date_utc": "2026-03-08T04:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2026-03-15",
            "race": "Chinese Grand Prix",
            "sessions": [
                {
                    "date": "2026-03-13T11:30:00+08:00",
                    "date_utc": "2026-03-13T03:30:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2026-03-13T15:30:00+08:00",
                    "date_utc": "2026-03-13T07:30:00",
                    "name": "Sprint Qualifying"
                },
                {
                    "date": "2026-03-14T11:00:00+08:00",
                    "date_utc": "2026-03-14T03:00:00",
                    "name": "Sprint"
                },
                {
                    "date": "2026-03-14T15:00:00+08:00",
                    "date_utc": "2026-03-14T07:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2026-03-15T15:00:00+08:00",
                    "date_utc": "2026-03-15T07:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2026-03-29",
            "race": "Japanese Grand Prix",
            "sessions": [
                {
                    "date": "2026-03-27T11:30:00+09:00",
                    "date_utc": "2026-03-27T02:30:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2026-03-27T15:00:00+09:00",
                    "date_utc": "2026-03-27T06:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2026-03-28T11:30:00+09:00",
                    "date_utc": "2026-03-28T02:30:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2026-03-28T15:00:00+09:00",
                    "date_utc": "2026-03-28T06:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2026-03-29T14:00:00+09:00",
                    "date_utc": "2026-03-29T05:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2026-05-03",
            "race": "Miami Grand Prix",
            "sessions": [
                {
                    "date": "2026-05-01T12:00:00-04:00",
                    "date_utc": "2026-05-01T16:00:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2026-05-01T16:30:00-04:00",
                    "date_utc": "2026-05-01T20:30:00",
                    "name": "Sprint Qualifying"
                },
                {
                    "date": "2026-05-02T12:00:00-04:00",
                    "date_utc": "2026-05-02T16:00:00",
                    "name": "Sprint"
                },
                {
                    "date": "2026-05-02T16:00:00-04:00",
                    "date_utc": "2026-05-02T20:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2026-05-03T13:00:00-04:00",
                    "date_utc": "2026-05-03T17:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2026-05-24",
            "race": "Canadian Grand Prix",
            "sessions": [
                {
                    "date": "2026-05-22T12:30:00-04:00",
                    "date_utc": "2026-05-22T16:30:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2026-05-22T16:30:00-04:00",
                    "date_utc": "2026-05-22T20:30:00",
                    "name": "Sprint Qualifying"
                },
                {
                    "date": "2026-05-23T12:00:00-04:00",
                    "date_utc": "2026-05-23T16:00:00",
                    "name": "Sprint"
                },
                {
                    "date": "2026-05-23T16:00:00-04:00",
                    "date_utc": "2026-05-23T20:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2026-05-24T16:00:00-04:00",
                    "date_utc": "2026-05-24T20:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2026-06-07",
            "race": "Monaco Grand Prix",
            "sessions": [
                {
                    "date": "2026-06-05T13:30:00+02:00",
                    "date_utc": "2026-06-05T11:30:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2026-06-05T17:00:00+02:00",
                    "date_utc": "2026-06-05T15:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2026-06-06T12:30:00+02:00",
                    "date_utc": "2026-06-06T10:30:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2026-06-06T16:00:00+02:00",
                    "date_utc": "2026-06-06T14:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2026-06-07T15:00:00+02:00",
                    "date_utc": "2026-06-07T13:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2026-06-14",
            "race": "Barcelona Grand Prix",
            "sessions": [
                {
                    "date": "2026-06-12T13:30:00+02:00",
                    "date_utc": "2026-06-12T11:30:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2026-06-12T17:00:00+02:00",
                    "date_utc": "2026-06-12T15:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2026-06-13T12:30:00+02:00",
                    "date_utc": "2026-06-13T10:30:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2026-06-13T16:00:00+02:00",
                    "date_utc": "2026-06-13T14:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2026-06-14T15:00:00+02:00",
                    "date_utc": "2026-06-14T13:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2026-06-28",
            "race": "Austrian Grand Prix",
            "sessions": [
                {
                    "date": "2026-06-26T13:30:00+02:00",
                    "date_utc": "2026-06-26T11:30:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2026-06-26T17:00:00+02:00",
                    "date_utc": "2026-06-26T15:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2026-06-27T12:30:00+02:00",
                    "date_utc": "2026-06-27T10:30:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2026-06-27T16:00:00+02:00",
                    "date_utc": "2026-06-27T14:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2026-06-28T15:00:00+02:00",
                    "date_utc": "2026-06-28T13:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2026-07-05",
            "race": "British Grand Prix",
            "sessions": [
                {
                    "date": "2026-07-03T12:30:00+01:00",
                    "date_utc": "2026-07-03T11:30:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2026-07-03T16:30:00+01:00",
                    "date_utc": "2026-07-03T15:30:00",
                    "name": "Sprint Qualifying"
                },
                {
                    "date": "2026-07-04T12:00:00+01:00",
                    "date_utc": "2026-07-04T11:00:00",
                    "name": "Sprint"
                },
                {
                    "date": "2026-07-04T16:00:00+01:00",
                    "date_utc": "2026-07-04T15:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2026-07-05T15:00:00+01:00",
                    "date_utc": "2026-07-05T14:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2026-07-19",
            "race": "Belgian Grand Prix",
            "sessions": [
                {
                    "date": "2026-07-17T13:30:00+02:00",
                    "date_utc": "2026-07-17T11:30:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2026-07-17T17:00:00+02:00",
                    "date_utc": "2026-07-17T15:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2026-07-18T12:30:00+02:00",
                    "date_utc": "2026-07-18T10:30:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2026-07-18T16:00:00+02:00",
                    "date_utc": "2026-07-18T14:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2026-07-19T15:00:00+02:00",
                    "date_utc": "2026-07-19T13:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2026-07-26",
            "race": "Hungarian Grand Prix",
            "sessions": [
                {
                    "date": "2026-07-24T13:30:00+02:00",
                    "date_utc": "2026-07-24T11:30:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2026-07-24T17:00:00+02:00",
                    "date_utc": "2026-07-24T15:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2026-07-25T12:30:00+02:00",
                    "date_utc": "2026-07-25T10:30:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2026-07-25T16:00:00+02:00",
                    "date_utc": "2026-07-25T14:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2026-07-26T15:00:00+02:00",
                    "date_utc": "2026-07-26T13:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2026-08-23",
            "race": "Dutch Grand Prix",
            "sessions": [
                {
                    "date": "2026-08-21T12:30:00+02:00",
                    "date_utc": "2026-08-21T10:30:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2026-08-21T16:30:00+02:00",
                    "date_utc": "2026-08-21T14:30:00",
                    "name": "Sprint Qualifying"
                },
                {
                    "date": "2026-08-22T12:00:00+02:00",
                    "date_utc": "2026-08-22T10:00:00",
                    "name": "Sprint"
                },
                {
                    "date": "2026-08-22T16:00:00+02:00",
                    "date_utc": "2026-08-22T14:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2026-08-23T15:00:00+02:00",
                    "date_utc": "2026-08-23T13:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2026-09-06",
            "race": "Italian Grand Prix",
            "sessions": [
                {
                    "date": "2026-09-04T12:30:00+02:00",
                    "date_utc": "2026-09-04T10:30:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2026-09-04T16:00:00+02:00",
                    "date_utc": "2026-09-04T14:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2026-09-05T12:30:00+02:00",
                    "date_utc": "2026-09-05T10:30:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2026-09-05T16:00:00+02:00",
                    "date_utc": "2026-09-05T14:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2026-09-06T15:00:00+02:00",
                    "date_utc": "2026-09-06T13:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2026-09-13",
            "race": "Spanish Grand Prix",
            "sessions": [
                {
                    "date": "2026-09-11T13:30:00+02:00",
                    "date_utc": "2026-09-11T11:30:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2026-09-11T17:00:00+02:00",
                    "date_utc": "2026-09-11T15:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2026-09-12T12:30:00+02:00",
                    "date_utc": "2026-09-12T10:30:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2026-09-12T16:00:00+02:00",
                    "date_utc": "2026-09-12T14:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2026-09-13T15:00:00+02:00",
                    "date_utc": "2026-09-13T13:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2026-09-26",
            "race": "Azerbaijan Grand Prix",
            "sessions": [
                {
                    "date": "2026-09-24T12:30:00+04:00",
                    "date_utc": "2026-09-24T08:30:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2026-09-24T16:00:00+04:00",
                    "date_utc": "2026-09-24T12:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2026-09-25T12:30:00+04:00",
                    "date_utc": "2026-09-25T08:30:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2026-09-25T16:00:00+04:00",
                    "date_utc": "2026-09-25T12:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2026-09-26T15:00:00+04:00",
                    "date_utc": "2026-09-26T11:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2026-10-11",
            "race": "Singapore Grand Prix",
            "sessions": [
                {
                    "date": "2026-10-09T16:30:00+08:00",
                    "date_utc": "2026-10-09T08:30:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2026-10-09T20:30:00+08:00",
                    "date_utc": "2026-10-09T12:30:00",
                    "name": "Sprint Qualifying"
                },
                {
                    "date": "2026-10-10T17:00:00+08:00",
                    "date_utc": "2026-10-10T09:00:00",
                    "name": "Sprint"
                },
                {
                    "date": "2026-10-10T21:00:00+08:00",
                    "date_utc": "2026-10-10T13:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2026-10-11T20:00:00+08:00",
                    "date_utc": "2026-10-11T12:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2026-10-25",
            "race": "United States Grand Prix",
            "sessions": [
                {
                    "date": "2026-10-23T12:30:00-05:00",
                    "date_utc": "2026-10-23T17:30:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2026-10-23T16:00:00-05:00",
                    "date_utc": "2026-10-23T21:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2026-10-24T12:30:00-05:00",
                    "date_utc": "2026-10-24T17:30:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2026-10-24T16:00:00-05:00",
                    "date_utc": "2026-10-24T21:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2026-10-25T15:00:00-05:00",
                    "date_utc": "2026-10-25T20:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2026-11-01",
            "race": "Mexico City Grand Prix",
            "sessions": [
                {
                    "date": "2026-10-30T12:30:00-06:00",
                    "date_utc": "2026-10-30T18:30:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2026-10-30T16:00:00-06:00",
                    "date_utc": "2026-10-30T22:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2026-10-31T11:30:00-06:00",
                    "date_utc": "2026-10-31T17:30:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2026-10-31T15:00:00-06:00",
                    "date_utc": "2026-10-31T21:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2026-11-01T14:00:00-06:00",
                    "date_utc": "2026-11-01T20:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2026-11-08",
            "race": "S\u00e3o Paulo Grand Prix",
            "sessions": [
                {
                    "date": "2026-11-06T12:30:00-03:00",
                    "date_utc": "2026-11-06T15:30:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2026-11-06T16:00:00-03:00",
                    "date_utc": "2026-11-06T19:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2026-11-07T11:30:00-03:00",
                    "date_utc": "2026-11-07T14:30:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2026-11-07T15:00:00-03:00",
                    "date_utc": "2026-11-07T18:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2026-11-08T14:00:00-03:00",
                    "date_utc": "2026-11-08T17:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2026-11-21",
            "race": "Las Vegas Grand Prix",
            "sessions": [
                {
                    "date": "2026-11-19T16:30:00-08:00",
                    "date_utc": "2026-11-20T00:30:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2026-11-19T20:00:00-08:00",
                    "date_utc": "2026-11-20T04:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2026-11-20T16:30:00-08:00",
                    "date_utc": "2026-11-21T00:30:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2026-11-20T20:00:00-08:00",
                    "date_utc": "2026-11-21T04:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2026-11-21T20:00:00-08:00",
                    "date_utc": "2026-11-22T04:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2026-11-29",
            "race": "Qatar Grand Prix",
            "sessions": [
                {
                    "date": "2026-11-27T16:30:00+03:00",
                    "date_utc": "2026-11-27T13:30:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2026-11-27T20:00:00+03:00",
                    "date_utc": "2026-11-27T17:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2026-11-28T17:30:00+03:00",
                    "date_utc": "2026-11-28T14:30:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2026-11-28T21:00:00+03:00",
                    "date_utc": "2026-11-28T18:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2026-11-29T19:00:00+03:00",
                    "date_utc": "2026-11-29T16:00:00",
                    "name": "Race"
                }
            ]
        },
        {
            "event_date": "2026-12-06",
            "race": "Abu Dhabi Grand Prix",
            "sessions": [
                {
                    "date": "2026-12-04T13:30:00+04:00",
                    "date_utc": "2026-12-04T09:30:00",
                    "name": "Practice 1"
                },
                {
                    "date": "2026-12-04T17:00:00+04:00",
                    "date_utc": "2026-12-04T13:00:00",
                    "name": "Practice 2"
                },
                {
                    "date": "2026-12-05T14:30:00+04:00",
                    "date_utc": "2026-12-05T10:30:00",
                    "name": "Practice 3"
                },
                {
                    "date": "2026-12-05T18:00:00+04:00",
                    "date_utc": "2026-12-05T14:00:00",
                    "name": "Qualifying"
                },
                {
                    "date": "2026-12-06T17:00:00+04:00",
                    "date_utc": "2026-12-06T13:00:00",
                    "name": "Race"
                }
            ]
        }
    ]
}
