"""
Hours-of-Service constants for property-carrying CMV drivers under the 70/8 rule.

Every constant in this module is cited to a specific section of 49 CFR Part 395.
A reviewer can verify each value against the FMCSA regs directly.

Scope is conservative per Decision 3:
  - In scope: the 4 core clocks (§395.3 a, b)
  - Out of scope: sleeper-berth split, 34-hr restart, short-haul exceptions,
    16-hr big-day exception, personal conveyance, co-driver teams.

This module is pure data. No functions, no side effects.
The clock arithmetic lives in hos_clocks.py; the schedule loop in hos_scheduler.py.
"""

# --- The four core clocks ---------------------------------------------------

# 14-hour driving window — once any on-duty work begins, all driving must be
# completed within 14 consecutive hours. Cannot be extended by off-duty time.
# 49 CFR §395.3(a)(2)
SHIFT_MAX_HOURS: float = 14.0

# 11-hour driving limit — within a single 14-hour window, total driving time
# may not exceed 11 hours.
# 49 CFR §395.3(a)(3)
DRIVING_LIMIT_HOURS: float = 11.0

# 30-minute break trigger — after 8 cumulative hours of driving without at
# least a 30-minute non-driving interruption, driver must take 30 min off
# (off-duty, sleeper, or on-duty-not-driving — but not driving).
# 49 CFR §395.3(a)(3)(ii)
BREAK_TRIGGER_HOURS: float = 8.0
BREAK_DURATION_MINUTES: int = 30
BREAK_DURATION_HOURS: float = BREAK_DURATION_MINUTES / 60.0  # 0.5

# 70 hours / 8 days — rolling on-duty total across any 8 consecutive days.
# Driver may not drive after reaching 70 on-duty hours in the window.
# 49 CFR §395.3(b)(2)
CYCLE_LIMIT_HOURS: float = 70.0
CYCLE_WINDOW_DAYS: int = 8

# 10-hour reset — 10 consecutive off-duty hours reset the 14-hr window,
# the 11-hr driving limit, and the 30-min break counter (but NOT the 70-hr cycle).
# 49 CFR §395.3(a)(1)
REST_RESET_HOURS: float = 10.0

# Decision 8 (and Schneider training video) — the 10-hour reset is logged as
# 1 hr OFF_DUTY (admin / dinner) followed by 9 hr SLEEPER. Sums to 10 hours.
REST_OFF_DUTY_PREFIX_HOURS: float = 1.0
REST_SLEEPER_HOURS: float = REST_RESET_HOURS - REST_OFF_DUTY_PREFIX_HOURS  # 9.0


# --- Trip-shape constants (not from §395; spec assumptions per Decision 8) --

# Fuel stop every 1,000 miles, 15 minutes on-duty-not-driving (cat scale, fueling).
# Assessment spec assumption — real-world refueling cadence varies by tank size,
# trailer, and route. 1,000 mi is the conservative-but-realistic interval for an
# 18-wheeler with a 200-gal tank at ~6 mpg.
FUEL_INTERVAL_MILES: float = 1000.0
FUEL_DURATION_MINUTES: int = 15
FUEL_DURATION_HOURS: float = FUEL_DURATION_MINUTES / 60.0  # 0.25

# Pickup and dropoff are each 1 hour on-duty-not-driving (loading / paperwork).
# Spec assumption from the problem statement.
PICKUP_DURATION_HOURS: float = 1.0
DROPOFF_DURATION_HOURS: float = 1.0


# --- FMCSA duty-status row codes -------------------------------------------
# These mirror trips.models.LogEntry.DutyStatus and the FMCSA paper-log rows.
# Defined here too so hos_scheduler.py can emit events without importing Django.

DUTY_OFF_DUTY: int = 1
DUTY_SLEEPER: int = 2
DUTY_DRIVING: int = 3
DUTY_ON_DUTY: int = 4
