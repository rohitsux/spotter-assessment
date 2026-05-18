"""
HOSClocks — the four simultaneous Hours-of-Service counters for one driver.

Tracks state across the trip but contains no scheduling logic. The greedy event
loop in hos_scheduler.py queries the `hrs_until_*` accessors to decide what to
do next, then calls one of `drive()`, `on_duty()`, `break_30()`, `rest_10()` to
advance state.

State variables and what resets them:

    cycle_used          rolling 70/8 on-duty total — only resets via 34-hr
                        restart (out of scope per Decision 3); within this build
                        it monotonically increases until the trip ends.
    drive_in_shift      driving time within the current 14-hr window — resets
                        on rest_10().
    on_duty_in_shift    driving + on-duty within the current 14-hr window —
                        resets on rest_10().
    drive_since_break   driving time since the last 30-min break OR 10-hr rest —
                        resets on break_30() or rest_10().

Every method is O(1). No I/O, no datetime arithmetic — the scheduler owns the
clock-on-the-wall; this class owns only counter math.
"""

from .hos_constants import (
    BREAK_DURATION_HOURS,
    BREAK_TRIGGER_HOURS,
    CYCLE_LIMIT_HOURS,
    DRIVING_LIMIT_HOURS,
    REST_RESET_HOURS,
    SHIFT_MAX_HOURS,
)


class HOSClocks:
    """Mutable state for the 4 simultaneous HOS counters. See module docstring."""

    def __init__(self, cycle_used: float = 0.0) -> None:
        # 70/8 rolling cycle — pre-loaded with the driver's used hours at trip start.
        # 49 CFR §395.3(b)(2)
        self.cycle_used: float = float(cycle_used)

        # Current shift counters — all zero at trip start (driver is fresh) and
        # after every 10-hr reset.
        self.drive_in_shift: float = 0.0      # vs 11-hr cap, §395.3(a)(3)
        self.on_duty_in_shift: float = 0.0    # vs 14-hr window, §395.3(a)(2)
        self.drive_since_break: float = 0.0   # vs 8-hr break trigger, §395.3(a)(3)(ii)

    # --- read-only accessors: "how many more hours can the driver do X?" -----

    def hrs_until_break_required(self) -> float:
        """Driving hours remaining before the 30-min break is mandatory.
        49 CFR §395.3(a)(3)(ii)"""
        return max(0.0, BREAK_TRIGGER_HOURS - self.drive_since_break)

    def hrs_until_driving_cap(self) -> float:
        """Driving hours remaining before the 11-hr daily cap.
        49 CFR §395.3(a)(3)"""
        return max(0.0, DRIVING_LIMIT_HOURS - self.drive_in_shift)

    def hrs_until_shift_end(self) -> float:
        """On-duty + driving hours remaining before the 14-hr shift window closes.
        49 CFR §395.3(a)(2)"""
        return max(0.0, SHIFT_MAX_HOURS - self.on_duty_in_shift)

    def cycle_remaining(self) -> float:
        """On-duty hours remaining in the 70/8 rolling cycle.
        49 CFR §395.3(b)(2)"""
        return max(0.0, CYCLE_LIMIT_HOURS - self.cycle_used)

    # --- state transitions: events advance the clocks ------------------------

    def drive(self, hrs: float) -> None:
        """Driving advances all three shift counters AND the cycle counter."""
        if hrs < 0:
            raise ValueError(f"drive hrs must be >= 0, got {hrs}")
        self.drive_in_shift += hrs
        self.drive_since_break += hrs
        self.on_duty_in_shift += hrs
        self.cycle_used += hrs

    def on_duty(self, hrs: float) -> None:
        """On-duty-not-driving (pickup, dropoff, fuel) advances the 14-hr and
        cycle counters but NOT the driving counters."""
        if hrs < 0:
            raise ValueError(f"on_duty hrs must be >= 0, got {hrs}")
        self.on_duty_in_shift += hrs
        self.cycle_used += hrs

    def break_30(self) -> None:
        """30-min break: resets the 8-hr drive-since-break counter ONLY.
        Does not extend the 14-hr window (break time counts against it).
        49 CFR §395.3(a)(3)(ii)"""
        self.drive_since_break = 0.0
        # The break itself is off-duty time — it consumes 14-hr window space
        # because the window is wall-clock-anchored. The scheduler tracks
        # wall-clock separately; here we just bump on_duty_in_shift to keep
        # the shift counter monotonic during the break window.
        self.on_duty_in_shift += BREAK_DURATION_HOURS

    def rest_10(self) -> None:
        """10 consecutive off-duty hours: reset the 14-hr window, the 11-hr
        driving limit, and the 30-min break counter. Does NOT reset the
        70-hr cycle (that needs a 34-hr restart, out of scope per Decision 3).
        49 CFR §395.3(a)(1)"""
        self.drive_in_shift = 0.0
        self.on_duty_in_shift = 0.0
        self.drive_since_break = 0.0
        # Cycle is intentionally NOT reset.

    # --- introspection -------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"HOSClocks(cycle_used={self.cycle_used:.2f}, "
            f"drive_in_shift={self.drive_in_shift:.2f}, "
            f"on_duty_in_shift={self.on_duty_in_shift:.2f}, "
            f"drive_since_break={self.drive_since_break:.2f})"
        )
