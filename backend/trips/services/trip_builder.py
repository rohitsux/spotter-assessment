"""
trip_builder — orchestrates one trip plan from form input to persisted rows.

Flow (POST /api/trips/):

    1. Geocode pickup + dropoff via ORS
    2. Route them via ORS driving-hgv (gets miles, hours, polyline GeoJSON)
    3. Run the HOS scheduler (Decision 8 greedy loop)
    4. Project schedule events to:
         - Stops (one per non-DRIVE event; lat/lng interpolated along polyline)
         - LogDays (one per calendar date the trip covers)
         - LogEntries (one per duty-status segment within a LogDay)
    5. Write everything under transaction.atomic() and return the Trip row

The projection rules (Decision 8 + resolved Q2):
    - REST_10 splits into 1.0 hr OFF_DUTY + 9.0 hr SLEEPER
    - DRIVE events emit no Stop but DO emit LogEntries
    - Any event spanning midnight is split into two LogEntries on adjacent dates
    - Daily totals sum to exactly 24.0 hrs per LogDay (asserted)

Admin block (driver_name, tractor_number, ...) hardcoded per resolved Q2.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from math import sqrt
from typing import Iterable

from django.db import transaction

from ..hos_constants import (
    DUTY_DRIVING,
    DUTY_OFF_DUTY,
    DUTY_ON_DUTY,
    DUTY_SLEEPER,
    REST_OFF_DUTY_PREFIX_HOURS,
    REST_SLEEPER_HOURS,
)
from ..hos_scheduler import EventType, ScheduleEvent, schedule
from ..models import LogDay, LogEntry, Stop, Trip
from ..ors_client import GeocodeResult, RouteResult, geocode, route_hgv


# --- hardcoded admin block per resolved-question 2 --------------------------

DEMO_DRIVER_NAME = "Rohit Suthar"
DEMO_TRACTOR_NUMBER = "4421"
DEMO_TRAILER_NUMBER = "8812"
DEMO_SHIPPER = "Don's Paper Co."
DEMO_COMMODITY = "Paper products"


# --- pure data shapes -------------------------------------------------------


@dataclass(frozen=True)
class StopRow:
    """Pre-DB shape for a Stop. Pure value object; trip FK added at write time."""
    type: str
    city: str
    state: str
    lat: float
    lng: float
    mile_marker: float
    arrive_at: datetime
    depart_at: datetime
    duration_minutes: int
    remark: str


@dataclass(frozen=True)
class LogEntryRow:
    """Pre-DB shape for a LogEntry. log_day FK added at write time."""
    date: date
    start_time_minutes: int
    end_time_minutes: int
    duty_status: int
    city: str
    state: str
    remark: str
    is_stationary: bool


# Maps schedule EventType → (Stop.type code, remark text)
STOP_TYPE_FOR_EVENT = {
    EventType.PICKUP:   "PICKUP",
    EventType.DROPOFF:  "DROPOFF",
    EventType.FUEL:     "FUEL",
    EventType.REST_10:  "REST_10",
    EventType.BREAK_30: "BREAK_30",
}

REMARK_FOR_EVENT = {
    EventType.PICKUP:   "Pickup",
    EventType.DROPOFF:  "Dropoff",
    EventType.FUEL:     "Fuel",
    EventType.REST_10:  "10-hour rest",
    EventType.BREAK_30: "30-minute break",
}


# --- polyline interpolation -------------------------------------------------


def _polyline_cumulative_miles(coords: list[list[float]]) -> list[float]:
    """For each polyline point, the cumulative miles from coords[0]. Uses a
    flat-earth approximation — fine for marker placement, not for routing.

    1 degree of latitude ≈ 69.0 mi everywhere.
    1 degree of longitude ≈ 69.0 * cos(lat) mi.
    """
    out = [0.0]
    total = 0.0
    for (lng1, lat1), (lng2, lat2) in zip(coords, coords[1:]):
        mean_lat = (lat1 + lat2) / 2.0
        dx = (lng2 - lng1) * 69.0 * _cos_deg(mean_lat)
        dy = (lat2 - lat1) * 69.0
        total += sqrt(dx * dx + dy * dy)
        out.append(total)
    return out


def _cos_deg(deg: float) -> float:
    from math import cos, radians
    return cos(radians(deg))


def _coord_at_mile(
    coords: list[list[float]],
    cumulative_miles: list[float],
    target_mile: float,
) -> tuple[float, float]:
    """Linear-interpolate the polyline to find [lng, lat] at the given mile.
    Clamps to endpoints if target is out of range."""
    if target_mile <= 0 or len(coords) <= 1:
        lng, lat = coords[0]
        return lng, lat
    if target_mile >= cumulative_miles[-1]:
        lng, lat = coords[-1]
        return lng, lat

    # Binary-search-ish linear walk (route polylines are O(thousands), fine).
    for i in range(1, len(cumulative_miles)):
        if cumulative_miles[i] >= target_mile:
            m0, m1 = cumulative_miles[i - 1], cumulative_miles[i]
            t = 0.0 if m1 == m0 else (target_mile - m0) / (m1 - m0)
            lng0, lat0 = coords[i - 1]
            lng1, lat1 = coords[i]
            return lng0 + (lng1 - lng0) * t, lat0 + (lat1 - lat0) * t
    lng, lat = coords[-1]
    return lng, lat


# --- event → Stop / LogEntry projection (pure) ------------------------------


def project_events_to_stops(
    events: Iterable[ScheduleEvent],
    polyline: list[list[float]],
    pickup_label: str,
    dropoff_label: str,
) -> list[StopRow]:
    """Emit one StopRow per non-DRIVE event. lat/lng interpolated along the
    polyline by mile_marker. city/state are best-effort — we don't reverse-
    geocode every intermediate stop (Decision 8 tradeoff: a real product
    would consume a truck-stop API)."""
    cumulative = _polyline_cumulative_miles(polyline)
    pickup_city, pickup_state = _split_city_state(pickup_label)
    dropoff_city, dropoff_state = _split_city_state(dropoff_label)

    rows: list[StopRow] = []
    for ev in events:
        if ev.type == EventType.DRIVE:
            continue

        if ev.type == EventType.PICKUP:
            city, state = pickup_city, pickup_state
        elif ev.type == EventType.DROPOFF:
            city, state = dropoff_city, dropoff_state
        else:
            city, state = "En route", ""

        lng, lat = _coord_at_mile(polyline, cumulative, ev.odometer_end)
        rows.append(
            StopRow(
                type=STOP_TYPE_FOR_EVENT[ev.type],
                city=city,
                state=state,
                lat=lat,
                lng=lng,
                mile_marker=ev.odometer_end,
                arrive_at=ev.start_at,
                depart_at=ev.start_at + timedelta(hours=ev.duration_hrs),
                duration_minutes=int(round(ev.duration_hrs * 60)),
                remark=REMARK_FOR_EVENT[ev.type],
            )
        )
    return rows


def project_events_to_log_entries(
    events: Iterable[ScheduleEvent],
    pickup_label: str,
    dropoff_label: str,
) -> list[LogEntryRow]:
    """Emit LogEntryRow(s) per event. REST_10 splits into 1 hr OFF + 9 hr
    SLEEPER per Decision 8. Any segment crossing midnight is split into
    two rows on adjacent dates so daily totals sum to exactly 24 hrs."""
    pickup_city, pickup_state = _split_city_state(pickup_label)
    dropoff_city, dropoff_state = _split_city_state(dropoff_label)

    rows: list[LogEntryRow] = []
    for ev in events:
        if ev.type == EventType.PICKUP:
            city, state = pickup_city, pickup_state
        elif ev.type == EventType.DROPOFF:
            city, state = dropoff_city, dropoff_state
        else:
            city, state = "En route", ""

        if ev.type == EventType.REST_10:
            # 1 hr OFF_DUTY then 9 hr SLEEPER (Decision 8 + Schneider video)
            off_end = ev.start_at + timedelta(hours=REST_OFF_DUTY_PREFIX_HOURS)
            sleeper_end = off_end + timedelta(hours=REST_SLEEPER_HOURS)
            rows.extend(_split_segment(
                ev.start_at, off_end, DUTY_OFF_DUTY, city, state, "Off duty", True,
            ))
            rows.extend(_split_segment(
                off_end, sleeper_end, DUTY_SLEEPER, city, state, "Sleeper berth", True,
            ))
            continue

        duty = _duty_status_for(ev.type)
        end = ev.start_at + timedelta(hours=ev.duration_hrs)
        remark = REMARK_FOR_EVENT.get(ev.type, "")
        # DRIVE entries aren't stationary; everything else is.
        is_stationary = ev.type != EventType.DRIVE
        rows.extend(_split_segment(ev.start_at, end, duty, city, state, remark, is_stationary))
    return rows


def _duty_status_for(event_type: EventType) -> int:
    return {
        EventType.PICKUP:   DUTY_ON_DUTY,
        EventType.DRIVE:    DUTY_DRIVING,
        EventType.BREAK_30: DUTY_OFF_DUTY,
        EventType.FUEL:     DUTY_ON_DUTY,
        EventType.DROPOFF:  DUTY_ON_DUTY,
    }[event_type]


def _split_segment(
    start: datetime,
    end: datetime,
    duty: int,
    city: str,
    state: str,
    remark: str,
    is_stationary: bool,
) -> list[LogEntryRow]:
    """Split a [start, end] interval at every midnight boundary. Returns one
    LogEntryRow per calendar day touched. All times are UTC for now."""
    rows: list[LogEntryRow] = []
    cursor = start
    while cursor < end:
        next_midnight = (cursor + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        seg_end = min(end, next_midnight)
        rows.append(LogEntryRow(
            date=cursor.date(),
            start_time_minutes=_minutes_since_midnight(cursor),
            end_time_minutes=_minutes_since_midnight(seg_end) if seg_end != next_midnight else 1440,
            duty_status=duty,
            city=city,
            state=state,
            remark=remark,
            is_stationary=is_stationary,
        ))
        cursor = seg_end
    return rows


def _minutes_since_midnight(dt: datetime) -> int:
    return dt.hour * 60 + dt.minute + (1 if dt.second >= 30 else 0)


def _split_city_state(label: str) -> tuple[str, str]:
    """Naive split: 'Houston, TX, USA' → ('Houston', 'TX'). Used only for
    pickup/dropoff display in the log header — Stop rows for fuel/rest
    show 'En route' and rely on lat/lng for the map."""
    parts = [p.strip() for p in label.split(",")]
    if len(parts) >= 2 and len(parts[1]) == 2:
        return parts[0], parts[1].upper()
    if len(parts) >= 2:
        # "Texas" → "TX" lookup; minimal mapping, fall back to first 2 chars.
        return parts[0], _state_to_abbrev(parts[1])
    return label, ""


_STATE_ABBREV = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
    "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
    "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID",
    "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS",
    "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS",
    "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV",
    "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM", "new york": "NY",
    "north carolina": "NC", "north dakota": "ND", "ohio": "OH", "oklahoma": "OK",
    "oregon": "OR", "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC",
    "south dakota": "SD", "tennessee": "TN", "texas": "TX", "utah": "UT",
    "vermont": "VT", "virginia": "VA", "washington": "WA", "west virginia": "WV",
    "wisconsin": "WI", "wyoming": "WY",
}


def _state_to_abbrev(name: str) -> str:
    return _STATE_ABBREV.get(name.strip().lower(), name[:2].upper())


# --- LogDay totals ----------------------------------------------------------


def aggregate_log_days(
    entries: list[LogEntryRow],
    miles_by_date: dict[date, float],
) -> list[dict]:
    """Group entries by date and compute per-status totals + on-clock total.
    Returns a list of dicts ready for LogDay.objects.create(**day_kwargs).
    Asserts the 24-hr invariant per day.

    The scheduler only emits working events; the time before the first event
    and after the last event on each day is implicit OFF_DUTY. We pad here
    so the row totals sum to 24 hrs (the FMCSA paper-log invariant)."""
    by_date: dict[date, list[LogEntryRow]] = {}
    for row in entries:
        by_date.setdefault(row.date, []).append(row)

    log_days: list[dict] = []
    for d in sorted(by_date):
        day_entries = sorted(by_date[d], key=lambda r: r.start_time_minutes)

        # Pad implicit OFF_DUTY at start of day if first event isn't at 00:00
        first = day_entries[0]
        if first.start_time_minutes > 0:
            day_entries.insert(0, LogEntryRow(
                date=d,
                start_time_minutes=0,
                end_time_minutes=first.start_time_minutes,
                duty_status=DUTY_OFF_DUTY,
                city=first.city, state=first.state,
                remark="Off duty",
                is_stationary=True,
            ))
        # Pad implicit OFF_DUTY at end of day if last event doesn't reach 24:00
        last = day_entries[-1]
        if last.end_time_minutes < 1440:
            day_entries.append(LogEntryRow(
                date=d,
                start_time_minutes=last.end_time_minutes,
                end_time_minutes=1440,
                duty_status=DUTY_OFF_DUTY,
                city=last.city, state=last.state,
                remark="Off duty",
                is_stationary=True,
            ))

        off = sum(_minutes(r) for r in day_entries if r.duty_status == DUTY_OFF_DUTY)
        sleeper = sum(_minutes(r) for r in day_entries if r.duty_status == DUTY_SLEEPER)
        driving = sum(_minutes(r) for r in day_entries if r.duty_status == DUTY_DRIVING)
        on_duty = sum(_minutes(r) for r in day_entries if r.duty_status == DUTY_ON_DUTY)
        total_minutes = off + sleeper + driving + on_duty

        # The 24-hr invariant. Allow 1-min tolerance for rounding from
        # the schedule's float→int minute conversion.
        if abs(total_minutes - 1440) > 1:
            raise AssertionError(
                f"LogDay {d} totals {total_minutes} min, expected 1440 "
                f"(off={off}, sleeper={sleeper}, driving={driving}, on_duty={on_duty})"
            )

        log_days.append({
            "date": d,
            "driver_name": DEMO_DRIVER_NAME,
            "tractor_number": DEMO_TRACTOR_NUMBER,
            "trailer_number": DEMO_TRAILER_NUMBER,
            "shipper": DEMO_SHIPPER,
            "commodity": DEMO_COMMODITY,
            "total_off_duty_hrs": _dec(off / 60.0),
            "total_sleeper_hrs": _dec(sleeper / 60.0),
            "total_driving_hrs": _dec(driving / 60.0),
            "total_on_duty_hrs": _dec(on_duty / 60.0),
            "total_miles": _dec(miles_by_date.get(d, 0.0)),
            "total_on_clock_hrs": _dec((driving + on_duty) / 60.0),
            "_entries": day_entries,   # carried for write step, stripped before .create()
        })
    return log_days


def _minutes(r: LogEntryRow) -> int:
    return r.end_time_minutes - r.start_time_minutes


def _dec(x: float, places: int = 2) -> Decimal:
    return Decimal(f"{x:.{places}f}")


def miles_per_day(events: list[ScheduleEvent]) -> dict[date, float]:
    """Sum the miles_covered of DRIVE events per calendar date.
    Drive events are not split at midnight in the scheduler (they're a
    single contiguous segment) — for daily-mileage totals we apportion
    by elapsed time on each side of midnight."""
    out: dict[date, float] = {}
    for ev in events:
        if ev.type != EventType.DRIVE:
            continue
        start = ev.start_at
        end = start + timedelta(hours=ev.duration_hrs)
        total_seconds = (end - start).total_seconds()
        if total_seconds == 0:
            continue
        cursor = start
        while cursor < end:
            next_midnight = (cursor + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            seg_end = min(end, next_midnight)
            frac = (seg_end - cursor).total_seconds() / total_seconds
            out[cursor.date()] = out.get(cursor.date(), 0.0) + ev.miles_covered * frac
            cursor = seg_end
    return out


# --- orchestration ----------------------------------------------------------


def build_trip(
    *,
    current_location: str,
    pickup_location: str,
    dropoff_location: str,
    current_cycle_used_hrs: float,
    start_at: datetime,
    api_key: str,
) -> Trip:
    """Full pipeline. Raises ORSError on routing failure (DRF maps to 502).
    All DB writes happen in one transaction."""

    # 1. Geocode + route via ORS (Decision 1)
    pickup_geo = geocode(pickup_location, api_key=api_key)
    dropoff_geo = geocode(dropoff_location, api_key=api_key)
    route = route_hgv(pickup_geo, dropoff_geo, api_key=api_key)

    # 2. Run the HOS scheduler (Decision 8)
    result = schedule(
        start_at=start_at,
        route_miles=route.miles,
        total_drive_hours=route.hours,
        cycle_used_hrs=float(current_cycle_used_hrs),
    )

    # 3. Project events (legal-path projection skips entries on the not-legal
    #    path per resolved-question 3: summary + map only, no log sheets).
    polyline = route.coordinates
    stops = project_events_to_stops(result.events, polyline, pickup_geo.label, dropoff_geo.label)

    log_days_data: list[dict] = []
    if result.is_legal:
        entries = project_events_to_log_entries(result.events, pickup_geo.label, dropoff_geo.label)
        log_days_data = aggregate_log_days(entries, miles_per_day(result.events))

    end_at = result.events[-1].start_at + timedelta(hours=result.events[-1].duration_hrs)

    # 4. Write everything atomically (Decision 5 — SQLite, one tx)
    with transaction.atomic():
        trip = Trip.objects.create(
            current_location=current_location,
            pickup_location=pickup_location,
            dropoff_location=dropoff_location,
            current_cycle_used_hrs=_dec(current_cycle_used_hrs),
            start_at=start_at,
            end_at=end_at,
            total_miles=_dec(route.miles),
            total_drive_hours=_dec(route.hours),
            is_legal=result.is_legal,
            cycle_used_at_end=_dec(result.cycle_used_at_end),
            not_legal_reason=result.not_legal_reason or "",
            route_geometry=route.geojson,
        )
        Stop.objects.bulk_create([
            Stop(
                trip=trip,
                type=s.type,
                city=s.city,
                state=s.state,
                lat=_dec(s.lat, 6),
                lng=_dec(s.lng, 6),
                mile_marker=_dec(s.mile_marker),
                arrive_at=s.arrive_at,
                depart_at=s.depart_at,
                duration_minutes=s.duration_minutes,
                remark=s.remark,
            )
            for s in stops
        ])
        for day_kwargs in log_days_data:
            day_entries = day_kwargs.pop("_entries")
            log_day = LogDay.objects.create(trip=trip, **day_kwargs)
            LogEntry.objects.bulk_create([
                LogEntry(
                    log_day=log_day,
                    start_time_minutes=e.start_time_minutes,
                    end_time_minutes=e.end_time_minutes,
                    duty_status=e.duty_status,
                    city=e.city,
                    state=e.state,
                    remark=e.remark,
                    is_stationary=e.is_stationary,
                )
                for e in day_entries
            ])
    return trip
