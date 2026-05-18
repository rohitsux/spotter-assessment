"""
HOS scheduler — the greedy event loop that turns a route into a legal schedule.

Inputs:
    start_at            wall-clock datetime the trip begins (driver clocks in at pickup)
    route_miles         total miles from ORS (driving-hgv)
    total_drive_hours   total driving time from ORS (used to derive avg_mph)
    cycle_used_hrs      driver's pre-trip 70/8 cycle position

Output:
    ScheduleResult(events, is_legal, not_legal_reason, cycle_used_at_end)
      events            ordered list[ScheduleEvent], starts with PICKUP, ends with DROPOFF
                        if legal; truncates before DROPOFF if cycle exhausts
      is_legal          bool — True iff DROPOFF was reached
      not_legal_reason  str | None — human-readable if is_legal=False

The loop is greedy per Decision 8: at every step, ask which of the 4 clocks
(or the fuel-mile clock) hits its limit first; insert the required reset event
if any limit is at zero, otherwise drive forward until the next limit. This is
provably optimal in the single-driver HOS problem space.

Pure Python. No Django, no I/O, no global state.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum

from .hos_clocks import HOSClocks
from .hos_constants import (
    BREAK_DURATION_HOURS,
    DROPOFF_DURATION_HOURS,
    DUTY_DRIVING,
    DUTY_OFF_DUTY,
    DUTY_ON_DUTY,
    DUTY_SLEEPER,
    FUEL_DURATION_HOURS,
    FUEL_INTERVAL_MILES,
    PICKUP_DURATION_HOURS,
    REST_OFF_DUTY_PREFIX_HOURS,
    REST_RESET_HOURS,
    REST_SLEEPER_HOURS,
)


class EventType(str, Enum):
    PICKUP = "PICKUP"
    DRIVE = "DRIVE"
    BREAK_30 = "BREAK_30"
    REST_10 = "REST_10"
    FUEL = "FUEL"
    DROPOFF = "DROPOFF"


# Maps the *event* to the duty-status row that owns most of its time.
# REST_10 is special: it spans BOTH off-duty and sleeper (1 hr + 9 hr per Decision 8).
# The LogEntry projection in trip_builder splits REST_10 into two entries.
DUTY_STATUS_FOR_EVENT = {
    EventType.PICKUP:   DUTY_ON_DUTY,
    EventType.DRIVE:    DUTY_DRIVING,
    EventType.BREAK_30: DUTY_OFF_DUTY,
    EventType.REST_10:  DUTY_SLEEPER,        # see split note above
    EventType.FUEL:     DUTY_ON_DUTY,
    EventType.DROPOFF:  DUTY_ON_DUTY,
}


@dataclass
class ScheduleEvent:
    type: EventType
    start_at: datetime
    duration_hrs: float
    miles_covered: float = 0.0          # 0 for non-driving events
    odometer_end: float = 0.0           # cumulative miles since trip start

    @property
    def end_at(self) -> datetime:
        return self.start_at + timedelta(hours=self.duration_hrs)


@dataclass
class ScheduleResult:
    events: list[ScheduleEvent] = field(default_factory=list)
    is_legal: bool = False
    not_legal_reason: str | None = None
    cycle_used_at_end: float = 0.0


# Tolerance for "this clock is at zero." Comparing floats with == is unsafe;
# in the loop, a value <= EPSILON counts as triggered.
EPSILON = 1e-6


def schedule(
    start_at: datetime,
    route_miles: float,
    total_drive_hours: float,
    cycle_used_hrs: float,
) -> ScheduleResult:
    """Greedy event loop. See module docstring."""

    if route_miles <= 0 or total_drive_hours <= 0:
        raise ValueError(
            f"route_miles ({route_miles}) and total_drive_hours "
            f"({total_drive_hours}) must both be > 0"
        )

    avg_mph = route_miles / total_drive_hours       # per-trip, not a constant — Decision 8
    clocks = HOSClocks(cycle_used=cycle_used_hrs)
    result = ScheduleResult()
    cursor = start_at
    drive_left = total_drive_hours
    miles_done = 0.0
    miles_since_fuel = 0.0          # resets on a FUEL event

    # --- helpers ------------------------------------------------------------

    def emit(event_type: EventType, duration_hrs: float, miles_covered: float = 0.0) -> None:
        nonlocal cursor, miles_done, miles_since_fuel
        miles_done += miles_covered
        miles_since_fuel += miles_covered
        result.events.append(
            ScheduleEvent(
                type=event_type,
                start_at=cursor,
                duration_hrs=duration_hrs,
                miles_covered=miles_covered,
                odometer_end=miles_done,
            )
        )
        cursor = cursor + timedelta(hours=duration_hrs)

    def hrs_until_next_fuel() -> float:
        """How many drive-hours remain before the next fuel stop is due.
        A FUEL event resets the counter, so this is exact: 0.0 means fuel now."""
        return max(0.0, (FUEL_INTERVAL_MILES - miles_since_fuel) / avg_mph)

    # --- start the trip at the pickup location ------------------------------

    emit(EventType.PICKUP, PICKUP_DURATION_HOURS)
    clocks.on_duty(PICKUP_DURATION_HOURS)

    # --- main loop ----------------------------------------------------------

    while drive_left > EPSILON:
        # Cycle exhaustion is the not-legal condition (Decision 3:
        # no silent 34-hr restart; report trip-not-legal instead).
        # Check BEFORE inserting any further on-duty time.
        if clocks.cycle_remaining() <= EPSILON:
            result.not_legal_reason = (
                f"driver has {clocks.cycle_remaining():.1f} hrs cycle remaining; "
                f"trip needs {drive_left:.1f} more drive hrs plus on-duty time"
            )
            result.is_legal = False
            result.cycle_used_at_end = clocks.cycle_used
            return result

        # How long can we drive before SOMETHING forces us to stop?
        budgets = {
            "break":     clocks.hrs_until_break_required(),   # → BREAK_30
            "drive_cap": clocks.hrs_until_driving_cap(),      # → REST_10
            "shift_end": clocks.hrs_until_shift_end(),        # → REST_10
            "fuel":      hrs_until_next_fuel(),               # → FUEL
            "drive_left": drive_left,                          # → DROPOFF
            "cycle":     clocks.cycle_remaining(),            # → not-legal sentinel
        }
        # Don't let the shift-end budget force a rest mid-break. break_30() already
        # bumps on_duty_in_shift by 0.5, so this is naturally bounded.
        next_limit = min(budgets.values())

        if next_limit > EPSILON:
            # Drive forward up to the next limit.
            hrs = next_limit
            miles = hrs * avg_mph
            emit(EventType.DRIVE, hrs, miles_covered=miles)
            clocks.drive(hrs)
            drive_left -= hrs
            continue

        # next_limit is ~0 — one or more clocks have triggered. Insert the
        # appropriate reset event. Priority matters when multiple are zero
        # simultaneously (e.g. break trigger and fuel both at 0).
        # Order: rest_10 (most disruptive) > break_30 > fuel.
        # Rationale: if the driver has hit the 11-hr cap OR the 14-hr window,
        # a 30-min break alone won't help; they need a full 10-hr reset.

        if budgets["drive_cap"] <= EPSILON or budgets["shift_end"] <= EPSILON:
            emit(EventType.REST_10, REST_RESET_HOURS)
            clocks.rest_10()
        elif budgets["break"] <= EPSILON:
            emit(EventType.BREAK_30, BREAK_DURATION_HOURS)
            clocks.break_30()
        elif budgets["fuel"] <= EPSILON:
            emit(EventType.FUEL, FUEL_DURATION_HOURS)
            clocks.on_duty(FUEL_DURATION_HOURS)
            miles_since_fuel = 0.0
        else:
            # Defensive: shouldn't happen — one of the above must be zero
            # if next_limit hit EPSILON.
            raise RuntimeError(
                f"scheduler stuck: next_limit={next_limit}, budgets={budgets}"
            )

    # --- finish the trip at the dropoff location ----------------------------

    # Need cycle room for the dropoff too. If not, trip-not-legal.
    if clocks.cycle_remaining() < DROPOFF_DURATION_HOURS - EPSILON:
        result.not_legal_reason = (
            f"driver has {clocks.cycle_remaining():.1f} hrs cycle remaining; "
            f"dropoff needs {DROPOFF_DURATION_HOURS:.1f} hrs on-duty"
        )
        result.is_legal = False
        result.cycle_used_at_end = clocks.cycle_used
        return result

    # And shift room — if the 14-hr window has run out, take a 10-hr rest first.
    if clocks.hrs_until_shift_end() < DROPOFF_DURATION_HOURS - EPSILON:
        emit(EventType.REST_10, REST_RESET_HOURS)
        clocks.rest_10()

    emit(EventType.DROPOFF, DROPOFF_DURATION_HOURS)
    clocks.on_duty(DROPOFF_DURATION_HOURS)

    result.is_legal = True
    result.cycle_used_at_end = clocks.cycle_used
    return result
