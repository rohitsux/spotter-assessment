"""
DRF viewset for the trips API.

POST /api/trips/      → run the full pipeline, persist, return the Trip
GET  /api/trips/<id>/ → return a persisted Trip (no recomputation; ORS
                        geometry is cached on the row)

Start-of-trip datetime is hardcoded per resolved Q1: tomorrow 06:00 UTC.
ORS failures (network, HTTP, empty result) → HTTP 502 per resolved Q4.
"""

import logging
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

logger = logging.getLogger(__name__)


# 10-min TTL — long enough that repeat-typing within a session always hits,
# short enough that a fresh ORS dataset shows up within the hour.
AUTOCOMPLETE_CACHE_TTL_SECONDS = 600


def _human_routing_error(exc: ORSError) -> str:
    """Translate an ORSError into a dispatcher-friendly message.
    The technical detail still lives in the server log; the client gets
    something actionable."""
    status = exc.status
    if status == 429:
        return "The routing service is rate-limiting us. Try again in a minute."
    if status in (502, 503, 504):
        return "The routing service is temporarily unavailable. Try again in a moment."
    if status == 401 or status == 403:
        return "The routing service rejected our credentials. Contact the operator."
    if status == 400:
        return "Couldn't route between those locations. Check that pickup and dropoff are valid."
    if status is None:
        # Network-level failure (DNS, connection refused, timeout)
        return "Couldn't reach the routing service. Check your network and try again."
    return "The routing service couldn't complete this request. Try again in a moment."


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
            # Log the technical details server-side so we can debug. The
            # 'Bad Gateway: /api/trips/' Django log line on its own doesn't
            # tell us if it was rate-limit, quota, network blip, or schema
            # drift — this gives us upstream status + body for the trace.
            logger.warning(
                "ORS upstream error during build_trip: status=%s body=%s exc=%s",
                exc.status, (exc.body or "")[:200], exc,
            )
            # Return a human-readable body. The dispatcher just needs to know
            # what's wrong and what to do; "ORS directions returned HTTP 503"
            # is technical noise. Map the upstream status to a plain hint.
            return Response(
                {"detail": _human_routing_error(exc)},
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

    # Sanitize: cache backends like memcached reject spaces and ":" in keys.
    # LocMemCache (our current backend) tolerates them but emits a CacheKeyWarning.
    # Stripping spaces and other non-alphanumeric chars makes the key portable
    # AND collapses near-duplicates ("Houston, TX" vs "houston tx" hit the same entry).
    safe = "".join(c if c.isalnum() else "_" for c in text.lower())
    cache_key = f"geo_{safe}"
    payload = cache.get(cache_key)
    if payload is not None:
        return Response(payload)

    try:
        results = autocomplete(text, api_key=settings.ORS_API_KEY, size=5)
    except ORSError as exc:
        logger.warning(
            "ORS upstream error during autocomplete: status=%s body=%s exc=%s",
            exc.status, (exc.body or "")[:200], exc,
        )
        return Response(
            {"detail": _human_routing_error(exc)},
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
