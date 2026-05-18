"""
DRF serializers for the trips API. Three nested layers:

    TripSerializer
      └── stops:    StopSerializer (many)
      └── log_days: LogDaySerializer (many)
                      └── entries: LogEntrySerializer (many)

Read shape matches the API contract in the plan (§3). Write shape is the
4 form inputs only — everything else (start_at, totals, route_geometry,
nested stops/log_days) is computed by services.trip_builder and serialized
as read_only.
"""

from rest_framework import serializers

from .models import LogDay, LogEntry, Stop, Trip


class LogEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = LogEntry
        fields = [
            "start_time_minutes",
            "end_time_minutes",
            "duty_status",
            "city",
            "state",
            "remark",
            "is_stationary",
        ]


class LogDaySerializer(serializers.ModelSerializer):
    entries = LogEntrySerializer(many=True, read_only=True)

    class Meta:
        model = LogDay
        fields = [
            "date",
            "driver_name",
            "tractor_number",
            "trailer_number",
            "shipper",
            "commodity",
            "total_off_duty_hrs",
            "total_sleeper_hrs",
            "total_driving_hrs",
            "total_on_duty_hrs",
            "total_miles",
            "total_on_clock_hrs",
            "entries",
        ]


class StopSerializer(serializers.ModelSerializer):
    class Meta:
        model = Stop
        fields = [
            "type",
            "city",
            "state",
            "lat",
            "lng",
            "mile_marker",
            "arrive_at",
            "depart_at",
            "duration_minutes",
            "remark",
        ]


class TripSerializer(serializers.ModelSerializer):
    stops = StopSerializer(many=True, read_only=True)
    log_days = LogDaySerializer(many=True, read_only=True)

    class Meta:
        model = Trip
        fields = [
            "id",
            # 4 form inputs — writable on POST
            "current_location",
            "pickup_location",
            "dropoff_location",
            "current_cycle_used_hrs",
            # computed outputs — read-only
            "start_at",
            "end_at",
            "total_miles",
            "total_drive_hours",
            "is_legal",
            "cycle_used_at_end",
            "not_legal_reason",
            "route_geometry",
            "created_at",
            # nested
            "stops",
            "log_days",
        ]
        read_only_fields = [
            "id",
            "start_at",
            "end_at",
            "total_miles",
            "total_drive_hours",
            "is_legal",
            "cycle_used_at_end",
            "not_legal_reason",
            "route_geometry",
            "created_at",
        ]

    def validate_current_cycle_used_hrs(self, value):
        if value < 0 or value > 70:
            raise serializers.ValidationError(
                "current_cycle_used_hrs must be between 0 and 70"
            )
        return value
