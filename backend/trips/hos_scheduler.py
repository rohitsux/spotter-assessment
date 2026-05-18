"""
HOS scheduler — the greedy event loop that turns a route into a legal schedule.

Inputs:
    start_at              wall-clock datetime the trip begins (driver clocks in)
    route_miles           main-leg miles from ORS pickup→dropoff (driving-hgv)
    total_drive_hours     main-leg driving time from ORS
    cycle_used_hrs        driver's pre-trip 70/8 cycle position
    deadhead_miles        optional, miles from current_location → pickup (Leg A)
    deadhead_drive_hours  optional, driving time for Leg A

Output:
    ScheduleResult(events, is_legal, not_legal_reason, cycle_used_at_end)
      events            ordered list[ScheduleEvent]
                        if deadhead supplied: starts with DEADHEAD drive events
                        then PICKUP, then DRIVE/BREAK_30/REST_10/FUEL, then DROPOFF
      is_legal          bool — True iff DROPOFF was reached
      not_legal_reason  str | None — human-readable if is_legal=False

The loop is greedy per Decision 8: at every step, ask which of the 4 clocks
(or the fuel-mile clock) hits its limit first; insert the required reset event
if any limit is at zero, otherwise drive forward until the next limit. The
deadhead leg (when provided) is scheduled BEFORE pickup using the same clocks
instance, so it counts against the same shift's 11-hr cap and 14-hr window.
Cycle exhaustion during deadhead returns is_legal=False with a deadhead-aware
reason.

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
    DEADHEAD = "DEADHEAD"   # driving event on Leg A (current_location → pickup)
    PICKUP = "PICKUP"
    DRIVE = "DRIVE"
    BREAK_30 = "BREAK_30"
    REST_10 = "REST_10"
    FUEL = "FUEL"
    DROPOFF = "DROPOFF"


# Maps the *event* to the duty-status row that owns most of its time.
# REST_10 is special: it spans BOTH off-duty and sleeper (1 hr + 9 hr per Decision 8).
# The LogEntry projection in trip_builder splits REST_10 into two entries.
# DEADHEAD is just driving — it projects to DUTY_DRIVING; the leg distinction
# is preserved on the event's type so the UI can label its log entries as
# deadhead miles, but the duty-status row is the same as a regular DRIVE.
DUTY_STATUS_FOR_EVENT = {
    EventType.DEADHEAD: DUTY_DRIVING,
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
    odometer_end: float = 0.0           # cumulative miles since trip start (Leg A miles included)

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
    *,
    deadhead_miles: float = 0.0,
    deadhead_drive_hours: float = 0.0,
) -> ScheduleResult:
    """Greedy event loop. See module docstring."""

    if route_miles <= 0 or total_drive_hours <= 0:
        raise ValueError(
            f"route_miles ({route_miles}) and total_drive_hours "
            f"({total_drive_hours}) must both be > 0"
        )
    if (deadhead_miles > 0) != (deadhead_drive_hours > 0):
        raise ValueError(
            "deadhead_miles and deadhead_drive_hours must both be > 0 or both be 0"
        )
    if deadhead_miles < 0 or deadhead_drive_hours < 0:
        raise ValueError("deadhead inputs must be non-negative")

    # avg_mph for each leg is derived from ORS data, not a fixed constant.
    # The two legs can have different averages (e.g. deadhead through dense
    # roads vs the main interstate run).
    main_avg_mph = route_miles / total_drive_hours
    deadhead_avg_mph = (
        deadhead_miles / deadhead_drive_hours if deadhead_drive_hours > 0 else main_avg_mph
    )

    clocks = HOSClocks(cycle_used=cycle_used_hrs)
    result = ScheduleResult()

    # Loop state — `state` is mutated by the inner helpers via the `nonlocal`
    # equivalent of attribute lookup. Using a dict keeps the closure simple.
    state = {
        "cursor": start_at,
        "miles_done": 0.0,
        "miles_since_fuel": 0.0,
    }

    def emit(event_type: EventType, duration_hrs: float, miles_covered: float = 0.0) -> None:
        state["miles_done"] += miles_covered
        state["miles_since_fuel"] += miles_covered
        result.events.append(
            ScheduleEvent(
                type=event_type,
                start_at=state["cursor"],
                duration_hrs=duration_hrs,
                miles_covered=miles_covered,
                odometer_end=state["miles_done"],
            )
        )
        state["cursor"] = state["cursor"] + timedelta(hours=duration_hrs)

    def hrs_until_next_fuel(avg_mph: float) -> float:
        return max(0.0, (FUEL_INTERVAL_MILES - state["miles_since_fuel"]) / avg_mph)

    def drive_phase(hours_to_consume: float, avg_mph: float, drive_event: EventType, leg_label: str) -> bool:
        """Run the greedy drive-and-rest loop for `hours_to_consume` hours of
        driving. Emits `drive_event` for each DRIVE segment so we can tell
        deadhead miles from main-leg miles in the event log.

        Returns True if the phase finished cleanly. Returns False if the
        cycle was exhausted mid-phase — caller should bail with not-legal."""
        drive_left = hours_to_consume

        while drive_left > EPSILON:
            if clocks.cycle_remaining() <= EPSILON:
                result.not_legal_reason = (
                    f"cycle exhausted during {leg_label} at mile "
                    f"{state['miles_done']:.0f}; {drive_left:.1f} drive hrs remain"
                )
                result.is_legal = False
                result.cycle_used_at_end = clocks.cycle_used
                return False

            budgets = {
                "break":     clocks.hrs_until_break_required(),
                "drive_cap": clocks.hrs_until_driving_cap(),
                "shift_end": clocks.hrs_until_shift_end(),
                "fuel":      hrs_until_next_fuel(avg_mph),
                "drive_left": drive_left,
                "cycle":     clocks.cycle_remaining(),
            }
            next_limit = min(budgets.values())

            if next_limit > EPSILON:
                hrs = next_limit
                miles = hrs * avg_mph
                emit(drive_event, hrs, miles_covered=miles)
                clocks.drive(hrs)
                drive_left -= hrs
                continue

            # A clock hit zero — insert the appropriate reset event.
            # Priority: rest_10 > break_30 > fuel (a 10-hr reset implies the
            # break reset; a break alone won't help if the 11-hr cap or 14-hr
            # window has triggered).
            if budgets["drive_cap"] <= EPSILON or budgets["shift_end"] <= EPSILON:
                emit(EventType.REST_10, REST_RESET_HOURS)
                clocks.rest_10()
            elif budgets["break"] <= EPSILON:
                emit(EventType.BREAK_30, BREAK_DURATION_HOURS)
                clocks.break_30()
            elif budgets["fuel"] <= EPSILON:
                emit(EventType.FUEL, FUEL_DURATION_HOURS)
                clocks.on_duty(FUEL_DURATION_HOURS)
                state["miles_since_fuel"] = 0.0
            else:
                raise RuntimeError(
                    f"scheduler stuck during {leg_label}: "
                    f"next_limit={next_limit}, budgets={budgets}"
                )

        return True

    # --- Leg A: deadhead (current_location → pickup) -----------------------

    if deadhead_drive_hours > 0:
        # Cycle pre-check: if there's not even room for a single deadhead minute,
        # bail out before emitting any DRIVE event.
        if clocks.cycle_remaining() <= EPSILON:
            result.not_legal_reason = (
                f"driver has {clocks.cycle_remaining():.1f} hrs cycle remaining; "
                f"deadhead from current_location needs {deadhead_drive_hours:.1f} drive hrs"
            )
            result.is_legal = False
            result.cycle_used_at_end = clocks.cycle_used
            return result

        if not drive_phase(deadhead_drive_hours, deadhead_avg_mph, EventType.DEADHEAD, "deadhead"):
            return result   # not-legal already populated

    # --- arrive at pickup, do the on-duty pickup event ---------------------

    if clocks.cycle_remaining() < PICKUP_DURATION_HOURS - EPSILON:
        result.not_legal_reason = (
            f"driver has {clocks.cycle_remaining():.1f} hrs cycle remaining; "
            f"pickup needs {PICKUP_DURATION_HOURS:.1f} hrs on-duty"
        )
        result.is_legal = False
        result.cycle_used_at_end = clocks.cycle_used
        return result

    emit(EventType.PICKUP, PICKUP_DURATION_HOURS)
    clocks.on_duty(PICKUP_DURATION_HOURS)

    # --- Leg B: pickup → dropoff (main leg) --------------------------------

    if not drive_phase(total_drive_hours, main_avg_mph, EventType.DRIVE, "main leg"):
        return result   # not-legal already populated

    # --- finish the trip at the dropoff location ---------------------------

    if clocks.cycle_remaining() < DROPOFF_DURATION_HOURS - EPSILON:
        result.not_legal_reason = (
            f"driver has {clocks.cycle_remaining():.1f} hrs cycle remaining; "
            f"dropoff needs {DROPOFF_DURATION_HOURS:.1f} hrs on-duty"
        )
        result.is_legal = False
        result.cycle_used_at_end = clocks.cycle_used
        return result

    if clocks.hrs_until_shift_end() < DROPOFF_DURATION_HOURS - EPSILON:
        emit(EventType.REST_10, REST_RESET_HOURS)
        clocks.rest_10()

    emit(EventType.DROPOFF, DROPOFF_DURATION_HOURS)
    clocks.on_duty(DROPOFF_DURATION_HOURS)

    result.is_legal = True
    result.cycle_used_at_end = clocks.cycle_used
    return result
