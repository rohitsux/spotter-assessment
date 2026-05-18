"""
Sanity tests for the HOS scheduler greedy event loop.

The canonical Houston-Chicago worked-example test lives in
test_hos_scheduler_worked_example.py (Phase 2.4). This file covers
structural invariants and the not-legal path without committing to
specific event counts that the worked example will pin down.
"""

from datetime import datetime, timezone

import pytest

from trips.hos_scheduler import EventType, schedule


T0 = datetime(2026, 5, 18, 6, 0, tzinfo=timezone.utc)


# --- input validation -------------------------------------------------------


def test_zero_miles_raises():
    with pytest.raises(ValueError):
        schedule(T0, route_miles=0, total_drive_hours=10, cycle_used_hrs=0)


def test_zero_drive_hours_raises():
    with pytest.raises(ValueError):
        schedule(T0, route_miles=100, total_drive_hours=0, cycle_used_hrs=0)


# --- trivial trip: well within one shift ------------------------------------


def test_short_trip_pickup_drive_dropoff_only():
    """A 200-mi, 4-hr trip with a fresh driver. No breaks, rests, or fuel needed."""
    r = schedule(T0, route_miles=200, total_drive_hours=4, cycle_used_hrs=0)
    assert r.is_legal is True
    types = [e.type for e in r.events]
    assert types == [EventType.PICKUP, EventType.DRIVE, EventType.DROPOFF]
    # cycle = 1 (pickup) + 4 (drive) + 1 (dropoff) = 6
    assert r.cycle_used_at_end == pytest.approx(6.0)


# --- structural invariants on any legal trip --------------------------------


def test_legal_trip_starts_with_pickup_ends_with_dropoff():
    r = schedule(T0, route_miles=500, total_drive_hours=9, cycle_used_hrs=10)
    assert r.is_legal is True
    assert r.events[0].type == EventType.PICKUP
    assert r.events[-1].type == EventType.DROPOFF


def test_drive_hours_sum_equals_total_drive_hours():
    """Every drive event together must cover exactly the route's drive time."""
    r = schedule(T0, route_miles=500, total_drive_hours=9, cycle_used_hrs=10)
    drive_total = sum(e.duration_hrs for e in r.events if e.type == EventType.DRIVE)
    assert drive_total == pytest.approx(9.0, abs=0.001)


def test_miles_sum_equals_route_miles():
    r = schedule(T0, route_miles=500, total_drive_hours=9, cycle_used_hrs=10)
    miles_total = sum(e.miles_covered for e in r.events if e.type == EventType.DRIVE)
    assert miles_total == pytest.approx(500.0, abs=0.01)


def test_events_are_contiguous_in_time():
    """No gaps and no overlaps between consecutive events."""
    r = schedule(T0, route_miles=500, total_drive_hours=9, cycle_used_hrs=10)
    for prev, nxt in zip(r.events, r.events[1:]):
        assert prev.end_at == nxt.start_at, f"gap/overlap: {prev} -> {nxt}"


# --- mandatory event insertion ---------------------------------------------


def test_long_drive_inserts_30_min_break():
    """Any trip whose driving exceeds 8 hrs must contain a BREAK_30."""
    r = schedule(T0, route_miles=600, total_drive_hours=10, cycle_used_hrs=0)
    assert r.is_legal is True
    assert any(e.type == EventType.BREAK_30 for e in r.events)


def test_multi_day_trip_inserts_10_hr_rest():
    """A trip exceeding the 11-hr daily cap must contain a REST_10."""
    r = schedule(T0, route_miles=1000, total_drive_hours=18, cycle_used_hrs=0)
    assert r.is_legal is True
    assert any(e.type == EventType.REST_10 for e in r.events)


def test_long_trip_inserts_fuel_stop():
    """A trip over 1000 mi must contain at least one FUEL event."""
    r = schedule(T0, route_miles=1200, total_drive_hours=22, cycle_used_hrs=0)
    assert r.is_legal is True
    assert any(e.type == EventType.FUEL for e in r.events)


# --- not-legal path ---------------------------------------------------------


def test_trip_not_legal_when_cycle_exhausted():
    """65 hrs used + a 24-hr trip > 70-hr cap → not legal, no DROPOFF emitted."""
    r = schedule(T0, route_miles=1088, total_drive_hours=24, cycle_used_hrs=65)
    assert r.is_legal is False
    assert r.not_legal_reason is not None
    assert "cycle" in r.not_legal_reason.lower()
    assert EventType.DROPOFF not in [e.type for e in r.events]


def test_not_legal_trip_still_emits_some_events_before_giving_up():
    """The schedule should reflect partial progress, not be empty."""
    r = schedule(T0, route_miles=1088, total_drive_hours=24, cycle_used_hrs=65)
    assert len(r.events) >= 1
    assert r.events[0].type == EventType.PICKUP


def test_cycle_used_at_end_is_reported_in_both_paths():
    legal = schedule(T0, route_miles=200, total_drive_hours=4, cycle_used_hrs=0)
    illegal = schedule(T0, route_miles=1088, total_drive_hours=24, cycle_used_hrs=65)
    assert legal.cycle_used_at_end > 0
    assert illegal.cycle_used_at_end > 0
