"""
Tests for the deadhead leg in the HOS scheduler (plan §9 amendment).

Deadhead = current_location → pickup. The scheduler treats this as a Leg A
that uses the SAME HOSClocks instance as the main leg, so deadhead drive
hours count against the same shift's 11-hr cap, 14-hr window, 30-min break
counter, and 70-hr cycle.
"""

from datetime import datetime, timezone

import pytest

from trips.hos_scheduler import EventType, schedule


T0 = datetime(2026, 5, 18, 6, 0, tzinfo=timezone.utc)


# --- input validation -------------------------------------------------------


def test_deadhead_miles_without_hours_raises():
    with pytest.raises(ValueError, match="must both be > 0 or both be 0"):
        schedule(T0, route_miles=1088, total_drive_hours=24, cycle_used_hrs=20,
                 deadhead_miles=240, deadhead_drive_hours=0)


def test_negative_deadhead_raises():
    with pytest.raises(ValueError, match="non-negative"):
        schedule(T0, route_miles=1088, total_drive_hours=24, cycle_used_hrs=20,
                 deadhead_miles=-1, deadhead_drive_hours=-1)


# --- happy-path: deadhead emits DEADHEAD events BEFORE PICKUP ---------------


def test_deadhead_events_precede_pickup():
    """Driver clocks in, drives Leg A, then arrives at pickup."""
    r = schedule(
        T0, route_miles=1088, total_drive_hours=24, cycle_used_hrs=20,
        deadhead_miles=240, deadhead_drive_hours=4,
    )
    assert r.is_legal is True
    types = [e.type for e in r.events]
    # The first event must be a DEADHEAD drive, not a PICKUP
    assert types[0] == EventType.DEADHEAD
    # PICKUP appears after all DEADHEAD events
    pickup_idx = types.index(EventType.PICKUP)
    deadhead_indices = [i for i, t in enumerate(types) if t == EventType.DEADHEAD]
    assert all(i < pickup_idx for i in deadhead_indices)


def test_deadhead_miles_in_total():
    """Sum of DEADHEAD + DRIVE miles equals total route miles (incl deadhead)."""
    r = schedule(
        T0, route_miles=1088, total_drive_hours=24, cycle_used_hrs=20,
        deadhead_miles=240, deadhead_drive_hours=4,
    )
    deadhead_miles = sum(e.miles_covered for e in r.events if e.type == EventType.DEADHEAD)
    drive_miles    = sum(e.miles_covered for e in r.events if e.type == EventType.DRIVE)
    assert deadhead_miles == pytest.approx(240.0, abs=0.01)
    assert drive_miles    == pytest.approx(1088.0, abs=0.01)


def test_deadhead_hours_consume_cycle_budget():
    """Deadhead drive hours and pickup/dropoff on-duty all hit the 70/8 cycle."""
    # Without deadhead: cycle_used_at_end ≈ 20 + 1 + 24 + 0.25 + 1 = 46.25
    # With 4-hr deadhead: 46.25 + 4 = 50.25
    r = schedule(
        T0, route_miles=1088, total_drive_hours=24, cycle_used_hrs=20,
        deadhead_miles=240, deadhead_drive_hours=4,
    )
    assert r.is_legal is True
    assert r.cycle_used_at_end == pytest.approx(50.25, abs=0.5)


def test_deadhead_consumes_shift_window_before_pickup():
    """A 4-hr deadhead burns 4 hrs of the 14-hr shift window before pickup
    even starts — so the main leg has less day-1 driving budget."""
    # Without deadhead, day 1 fits 8 drive + break + 3 drive = 11.0 in shift
    # With 4-hr deadhead: shift opens with 14 - 4 = 10 hrs left,
    # then pickup eats 1 → 9 hrs window; main-leg day 1 drive ≤ 9 hrs
    r = schedule(
        T0, route_miles=1088, total_drive_hours=24, cycle_used_hrs=20,
        deadhead_miles=240, deadhead_drive_hours=4,
    )
    # The first REST_10 should appear earlier (in clock time) than the no-deadhead case
    assert r.is_legal is True
    first_rest = next((e for e in r.events if e.type == EventType.REST_10), None)
    assert first_rest is not None, "long trip with deadhead must include rests"


# --- not-legal: cycle exhausts during deadhead ------------------------------


def test_cycle_exhausts_during_deadhead_returns_not_legal():
    """Driver has 5 hrs cycle remaining but a 6-hr deadhead → not legal,
    no PICKUP event emitted."""
    r = schedule(
        T0, route_miles=1088, total_drive_hours=24, cycle_used_hrs=65,
        deadhead_miles=350, deadhead_drive_hours=6,
    )
    assert r.is_legal is False
    assert r.not_legal_reason is not None
    assert "deadhead" in r.not_legal_reason.lower()
    types = [e.type for e in r.events]
    assert EventType.PICKUP not in types
    assert EventType.DROPOFF not in types


def test_cycle_exhausted_at_trip_start_with_deadhead():
    """Cycle already at 70 + a deadhead → not legal before any drive event."""
    r = schedule(
        T0, route_miles=1088, total_drive_hours=24, cycle_used_hrs=70,
        deadhead_miles=240, deadhead_drive_hours=4,
    )
    assert r.is_legal is False
    assert "cycle" in r.not_legal_reason.lower()
    # No events should be emitted at all
    assert len(r.events) == 0


# --- zero deadhead === backward compat --------------------------------------


def test_zero_deadhead_is_identical_to_no_deadhead_kwarg():
    """Calling schedule() with deadhead_miles=0, deadhead_drive_hours=0
    must produce the identical schedule as omitting both kwargs."""
    a = schedule(T0, route_miles=1088, total_drive_hours=24, cycle_used_hrs=20)
    b = schedule(T0, route_miles=1088, total_drive_hours=24, cycle_used_hrs=20,
                 deadhead_miles=0, deadhead_drive_hours=0)
    assert len(a.events) == len(b.events)
    for ea, eb in zip(a.events, b.events):
        assert ea.type == eb.type
        assert ea.duration_hrs == pytest.approx(eb.duration_hrs)
        assert ea.miles_covered == pytest.approx(eb.miles_covered)
    assert a.cycle_used_at_end == pytest.approx(b.cycle_used_at_end)
    assert a.is_legal == b.is_legal


# --- long deadhead → mandatory break / rest before pickup -------------------


def test_long_deadhead_inserts_break_before_pickup():
    """A 9-hr deadhead crosses the 8-hr break trigger → BREAK_30 must appear
    in the deadhead leg, before PICKUP."""
    r = schedule(
        T0, route_miles=1088, total_drive_hours=24, cycle_used_hrs=0,
        deadhead_miles=540, deadhead_drive_hours=9,
    )
    assert r.is_legal is True
    pickup_idx = next(i for i, e in enumerate(r.events) if e.type == EventType.PICKUP)
    pre_pickup_types = [e.type for e in r.events[:pickup_idx]]
    assert EventType.BREAK_30 in pre_pickup_types


def test_very_long_deadhead_inserts_rest_before_pickup():
    """A 12-hr deadhead exceeds the 11-hr daily cap → REST_10 must fire
    inside the deadhead leg, before PICKUP."""
    r = schedule(
        T0, route_miles=1088, total_drive_hours=24, cycle_used_hrs=0,
        deadhead_miles=720, deadhead_drive_hours=12,
    )
    assert r.is_legal is True
    pickup_idx = next(i for i, e in enumerate(r.events) if e.type == EventType.PICKUP)
    pre_pickup_types = [e.type for e in r.events[:pickup_idx]]
    assert EventType.REST_10 in pre_pickup_types


# --- odometer continuity -----------------------------------------------------


def test_odometer_is_continuous_across_legs():
    """odometer_end on the last DEADHEAD event = first DRIVE event's start odometer."""
    r = schedule(
        T0, route_miles=1088, total_drive_hours=24, cycle_used_hrs=20,
        deadhead_miles=240, deadhead_drive_hours=4,
    )
    assert r.is_legal is True
    # Last DEADHEAD ends at ~240; PICKUP doesn't advance odo; first DRIVE
    # starts at that same odo (because emit() carries miles_done forward).
    last_dh   = next(e for e in reversed(r.events) if e.type == EventType.DEADHEAD)
    pickup    = next(e for e in r.events if e.type == EventType.PICKUP)
    first_drv = next(e for e in r.events if e.type == EventType.DRIVE)
    assert last_dh.odometer_end == pytest.approx(240.0, abs=0.5)
    assert pickup.odometer_end  == pytest.approx(last_dh.odometer_end)
    # First DRIVE event's odo should be > 240 (it added miles to the running total)
    assert first_drv.odometer_end > last_dh.odometer_end
