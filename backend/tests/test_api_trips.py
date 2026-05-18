"""
DRF integration tests for the /api/trips/ endpoint.

All tests mock ORS via monkeypatch — the API contract is what's under test,
not the routing client.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from rest_framework.test import APIClient

from trips import ors_client
from trips.ors_client import ORSError
from trips.services import trip_builder


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "ors_route_houston_chicago.geojson"


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def mock_ors_success(monkeypatch):
    fixture = json.loads(FIXTURE_PATH.read_text())

    def fake_geocode(text, api_key, **kw):
        if "Houston" in text:
            return ors_client.GeocodeResult(label="Houston, TX, USA", lng=-95.3698, lat=29.7604)
        if "Chicago" in text:
            return ors_client.GeocodeResult(label="Chicago, IL, USA", lng=-87.6298, lat=41.8781)
        # Default (e.g. "Dallas, TX") returns Houston-area coords so the
        # deadhead leg is skipped — keeps these envelope-shape tests focused
        # on the single-leg-routing case. Deadhead-specific API tests live
        # in test_api_trips_deadhead.py.
        return ors_client.GeocodeResult(label=text, lng=-95.3698, lat=29.7604)

    def fake_route_hgv(src, dst, api_key, **kw):
        return ors_client.RouteResult(miles=1088.0, hours=24.0, geojson=fixture)

    monkeypatch.setattr(trip_builder, "geocode", fake_geocode)
    monkeypatch.setattr(trip_builder, "route_hgv", fake_route_hgv)


@pytest.fixture
def mock_ors_failure(monkeypatch):
    def fake_geocode(text, api_key, **kw):
        raise ORSError("upstream blew up", status=503, body="Service Unavailable")

    monkeypatch.setattr(trip_builder, "geocode", fake_geocode)


# --- happy path ------------------------------------------------------------


@pytest.mark.django_db
def test_post_trips_returns_201_with_full_envelope(client, mock_ors_success):
    resp = client.post(
        "/api/trips/",
        data={
            "current_location": "Dallas, TX",
            "pickup_location": "Houston, TX",
            "dropoff_location": "Chicago, IL",
            "current_cycle_used_hrs": 20.0,
        },
        format="json",
    )
    assert resp.status_code == 201, resp.content
    body = resp.json()
    # Envelope keys present
    for key in (
        "id", "current_location", "pickup_location", "dropoff_location",
        "current_cycle_used_hrs", "start_at", "end_at", "total_miles",
        "total_drive_hours", "is_legal", "cycle_used_at_end",
        "not_legal_reason", "route_geometry", "stops", "log_days",
    ):
        assert key in body, f"missing key: {key}"
    assert body["is_legal"] is True
    assert float(body["total_miles"]) == pytest.approx(1088.0)
    assert float(body["cycle_used_at_end"]) == pytest.approx(46.25, abs=0.5)
    assert len(body["stops"]) >= 5
    assert len(body["log_days"]) == 3
    # Nested entries present
    assert all(isinstance(d["entries"], list) and len(d["entries"]) >= 1 for d in body["log_days"])


@pytest.mark.django_db
def test_post_trips_persists_and_get_returns_same_envelope(client, mock_ors_success):
    create = client.post(
        "/api/trips/",
        data={
            "current_location": "Dallas, TX",
            "pickup_location": "Houston, TX",
            "dropoff_location": "Chicago, IL",
            "current_cycle_used_hrs": 20.0,
        },
        format="json",
    )
    trip_id = create.json()["id"]
    get = client.get(f"/api/trips/{trip_id}/")
    assert get.status_code == 200
    assert get.json()["id"] == trip_id
    assert get.json()["is_legal"] is True


# --- illegal-trip path -----------------------------------------------------


@pytest.mark.django_db
def test_post_trips_illegal_trip_returns_201_with_no_log_days(client, mock_ors_success):
    """Resolved Q3: not-legal trip persists, returns summary + stops, no log_days."""
    resp = client.post(
        "/api/trips/",
        data={
            "current_location": "Dallas, TX",
            "pickup_location": "Houston, TX",
            "dropoff_location": "Chicago, IL",
            "current_cycle_used_hrs": 65.0,
        },
        format="json",
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["is_legal"] is False
    assert body["not_legal_reason"]
    assert body["log_days"] == []
    assert len(body["stops"]) >= 1   # at least PICKUP


# --- validation ------------------------------------------------------------


@pytest.mark.django_db
def test_post_trips_validation_missing_field_returns_400(client, mock_ors_success):
    resp = client.post(
        "/api/trips/",
        data={
            "current_location": "Dallas, TX",
            "pickup_location": "Houston, TX",
            # dropoff missing
            "current_cycle_used_hrs": 20.0,
        },
        format="json",
    )
    assert resp.status_code == 400
    assert "dropoff_location" in resp.json()


@pytest.mark.django_db
def test_post_trips_validation_cycle_out_of_range_returns_400(client, mock_ors_success):
    resp = client.post(
        "/api/trips/",
        data={
            "current_location": "Dallas, TX",
            "pickup_location": "Houston, TX",
            "dropoff_location": "Chicago, IL",
            "current_cycle_used_hrs": 99.0,
        },
        format="json",
    )
    assert resp.status_code == 400
    assert "current_cycle_used_hrs" in resp.json()


# --- ORS failure → 502 -----------------------------------------------------


@pytest.mark.django_db
def test_post_trips_ors_failure_returns_502(client, mock_ors_failure):
    """Resolved Q4: hard-fail with HTTP 502 + clear message. No silent fallbacks."""
    resp = client.post(
        "/api/trips/",
        data={
            "current_location": "Dallas, TX",
            "pickup_location": "Houston, TX",
            "dropoff_location": "Chicago, IL",
            "current_cycle_used_hrs": 20.0,
        },
        format="json",
    )
    assert resp.status_code == 502
    body = resp.json()
    assert body["detail"] == "Routing service unavailable"
    assert body["upstream_status"] == 503
    assert "upstream_message" in body


# --- GET nonexistent -------------------------------------------------------


@pytest.mark.django_db
def test_get_trips_404_for_missing_id(client):
    resp = client.get("/api/trips/99999/")
    assert resp.status_code == 404
