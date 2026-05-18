"""
Unit tests for HOSClocks — the pure-arithmetic layer of the HOS scheduler.

These tests exercise each counter independently and the interactions between
them (drive resets vs cycle resets, etc.). No Django, no datetimes — just
counter math.
"""

import pytest

from trips.hos_clocks import HOSClocks
from trips.hos_constants import (
    BREAK_TRIGGER_HOURS,
    CYCLE_LIMIT_HOURS,
    DRIVING_LIMIT_HOURS,
    REST_RESET_HOURS,
    SHIFT_MAX_HOURS,
)


# --- initial state ----------------------------------------------------------


def test_fresh_clocks_have_full_budgets():
    c = HOSClocks(cycle_used=0)
    assert c.cycle_remaining() == CYCLE_LIMIT_HOURS                  # 70
    assert c.hrs_until_driving_cap() == DRIVING_LIMIT_HOURS           # 11
    assert c.hrs_until_shift_end() == SHIFT_MAX_HOURS                 # 14
    assert c.hrs_until_break_required() == BREAK_TRIGGER_HOURS        # 8


def test_partially_used_cycle_reduces_only_cycle_remaining():
    c = HOSClocks(cycle_used=20)
    assert c.cycle_remaining() == pytest.approx(50.0)
    assert c.hrs_until_driving_cap() == DRIVING_LIMIT_HOURS           # shift is fresh
    assert c.hrs_until_shift_end() == SHIFT_MAX_HOURS
    assert c.hrs_until_break_required() == BREAK_TRIGGER_HOURS


# --- drive() advances all 4 counters ----------------------------------------


def test_drive_advances_all_four_counters():
    c = HOSClocks(cycle_used=10)
    c.drive(3.0)
    assert c.cycle_used == pytest.approx(13.0)
    assert c.drive_in_shift == pytest.approx(3.0)
    assert c.on_duty_in_shift == pytest.approx(3.0)
    assert c.drive_since_break == pytest.approx(3.0)


def test_drive_reduces_remaining_budgets():
    c = HOSClocks()
    c.drive(5.0)
    assert c.hrs_until_driving_cap() == pytest.approx(6.0)            # 11 - 5
    assert c.hrs_until_shift_end() == pytest.approx(9.0)              # 14 - 5
    assert c.hrs_until_break_required() == pytest.approx(3.0)         # 8 - 5
    assert c.cycle_remaining() == pytest.approx(65.0)                 # 70 - 5


def test_drive_negative_hours_raises():
    c = HOSClocks()
    with pytest.raises(ValueError):
        c.drive(-1.0)


# --- on_duty() advances 14-hr + cycle, NOT drive counters -------------------


def test_on_duty_advances_shift_and_cycle_only():
    c = HOSClocks(cycle_used=10)
    c.on_duty(1.0)
    assert c.cycle_used == pytest.approx(11.0)
    assert c.on_duty_in_shift == pytest.approx(1.0)
    assert c.drive_in_shift == 0.0
    assert c.drive_since_break == 0.0


def test_pickup_then_drive_consumes_window():
    c = HOSClocks()
    c.on_duty(1.0)                                                    # 1-hr pickup
    c.drive(8.0)                                                      # 8 hrs driving
    assert c.hrs_until_shift_end() == pytest.approx(5.0)              # 14 - 9
    assert c.hrs_until_driving_cap() == pytest.approx(3.0)            # 11 - 8
    assert c.hrs_until_break_required() == pytest.approx(0.0)         # 8 - 8 = at the trigger


# --- break_30() resets only the 8-hr trigger --------------------------------


def test_break_30_resets_drive_since_break_only():
    c = HOSClocks()
    c.drive(8.0)
    assert c.hrs_until_break_required() == pytest.approx(0.0)
    c.break_30()
    assert c.hrs_until_break_required() == BREAK_TRIGGER_HOURS        # reset to 8
    assert c.drive_in_shift == pytest.approx(8.0)                     # still 8
    assert c.cycle_used == pytest.approx(8.0)                         # cycle unaffected by break


def test_break_30_consumes_shift_window():
    """A 30-min break consumes 0.5 hr of the 14-hr wall-clock window."""
    c = HOSClocks()
    c.drive(8.0)
    c.break_30()
    # 14 - 8 driving - 0.5 break = 5.5 hrs of shift left
    assert c.hrs_until_shift_end() == pytest.approx(5.5)


# --- rest_10() resets all shift counters, NOT cycle -------------------------


def test_rest_10_resets_all_shift_counters():
    c = HOSClocks(cycle_used=20)
    c.drive(11.0)                                                     # max out the day
    assert c.hrs_until_driving_cap() == pytest.approx(0.0)
    assert c.hrs_until_shift_end() == pytest.approx(3.0)              # 14 - 11
    c.rest_10()
    assert c.hrs_until_driving_cap() == DRIVING_LIMIT_HOURS           # 11 reset
    assert c.hrs_until_shift_end() == SHIFT_MAX_HOURS                 # 14 reset
    assert c.hrs_until_break_required() == BREAK_TRIGGER_HOURS        # 8 reset


def test_rest_10_does_not_reset_cycle():
    """Decision 3: 70-hr cycle only resets via 34-hr restart, which is OUT OF SCOPE."""
    c = HOSClocks(cycle_used=20)
    c.drive(11.0)
    assert c.cycle_used == pytest.approx(31.0)
    c.rest_10()
    assert c.cycle_used == pytest.approx(31.0)                        # unchanged
    assert c.cycle_remaining() == pytest.approx(39.0)


# --- 70-hr cycle exhaustion -------------------------------------------------


def test_cycle_exhausts_after_70_hrs():
    c = HOSClocks(cycle_used=65)
    c.drive(5.0)
    assert c.cycle_remaining() == pytest.approx(0.0)


def test_cycle_remaining_clamped_at_zero():
    """Negative budgets shouldn't leak out — the schedule loop tests against 0."""
    c = HOSClocks(cycle_used=80)                                      # over-cap
    assert c.cycle_remaining() == 0.0


# --- realistic mini-day sequence --------------------------------------------


def test_full_day_sequence_matches_expected_state():
    """One driving day: pickup + 8 hrs drive + 30-min break + 3 hrs drive."""
    c = HOSClocks(cycle_used=20)
    c.on_duty(1.0)              # pickup
    c.drive(8.0)                # first half
    c.break_30()                # mandatory 30-min
    c.drive(3.0)                # second half — hits 11-hr cap

    assert c.drive_in_shift == pytest.approx(11.0)                    # at cap
    assert c.hrs_until_driving_cap() == pytest.approx(0.0)
    assert c.on_duty_in_shift == pytest.approx(12.5)                  # 1 + 8 + 0.5 + 3
    assert c.cycle_used == pytest.approx(32.0)                        # 20 + 1 + 8 + 3
    # break doesn't count against cycle
    assert c.hrs_until_shift_end() == pytest.approx(1.5)              # 14 - 12.5
