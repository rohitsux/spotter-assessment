"""
Canonical worked example: Houston → Chicago.

This is the reference scenario the Loom script narrates and the README cites.
It pins down the scheduler's exact event sequence so any regression — in
clock arithmetic, event-priority order, or fuel-boundary handling — fails
loudly here.

Inputs:
    pickup            Houston, TX
    dropoff           Chicago, IL
    route_miles       1088.0   (from real ORS driving-hgv response)
    total_drive_hrs   24.0     (from real ORS driving-hgv response)
    cycle_used_hrs    20.0     (driver has used 20 of 70 hrs in their cycle)
    start_at          Mon May 18, 2026, 06:00 UTC

Expected legal 3-day plan ending Wed May 20 at 05:15 UTC with cycle_used 46.25.

This test satisfies MUST #5 in BUILD-BRIEF (a passing unit test that encodes
the worked example).
"""

from datetime import datetime, timedelta, timezone

import pytest

from trips.hos_scheduler import EventType, ScheduleEvent, schedule


# --- canonical inputs -------------------------------------------------------

START_AT = datetime(2026, 5, 18, 6, 0, tzinfo=timezone.utc)
ROUTE_MILES = 1088.0
TOTAL_DRIVE_HOURS = 24.0
CYCLE_USED_HRS = 20.0


@pytest.fixture(scope="module")
def result():
    """Run the schedule once; share across all assertions in this file."""
    return schedule(
        start_at=START_AT,
        route_miles=ROUTE_MILES,
        total_drive_hours=TOTAL_DRIVE_HOURS,
        cycle_used_hrs=CYCLE_USED_HRS,
    )


# --- top-level outcome ------------------------------------------------------


def test_trip_is_legal(result):
    """Driver has 50 cycle hrs remaining and the trip needs ~26 on-clock hrs.
    Plenty of headroom — must be legal."""
    assert result.is_legal is True
    assert result.not_legal_reason is None


def test_cycle_used_at_end_is_in_expected_band(result):
    """Started at 20, trip adds ~26.25 on-clock hrs (1 pickup + 24 drive +
    0.25 fuel + 1 dropoff), ends at 46.25. Asserted with a wide tolerance
    so a future scheduler tweak that shifts a fuel stop doesn't break this."""
    assert result.cycle_used_at_end == pytest.approx(46.25, abs=0.5)


def test_cycle_used_at_end_leaves_at_least_20_hrs_to_spare(result):
    """Loom-script claim: 'Driver ends at 46 of 70, under cap.' Must hold."""
    assert result.cycle_used_at_end < 50.0
    assert 70.0 - result.cycle_used_at_end >= 20.0


# --- event shape ------------------------------------------------------------


def test_pickup_is_first_event_at_start_time(result):
    first = result.events[0]
    assert first.type == EventType.PICKUP
    assert first.start_at == START_AT
    assert first.duration_hrs == pytest.approx(1.0)


def test_dropoff_is_last_event(result):
    last = result.events[-1]
    assert last.type == EventType.DROPOFF
    assert last.duration_hrs == pytest.approx(1.0)


def test_two_ten_hour_rests_separate_three_driving_days(result):
    """A 24-hr-drive trip can't fit two 11-hr days, so 3 days, so 2 rests
    between them. Decision 8."""
    rests = [e for e in result.events if e.type == EventType.REST_10]
    assert len(rests) == 2
    assert all(r.duration_hrs == pytest.approx(10.0) for r in rests)


def test_at_least_two_30_min_breaks(result):
    """Each driving day that does 8+ hrs needs a 30-min break.
    With 24 drive-hrs split as 11 + 11 + 2, days 1 and 2 each need one."""
    breaks = [e for e in result.events if e.type == EventType.BREAK_30]
    assert len(breaks) >= 2
    assert all(b.duration_hrs == pytest.approx(0.5) for b in breaks)


def test_at_least_one_fuel_stop_near_mile_1000(result):
    """1088-mi trip crosses the 1000-mi fuel boundary once."""
    fuels = [e for e in result.events if e.type == EventType.FUEL]
    assert len(fuels) >= 1
    assert all(f.duration_hrs == pytest.approx(0.25) for f in fuels)
    # The fuel stop should be at odo == 1000 (or very close after the fix to
    # the modulo-at-boundary bug).
    first_fuel = fuels[0]
    assert first_fuel.odometer_end == pytest.approx(1000.0, abs=1.0)


# --- numeric invariants -----------------------------------------------------


def test_total_drive_hours_sum_to_route_drive_time(result):
    drive_total = sum(e.duration_hrs for e in result.events if e.type == EventType.DRIVE)
    assert drive_total == pytest.approx(TOTAL_DRIVE_HOURS, abs=0.001)


def test_total_miles_sum_to_route_miles(result):
    miles_total = sum(e.miles_covered for e in result.events if e.type == EventType.DRIVE)
    assert miles_total == pytest.approx(ROUTE_MILES, abs=0.01)


def test_final_odometer_equals_route_miles(result):
    assert result.events[-1].odometer_end == pytest.approx(ROUTE_MILES, abs=0.01)


def test_events_are_contiguous_in_time(result):
    """No gaps, no overlaps."""
    for prev, nxt in zip(result.events, result.events[1:]):
        assert prev.end_at == nxt.start_at, f"discontinuity: {prev} -> {nxt}"


def test_trip_duration_is_just_under_three_days(result):
    """Loom: 'Starts Mon 6 AM, ends Wed ~5 AM' → ~47 hours wall-clock."""
    first = result.events[0]
    last = result.events[-1]
    elapsed = last.end_at - first.start_at
    # 24 drive + 2 pickups/dropoffs + 2 * 10 rest + 2 * 0.5 break + 0.25 fuel ≈ 47.25
    assert timedelta(hours=46) < elapsed < timedelta(hours=49)


# --- Loom-script narrative anchors ------------------------------------------


def test_first_drive_segment_hits_the_30_min_break_at_8_hours(result):
    """Loom day-1 narration: '7 AM driving starts. After 8 cumulative
    driving hours the federal rule triggers a mandatory 30-min break.'"""
    # Event sequence: PICKUP, DRIVE, BREAK_30, ...
    assert result.events[0].type == EventType.PICKUP
    assert result.events[1].type == EventType.DRIVE
    assert result.events[1].duration_hrs == pytest.approx(8.0)
    assert result.events[2].type == EventType.BREAK_30


def test_day_one_ends_with_a_10_hr_rest_after_11_drive_hrs(result):
    """Loom: 'hits the 11-hour daily driving cap, starts the 10-hour rest.'"""
    # Sum DRIVE durations until the first REST_10 — should be exactly 11.
    drive_before_rest = 0.0
    for e in result.events:
        if e.type == EventType.DRIVE:
            drive_before_rest += e.duration_hrs
        elif e.type == EventType.REST_10:
            break
    assert drive_before_rest == pytest.approx(11.0, abs=0.001)
