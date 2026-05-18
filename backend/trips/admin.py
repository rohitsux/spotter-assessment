"""Admin registrations — present for dev introspection only. No end-user auth."""

from django.contrib import admin

from .models import LogDay, LogEntry, Stop, Trip


class StopInline(admin.TabularInline):
    model = Stop
    extra = 0


class LogEntryInline(admin.TabularInline):
    model = LogEntry
    extra = 0


class LogDayInline(admin.TabularInline):
    model = LogDay
    extra = 0


@admin.register(Trip)
class TripAdmin(admin.ModelAdmin):
    list_display = ("id", "pickup_location", "dropoff_location", "is_legal", "total_miles", "created_at")
    list_filter = ("is_legal",)
    search_fields = ("pickup_location", "dropoff_location")
    inlines = [StopInline, LogDayInline]


@admin.register(Stop)
class StopAdmin(admin.ModelAdmin):
    list_display = ("id", "trip_id", "type", "city", "state", "mile_marker", "arrive_at")
    list_filter = ("type",)


@admin.register(LogDay)
class LogDayAdmin(admin.ModelAdmin):
    list_display = ("id", "trip_id", "date", "total_driving_hrs", "total_on_clock_hrs", "total_miles")
    inlines = [LogEntryInline]


@admin.register(LogEntry)
class LogEntryAdmin(admin.ModelAdmin):
    list_display = ("id", "log_day_id", "duty_status", "start_time_minutes", "end_time_minutes", "city", "state")
    list_filter = ("duty_status",)
