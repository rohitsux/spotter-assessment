"""
Tests for ors_client.py — three tiers:

1. Mocked unit tests (always run) — monkeypatched requests, fast, isolated.
2. Fixture-replay test (always run) — parses the captured Houston→Chicago
   GeoJSON fixture, regression-tests the parser against a real ORS payload.
3. Live test (opt-in) — hits real ORS once. Gated on ORS_LIVE=1 to protect
   the 2,000/day free tier quota. Run manually before Loom recording:
       ORS_LIVE=1 pytest backend/tests/test_ors_client.py -m live_ors
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from trips import ors_client
from trips.ors_client import GeocodeResult, ORSError, RouteResult


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "ors_route_houston_chicago.geojson"


# --- helpers ---------------------------------------------------------------


class _FakeResponse:
    """Minimal stand-in for requests.Response."""

    def __init__(self, payload: dict | None = None, *, status: int = 200, text: str = ""):
        self._payload = payload or {}
        self.status_code = status
        self.text = text or json.dumps(self._payload)

    @property
    def ok(self) -> bool:
        return 200 <= self.status_code < 300

    def json(self) -> dict:
        return self._payload


# --- geocode (mocked) ------------------------------------------------------


def test_geocode_parses_lng_lat_and_label(monkeypatch):
    payload = {
        "features": [
            {
                "geometry": {"coordinates": [-95.3698, 29.7604]},
                "properties": {"label": "Houston, Texas, United States"},
            }
        ]
    }
    monkeypatch.setattr(ors_client.requests, "get", lambda *a, **kw: _FakeResponse(payload))

    result = ors_client.geocode("Houston, TX", api_key="fake-key")
    assert isinstance(result, GeocodeResult)
    assert result.label == "Houston, Texas, United States"
    assert result.lng == pytest.approx(-95.3698)
    assert result.lat == pytest.approx(29.7604)
    assert result.coord == [-95.3698, 29.7604]


def test_geocode_raises_on_empty_results(monkeypatch):
    monkeypatch.setattr(ors_client.requests, "get", lambda *a, **kw: _FakeResponse({"features": []}))
    with pytest.raises(ORSError, match="no results"):
        ors_client.geocode("Atlantis", api_key="fake-key")


def test_geocode_raises_on_http_error(monkeypatch):
    monkeypatch.setattr(
        ors_client.requests, "get",
        lambda *a, **kw: _FakeResponse({}, status=429, text="rate limited"),
    )
    with pytest.raises(ORSError) as exc:
        ors_client.geocode("Houston, TX", api_key="fake-key")
    assert exc.value.status == 429
    assert "429" in str(exc.value)


def test_geocode_raises_when_api_key_missing():
    with pytest.raises(ORSError, match="not configured"):
        ors_client.geocode("Houston, TX", api_key="")


# --- route_hgv (mocked) ----------------------------------------------------


def test_route_hgv_parses_distance_and_duration(monkeypatch):
    # 1,088 mi == 1,751,033 m  |  24 hr == 86,400 s
    payload = {
        "features": [
            {
                "geometry": {"type": "LineString", "coordinates": [[-95.37, 29.76], [-87.65, 41.85]]},
                "properties": {"summary": {"distance": 1751033.0, "duration": 86400.0}},
            }
        ]
    }
    monkeypatch.setattr(ors_client.requests, "post", lambda *a, **kw: _FakeResponse(payload))

    result = ors_client.route_hgv([-95.37, 29.76], [-87.65, 41.85], api_key="fake-key")
    assert isinstance(result, RouteResult)
    assert result.miles == pytest.approx(1088.0, abs=0.5)
    assert result.hours == pytest.approx(24.0, abs=0.01)
    assert result.geojson == payload
    assert result.coordinates == [[-95.37, 29.76], [-87.65, 41.85]]


def test_route_hgv_accepts_geocode_result_instances(monkeypatch):
    payload = {
        "features": [
            {
                "geometry": {"type": "LineString", "coordinates": [[0, 0], [1, 1]]},
                "properties": {"summary": {"distance": 1609.34, "duration": 3600.0}},
            }
        ]
    }
    captured = {}

    def fake_post(*args, **kwargs):
        captured["body"] = kwargs.get("json")
        return _FakeResponse(payload)

    monkeypatch.setattr(ors_client.requests, "post", fake_post)

    src = GeocodeResult(label="A", lng=-95.0, lat=29.0)
    dst = GeocodeResult(label="B", lng=-87.0, lat=41.0)
    ors_client.route_hgv(src, dst, api_key="fake-key")

    assert captured["body"]["coordinates"] == [[-95.0, 29.0], [-87.0, 41.0]]


def test_route_hgv_raises_on_empty_features(monkeypatch):
    monkeypatch.setattr(ors_client.requests, "post", lambda *a, **kw: _FakeResponse({"features": []}))
    with pytest.raises(ORSError, match="no route"):
        ors_client.route_hgv([-95.0, 29.0], [-87.0, 41.0], api_key="fake-key")


def test_route_hgv_raises_on_http_error(monkeypatch):
    monkeypatch.setattr(
        ors_client.requests, "post",
        lambda *a, **kw: _FakeResponse({}, status=500, text="upstream boom"),
    )
    with pytest.raises(ORSError) as exc:
        ors_client.route_hgv([-95.0, 29.0], [-87.0, 41.0], api_key="fake-key")
    assert exc.value.status == 500


# --- fixture-based parse test (replays a real ORS response) -----------------


@pytest.mark.skipif(
    not FIXTURE_PATH.exists(),
    reason="ORS route fixture not yet imported (will land in Phase 3.2)",
)
def test_route_hgv_parses_real_response_fixture(monkeypatch):
    """Replay a captured Houston->Chicago response. Guards the parser
    against schema drift on the real API."""
    payload = json.loads(FIXTURE_PATH.read_text())
    monkeypatch.setattr(ors_client.requests, "post", lambda *a, **kw: _FakeResponse(payload))

    result = ors_client.route_hgv([-95.37, 29.76], [-87.65, 41.85], api_key="fake-key")
    # Expected band for HOU->CHI via driving-hgv (see ors_test.py).
    assert 1000 < result.miles < 1200
    assert 15 < result.hours < 30


# --- live integration test (opt-in) -----------------------------------------


@pytest.mark.live_ors
@pytest.mark.skipif(
    not os.environ.get("ORS_LIVE"),
    reason="Live ORS test gated on ORS_LIVE=1 to protect the 2,000/day free tier quota",
)
def test_geocode_and_route_hgv_against_real_ors():
    from django.conf import settings
    api_key = settings.ORS_API_KEY
    assert api_key, "ORS_API_KEY must be set in app/.env"

    h = ors_client.geocode("Houston, TX", api_key=api_key)
    c = ors_client.geocode("Chicago, IL", api_key=api_key)
    assert "Houston" in h.label
    assert "Chicago" in c.label

    route = ors_client.route_hgv(h, c, api_key=api_key)
    assert 1000 < route.miles < 1200, f"unexpected mileage: {route.miles}"
    assert 15 < route.hours < 30, f"unexpected duration: {route.hours}"
