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
from django.core.cache import cache
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import Trip
from .ors_client import ORSError, autocomplete
from .serializers import TripSerializer
from .services.trip_builder import build_trip


# 10-min TTL — long enough that repeat-typing within a session always hits,
# short enough that a fresh ORS dataset shows up within the hour.
AUTOCOMPLETE_CACHE_TTL_SECONDS = 600


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


@api_view(["GET"])
def geocode_autocomplete(request):
    """GET /api/geocode/?text=<q>

    Thin proxy over ORS /geocode/autocomplete. Keeps the API key server-side
    so the frontend can call same-origin during dev (Vite proxy) and prod.

    Cached for 10 min on the lowercased+stripped query. Repeat keystrokes
    within a typing session ('Hou' -> 'Hous' -> ...) hit cache after the
    first lookup; common cities (Houston, Chicago, Bangalore) stay warm
    across sessions. Cache hits skip the ORS round-trip entirely — typical
    response under 20 ms vs ~300 ms for a cold hit.

    Empty/short queries return an empty list without hitting ORS — protects
    the 2000/day quota from runaway keystrokes.
    """
    text = (request.query_params.get("text") or "").strip()
    if len(text) < 2:
        return Response({"results": []})

    cache_key = f"geo:{text.lower()}"
    payload = cache.get(cache_key)
    if payload is not None:
        return Response(payload)

    try:
        results = autocomplete(text, api_key=settings.ORS_API_KEY, size=5)
    except ORSError as exc:
        return Response(
            {
                "detail": "Routing service unavailable",
                "upstream_status": exc.status,
                "upstream_message": str(exc),
            },
            status=status.HTTP_502_BAD_GATEWAY,
        )

    payload = {
        "results": [
            {"label": r.label, "lng": r.lng, "lat": r.lat}
            for r in results
        ]
    }
    cache.set(cache_key, payload, timeout=AUTOCOMPLETE_CACHE_TTL_SECONDS)
    return Response(payload)
