"""
Domain models for the Spotter trip planner.

Four models per Decision 6:

    Trip      one dispatcher request — the form inputs + computed outcome
    Stop      one geographic point on the map (pickup, dropoff, fuel, rest, break)
    LogDay    one 24-hour duty-status sheet, with admin block + totals
    LogEntry  one row in a LogDay's 24-hour grid (duty-status segment)

Trip 1—* Stop, Trip 1—* LogDay, LogDay 1—* LogEntry.

Stops feed the map view; LogEntries feed the 24-hour grid. A pickup creates
one Stop AND one LogEntry with shared city/state/remark (Decision 6 tradeoff).
"""

from django.db import models


class Trip(models.Model):
    """Top-level trip request + computed schedule summary."""

    # --- form inputs (Decision 6 + BUILD-BRIEF §1) -----------------------------
    current_location = models.CharField(max_length=200)
    pickup_location = models.CharField(max_length=200)
    dropoff_location = models.CharField(max_length=200)
    current_cycle_used_hrs = models.DecimalField(max_digits=4, decimal_places=2)

    # --- computed outputs (filled in by services.trip_builder) -----------------
    start_at = models.DateTimeField(null=True, blank=True)
    end_at = models.DateTimeField(null=True, blank=True)
    total_miles = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    total_drive_hours = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    is_legal = models.BooleanField(null=True, blank=True)
    cycle_used_at_end = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    not_legal_reason = models.CharField(max_length=300, blank=True, default="")

    # Full ORS route geometry (GeoJSON LineString) cached for the frontend map.
    # Persisted so a GET /api/trips/<id>/ replay doesn't re-hit ORS.
    route_geometry = models.JSONField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Trip #{self.pk}: {self.pickup_location} -> {self.dropoff_location}"


class Stop(models.Model):
    """A geographic event on the trip. Feeds the map markers."""

    class StopType(models.TextChoices):
        DEADHEAD = "DEADHEAD", "Deadhead depart"
        PICKUP = "PICKUP", "Pickup"
        DROPOFF = "DROPOFF", "Dropoff"
        FUEL = "FUEL", "Fuel"
        REST_10 = "REST_10", "10-hour rest"
        BREAK_30 = "BREAK_30", "30-minute break"

    trip = models.ForeignKey(Trip, on_delete=models.CASCADE, related_name="stops")
    type = models.CharField(max_length=10, choices=StopType.choices)
    city = models.CharField(max_length=120)
    state = models.CharField(max_length=2)
    lat = models.DecimalField(max_digits=9, decimal_places=6)
    lng = models.DecimalField(max_digits=9, decimal_places=6)

    # cumulative miles from origin at the moment this stop occurs
    mile_marker = models.DecimalField(max_digits=8, decimal_places=2)

    arrive_at = models.DateTimeField()
    depart_at = models.DateTimeField()
    duration_minutes = models.IntegerField()

    remark = models.CharField(max_length=200, blank=True, default="")

    class Meta:
        ordering = ["trip_id", "arrive_at"]

    def __str__(self) -> str:
        return f"{self.get_type_display()} @ {self.city}, {self.state}"


class LogDay(models.Model):
    """One 24-hour duty-status sheet for one calendar day of the trip."""

    trip = models.ForeignKey(Trip, on_delete=models.CASCADE, related_name="log_days")
    date = models.DateField()

    # Admin block (Decision 6 — hardcoded demo values per resolved Q2)
    driver_name = models.CharField(max_length=120)
    tractor_number = models.CharField(max_length=20)
    trailer_number = models.CharField(max_length=20)
    shipper = models.CharField(max_length=120)
    commodity = models.CharField(max_length=120)

    # Daily totals — sum of LogEntry segments per duty-status line.
    # Invariant: off + sleeper + driving + on_duty == 24.0
    total_off_duty_hrs = models.DecimalField(max_digits=4, decimal_places=2, default=0)
    total_sleeper_hrs = models.DecimalField(max_digits=4, decimal_places=2, default=0)
    total_driving_hrs = models.DecimalField(max_digits=4, decimal_places=2, default=0)
    total_on_duty_hrs = models.DecimalField(max_digits=4, decimal_places=2, default=0)

    total_miles = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    # Circled number in the FMCSA paper log — sum of driving + on-duty for this day,
    # feeds the rolling 70-hour cycle (Schneider training video).
    total_on_clock_hrs = models.DecimalField(max_digits=4, decimal_places=2, default=0)

    class Meta:
        ordering = ["trip_id", "date"]
        constraints = [
            models.UniqueConstraint(fields=["trip", "date"], name="unique_logday_per_trip_date"),
        ]

    def __str__(self) -> str:
        return f"LogDay {self.date} (trip #{self.trip_id})"


class LogEntry(models.Model):
    """One contiguous duty-status segment within a LogDay's 24-hour grid."""

    class DutyStatus(models.IntegerChoices):
        # Numbered 1-4 to match the FMCSA paper-log row numbering.
        OFF_DUTY = 1, "Off-Duty"
        SLEEPER = 2, "Sleeper Berth"
        DRIVING = 3, "Driving"
        ON_DUTY = 4, "On-Duty (not driving)"

    log_day = models.ForeignKey(LogDay, on_delete=models.CASCADE, related_name="entries")

    # Minutes since midnight on log_day.date. 0..1440 inclusive.
    # An entry that crosses midnight is split into two entries on adjacent dates.
    start_time_minutes = models.IntegerField()
    end_time_minutes = models.IntegerField()

    duty_status = models.IntegerField(choices=DutyStatus.choices)

    # Required per Decision 6 — Schneider video confirms city/state must be on every status change.
    city = models.CharField(max_length=120)
    state = models.CharField(max_length=2)
    remark = models.CharField(max_length=200, blank=True, default="")

    # True for on-duty events that happen at a stationary location (e.g. 30-min cat-scale break).
    # Renders as a bracket below the timeline in the 24-hr grid (Decision 2).
    is_stationary = models.BooleanField(default=False)

    class Meta:
        ordering = ["log_day_id", "start_time_minutes"]

    def __str__(self) -> str:
        return f"{self.get_duty_status_display()} {self.start_time_minutes}-{self.end_time_minutes}"
