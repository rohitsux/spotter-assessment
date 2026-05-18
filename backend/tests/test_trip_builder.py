"""
Tests for the trip_builder service.

Two layers:
1. Pure projection tests — feed scheduler events through the projection
   functions, assert REST_10 splits, midnight splits, daily totals, etc.
   No DB, no Django models needed.
2. Orchestration test — mocks ORS, calls build_trip, asserts the persisted
   Trip + Stops + LogDays + LogEntries are correct. Uses pytest-django's
   `django_db` marker.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from trips.hos_constants import (
    DUTY_DRIVING,
    DUTY_OFF_DUTY,
    DUTY_ON_DUTY,
    DUTY_SLEEPER,
)
from trips.hos_scheduler import EventType, ScheduleEvent, schedule
from trips.services import trip_builder
from trips.services.trip_builder import (
    LogEntryRow,
    aggregate_log_days,
    build_trip,
    miles_per_day,
    project_events_to_log_entries,
    project_events_to_stops,
)


T0 = datetime(2026, 5, 18, 6, 0, tzinfo=timezone.utc)
FIXTURE_PATH = Path(__file__).parent / "fixtures" / "ors_route_houston_chicago.geojson"


# --- pure projection: log entries ------------------------------------------


def test_rest_10_event_splits_into_off_duty_and_sleeper():
    """REST_10 must become 1 hr OFF_DUTY then 9 hr SLEEPER (Decision 8)."""
    events = [
        ScheduleEvent(EventType.PICKUP, T0, 1.0),
        ScheduleEvent(EventType.REST_10, T0 + timedelta(hours=1), 10.0),
    ]
    entries = project_events_to_log_entries(events, "Houston, TX", "Chicago, IL")

    rest_entries = [e for e in entries if e.duty_status in (DUTY_OFF_DUTY, DUTY_SLEEPER)]
    assert len(rest_entries) == 2
    off = rest_entries[0]
    sleeper = rest_entries[1]
    assert off.duty_status == DUTY_OFF_DUTY
    assert sleeper.duty_status == DUTY_SLEEPER
    # 1 hr off (60 min) + 9 hr sleeper (540 min)
    assert off.end_time_minutes - off.start_time_minutes == 60
    assert sleeper.end_time_minutes - sleeper.start_time_minutes == 540


def test_midnight_crossing_splits_into_two_dates():
    """A drive event spanning midnight emits one LogEntryRow per date."""
    start = datetime(2026, 5, 18, 22, 0, tzinfo=timezone.utc)
    events = [ScheduleEvent(EventType.DRIVE, start, 4.0, miles_covered=200, odometer_end=200)]
    entries = project_events_to_log_entries(events, "Houston, TX", "Chicago, IL")
    assert len(entries) == 2
    assert entries[0].date == start.date()
    assert entries[0].end_time_minutes == 1440        # ends at midnight
    assert entries[1].date == start.date() + timedelta(days=1)
    assert entries[1].start_time_minutes == 0          # starts at midnight


def test_drive_entries_are_not_stationary():
    events = [
        ScheduleEvent(EventType.PICKUP, T0, 1.0),
        ScheduleEvent(EventType.DRIVE, T0 + timedelta(hours=1), 2.0, miles_covered=100, odometer_end=100),
    ]
    entries = project_events_to_log_entries(events, "Houston, TX", "Chicago, IL")
    drive_entries = [e for e in entries if e.duty_status == DUTY_DRIVING]
    assert all(not e.is_stationary for e in drive_entries)


def test_break_30_entry_is_stationary_and_off_duty():
    events = [
        ScheduleEvent(EventType.BREAK_30, T0, 0.5),
    ]
    entries = project_events_to_log_entries(events, "Houston, TX", "Chicago, IL")
    assert len(entries) == 1
    assert entries[0].duty_status == DUTY_OFF_DUTY
    assert entries[0].is_stationary is True


# --- pure projection: stops ------------------------------------------------


def test_drive_events_emit_no_stops():
    events = [
        ScheduleEvent(EventType.PICKUP, T0, 1.0),
        ScheduleEvent(EventType.DRIVE, T0 + timedelta(hours=1), 5.0, miles_covered=200, odometer_end=200),
        ScheduleEvent(EventType.DROPOFF, T0 + timedelta(hours=6), 1.0),
    ]
    polyline = [[-95.0, 29.0], [-87.0, 42.0]]
    stops = project_events_to_stops(events, polyline, "Houston, TX", "Chicago, IL")
    assert len(stops) == 2  # PICKUP + DROPOFF only
    assert stops[0].type == "PICKUP"
    assert stops[1].type == "DROPOFF"


def test_pickup_stop_uses_pickup_city_state():
    events = [ScheduleEvent(EventType.PICKUP, T0, 1.0)]
    polyline = [[-95.0, 29.0], [-87.0, 42.0]]
    stops = project_events_to_stops(events, polyline, "Houston, TX", "Chicago, IL")
    assert stops[0].city == "Houston"
    assert stops[0].state == "TX"


def test_intermediate_stops_interpolate_along_polyline():
    """A fuel stop at odo=500 mi on a 1000-mi route should land between
    the polyline endpoints."""
    events = [
        ScheduleEvent(EventType.FUEL, T0, 0.25, odometer_end=500),
    ]
    # A trivial straight-line polyline: 0,0 to 10,0. Cumulative miles = 690.
    polyline = [[0.0, 0.0], [10.0, 0.0]]
    stops = project_events_to_stops(events, polyline, "A", "B")
    assert stops[0].type == "FUEL"
    # 500/690 ≈ 0.72 along the polyline → lng ≈ 7.2, lat = 0.0
    assert 0.0 < stops[0].lng < 10.0
    assert stops[0].lat == pytest.approx(0.0, abs=0.001)


# --- pure aggregation: daily totals ----------------------------------------


def test_log_day_totals_sum_to_24_hrs():
    """Every LogDay in the aggregated output must have minutes summing to 1440."""
    # Build a realistic 1-day schedule: pickup + drive + break + drive + dropoff (12 hrs work)
    # then 12 hrs off-duty rolling into next day. Simpler: use the worked example.
    result = schedule(T0, route_miles=1088, total_drive_hours=24, cycle_used_hrs=20)
    entries = project_events_to_log_entries(result.events, "Houston, TX", "Chicago, IL")
    miles = miles_per_day(result.events)
    days = aggregate_log_days(entries, miles)
    for d in days:
        total = (
            d["total_off_duty_hrs"]
            + d["total_sleeper_hrs"]
            + d["total_driving_hrs"]
            + d["total_on_duty_hrs"]
        )
        # Decimal sum with 2dp tolerance
        assert abs(float(total) - 24.0) < 0.05, f"{d['date']}: total={total}"


def test_log_day_count_matches_calendar_days_touched():
    """The Houston→Chicago worked example spans 3 calendar dates."""
    result = schedule(T0, route_miles=1088, total_drive_hours=24, cycle_used_hrs=20)
    entries = project_events_to_log_entries(result.events, "Houston, TX", "Chicago, IL")
    days = aggregate_log_days(entries, miles_per_day(result.events))
    assert len(days) == 3


def test_log_day_admin_block_is_hardcoded_demo_values():
    """Resolved Q2: hardcode the demo admin block."""
    result = schedule(T0, route_miles=200, total_drive_hours=4, cycle_used_hrs=0)
    entries = project_events_to_log_entries(result.events, "Houston, TX", "Chicago, IL")
    days = aggregate_log_days(entries, miles_per_day(result.events))
    assert days[0]["driver_name"] == "Rohit Suthar"
    assert days[0]["tractor_number"] == "4421"
    assert days[0]["trailer_number"] == "8812"
    assert days[0]["shipper"] == "Don's Paper Co."
    assert days[0]["commodity"] == "Paper products"


def test_miles_per_day_sums_to_total_route_miles():
    result = schedule(T0, route_miles=1088, total_drive_hours=24, cycle_used_hrs=20)
    per_day = miles_per_day(result.events)
    assert sum(per_day.values()) == pytest.approx(1088.0, abs=0.5)


# --- orchestration with DB writes ------------------------------------------


@pytest.fixture
def mock_ors(monkeypatch):
    """Stub ORS so build_trip never hits the network."""
    fixture = json.loads(FIXTURE_PATH.read_text()) if FIXTURE_PATH.exists() else {
        "features": [{
            "geometry": {"type": "LineString", "coordinates": [[-95.37, 29.76], [-87.65, 41.85]]},
            "properties": {"summary": {"distance": 1751033.0, "duration": 86400.0}},
        }]
    }

    from trips import ors_client

    def fake_geocode(text, api_key, **kw):
        if "Houston" in text:
            return ors_client.GeocodeResult(label="Houston, TX, USA", lng=-95.3698, lat=29.7604)
        if "Chicago" in text:
            return ors_client.GeocodeResult(label="Chicago, IL, USA", lng=-87.6298, lat=41.8781)
        return ors_client.GeocodeResult(label=text, lng=0.0, lat=0.0)

    def fake_route_hgv(src, dst, api_key, **kw):
        return ors_client.RouteResult(miles=1088.0, hours=24.0, geojson=fixture)

    monkeypatch.setattr(trip_builder, "geocode", fake_geocode)
    monkeypatch.setattr(trip_builder, "route_hgv", fake_route_hgv)


@pytest.mark.django_db
def test_build_trip_persists_trip_with_computed_fields(mock_ors):
    trip = build_trip(
        current_location="Dallas, TX",
        pickup_location="Houston, TX",
        dropoff_location="Chicago, IL",
        current_cycle_used_hrs=20.0,
        start_at=T0,
        api_key="fake",
    )
    assert trip.pk is not None
    assert trip.is_legal is True
    assert float(trip.total_miles) == pytest.approx(1088.0)
    assert float(trip.total_drive_hours) == pytest.approx(24.0)
    assert float(trip.cycle_used_at_end) == pytest.approx(46.25, abs=0.5)
    assert trip.route_geometry is not None
    assert "features" in trip.route_geometry


@pytest.mark.django_db
def test_build_trip_writes_stops_with_geometry(mock_ors):
    trip = build_trip(
        current_location="Dallas, TX",
        pickup_location="Houston, TX",
        dropoff_location="Chicago, IL",
        current_cycle_used_hrs=20.0,
        start_at=T0,
        api_key="fake",
    )
    stops = list(trip.stops.all().order_by("arrive_at"))
    types = [s.type for s in stops]
    assert types[0] == "PICKUP"
    assert types[-1] == "DROPOFF"
    assert "REST_10" in types
    assert any(s.type == "FUEL" for s in stops)
    # Lat/lng should fall inside the US bounding box (rough sanity)
    for s in stops:
        assert 24 < float(s.lat) < 50
        assert -125 < float(s.lng) < -65


@pytest.mark.django_db
def test_build_trip_writes_three_log_days_each_summing_to_24_hrs(mock_ors):
    trip = build_trip(
        current_location="Dallas, TX",
        pickup_location="Houston, TX",
        dropoff_location="Chicago, IL",
        current_cycle_used_hrs=20.0,
        start_at=T0,
        api_key="fake",
    )
    log_days = list(trip.log_days.all().order_by("date"))
    assert len(log_days) == 3
    for d in log_days:
        total = (
            float(d.total_off_duty_hrs)
            + float(d.total_sleeper_hrs)
            + float(d.total_driving_hrs)
            + float(d.total_on_duty_hrs)
        )
        assert abs(total - 24.0) < 0.05, f"{d.date}: total={total}"
    # Every day has at least one entry
    for d in log_days:
        assert d.entries.count() >= 1


@pytest.mark.django_db
def test_build_trip_skips_log_days_when_not_legal(mock_ors, monkeypatch):
    """Resolved Q3: illegal trip → summary + map only, no log sheets."""
    from trips import ors_client

    def fake_route_hgv(src, dst, api_key, **kw):
        return ors_client.RouteResult(miles=1088.0, hours=24.0, geojson={
            "features": [{
                "geometry": {"type": "LineString", "coordinates": [[-95.37, 29.76], [-87.65, 41.85]]},
                "properties": {"summary": {"distance": 1751033.0, "duration": 86400.0}},
            }]
        })
    monkeypatch.setattr(trip_builder, "route_hgv", fake_route_hgv)

    trip = build_trip(
        current_location="Dallas, TX",
        pickup_location="Houston, TX",
        dropoff_location="Chicago, IL",
        current_cycle_used_hrs=65.0,    # only 5 hrs left in cycle
        start_at=T0,
        api_key="fake",
    )
    assert trip.is_legal is False
    assert trip.not_legal_reason
    assert trip.log_days.count() == 0          # no logs on not-legal path
    assert trip.stops.count() >= 1             # at least PICKUP was emitted
