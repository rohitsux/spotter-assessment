"""
DRF viewset for the trips API.

POST /api/trips/      → run the full pipeline, persist, return the Trip
GET  /api/trips/<id>/ → return a persisted Trip (no recomputation; ORS
                        geometry is cached on the row)

Start-of-trip datetime is hardcoded per resolved Q1: tomorrow 06:00 UTC.
ORS failures (network, HTTP, empty result) → HTTP 502 per resolved Q4.
"""

from datetime import datetime, time, timedelta, timezone

from django.conf import settings
from rest_framework import mixins, status, viewsets
from rest_framework.response import Response

from .models import Trip
from .ors_client import ORSError
from .serializers import TripSerializer
from .services.trip_builder import build_trip


def _default_start_at() -> datetime:
    """Tomorrow 06:00 UTC. Resolved Q1: form has no datetime field, so we
    pick a fixed start so the Loom narration stays consistent and the
    summary card has a real timestamp to display."""
    tomorrow = (datetime.now(timezone.utc) + timedelta(days=1)).date()
    return datetime.combine(tomorrow, time(6, 0), tzinfo=timezone.utc)


class TripViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """POST create + GET retrieve only. No list, update, or delete."""

    queryset = Trip.objects.all()
    serializer_class = TripSerializer

    def create(self, request, *args, **kwargs):
        # Validate the 4 form inputs first
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            trip = build_trip(
                current_location=data["current_location"],
                pickup_location=data["pickup_location"],
                dropoff_location=data["dropoff_location"],
                current_cycle_used_hrs=float(data["current_cycle_used_hrs"]),
                start_at=_default_start_at(),
                api_key=settings.ORS_API_KEY,
            )
        except ORSError as exc:
            return Response(
                {
                    "detail": "Routing service unavailable",
                    "upstream_status": exc.status,
                    "upstream_message": str(exc),
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )

        output = TripSerializer(trip, context=self.get_serializer_context()).data
        return Response(output, status=status.HTTP_201_CREATED)
