"""
OpenRouteService client. Two endpoints used:

    geocode(text)       /geocode/search      free-text → (label, lng, lat)
    route_hgv(src, dst) /v2/directions/driving-hgv/geojson
                                              two coords → full GeoJSON FeatureCollection

The driving-hgv profile is the most important domain choice in this app
(Decision 1) — it respects bridge heights and weight limits, so the polyline
on the map represents a legal truck route, not a passenger-car shortcut.

This module is a thin wrapper. It does not retry, cache, or rate-limit.
Failures raise ORSError with the upstream status and body. The caller
(services/trip_builder.py) is responsible for converting that into the
HTTP 502 response described in resolved-question 4.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests

ORS_BASE = "https://api.openrouteservice.org"
DEFAULT_TIMEOUT_SECONDS = 30


class ORSError(RuntimeError):
    """Raised when an ORS call fails (HTTP error, empty result, parse error)."""

    def __init__(self, message: str, *, status: int | None = None, body: str | None = None):
        super().__init__(message)
        self.status = status
        self.body = body


@dataclass(frozen=True)
class GeocodeResult:
    label: str           # e.g. "Houston, Texas, United States"
    lng: float
    lat: float

    @property
    def coord(self) -> list[float]:
        """[lng, lat] — the order ORS uses for routing input."""
        return [self.lng, self.lat]


@dataclass(frozen=True)
class RouteResult:
    miles: float
    hours: float
    geojson: dict[str, Any]      # full FeatureCollection — caller persists this for the map

    @property
    def coordinates(self) -> list[list[float]]:
        """The polyline as a list of [lng, lat] points."""
        return self.geojson["features"][0]["geometry"]["coordinates"]


# --- public API -------------------------------------------------------------


def geocode(text: str, api_key: str, *, timeout: float = DEFAULT_TIMEOUT_SECONDS) -> GeocodeResult:
    """Free-text → most-likely geographic match. Raises ORSError on failure."""
    if not api_key:
        raise ORSError("ORS_API_KEY is not configured")

    url = f"{ORS_BASE}/geocode/search"
    params = {"api_key": api_key, "text": text, "size": 1}
    try:
        resp = requests.get(url, params=params, timeout=timeout, headers={"Accept": "application/json"})
    except requests.RequestException as exc:
        raise ORSError(f"network error contacting ORS geocode: {exc}") from exc

    if not resp.ok:
        raise ORSError(
            f"ORS geocode returned HTTP {resp.status_code} for {text!r}",
            status=resp.status_code,
            body=resp.text[:500],
        )

    data = resp.json()
    features = data.get("features") or []
    if not features:
        raise ORSError(f"ORS geocode returned no results for {text!r}")

    feat = features[0]
    coords = feat["geometry"]["coordinates"]   # [lng, lat]
    label = feat["properties"].get("label", text)
    return GeocodeResult(label=label, lng=float(coords[0]), lat=float(coords[1]))


def route_hgv(
    src: GeocodeResult | list[float],
    dst: GeocodeResult | list[float],
    api_key: str,
    *,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> RouteResult:
    """Compute a driving-hgv (truck-aware) route between two coordinates.
    Accepts either GeocodeResult instances or raw [lng, lat] lists."""
    if not api_key:
        raise ORSError("ORS_API_KEY is not configured")

    src_coord = src.coord if isinstance(src, GeocodeResult) else list(src)
    dst_coord = dst.coord if isinstance(dst, GeocodeResult) else list(dst)

    url = f"{ORS_BASE}/v2/directions/driving-hgv/geojson"
    headers = {
        "Authorization": api_key,
        "Content-Type": "application/json",
        "Accept": "application/geo+json",
    }
    body = {"coordinates": [src_coord, dst_coord], "instructions": False}

    try:
        resp = requests.post(url, headers=headers, json=body, timeout=timeout)
    except requests.RequestException as exc:
        raise ORSError(f"network error contacting ORS directions: {exc}") from exc

    if not resp.ok:
        raise ORSError(
            f"ORS directions returned HTTP {resp.status_code}",
            status=resp.status_code,
            body=resp.text[:500],
        )

    data = resp.json()
    features = data.get("features") or []
    if not features:
        raise ORSError("ORS directions returned no route")

    summary = features[0]["properties"]["summary"]
    distance_m = float(summary["distance"])
    duration_s = float(summary["duration"])

    return RouteResult(
        miles=distance_m / 1609.34,
        hours=duration_s / 3600.0,
        geojson=data,
    )
