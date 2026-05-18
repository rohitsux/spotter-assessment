"""
Tests for the /api/geocode/ autocomplete endpoint.

All tests stub ors_client.requests so no real ORS quota is consumed.
"""

from __future__ import annotations

import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from trips import ors_client
from trips.ors_client import ORSError


@pytest.fixture(autouse=True)
def _clear_cache():
    """Every geocode test starts with a cold cache so call-count assertions
    are deterministic."""
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def client():
    return APIClient()


class _FakeResp:
    def __init__(self, payload, *, status=200, text=""):
        self._payload = payload
        self.status_code = status
        self.text = text

    @property
    def ok(self):
        return 200 <= self.status_code < 300

    def json(self):
        return self._payload


# --- happy path ------------------------------------------------------------


def test_geocode_returns_5_suggestions(client, monkeypatch):
    payload = {
        "features": [
            {"geometry": {"coordinates": [-95.37, 29.76]}, "properties": {"label": "Houston, TX, USA"}},
            {"geometry": {"coordinates": [-95.21, 29.55]}, "properties": {"label": "Houston Hobby, TX"}},
            {"geometry": {"coordinates": [-92.31, 38.81]}, "properties": {"label": "Houston, MO"}},
        ]
    }
    monkeypatch.setattr(ors_client.requests, "get", lambda *a, **kw: _FakeResp(payload))

    resp = client.get("/api/geocode/", {"text": "Houston"})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["results"]) == 3
    assert body["results"][0]["label"].startswith("Houston, TX")
    assert "lng" in body["results"][0] and "lat" in body["results"][0]


def test_geocode_empty_results_returns_200(client, monkeypatch):
    monkeypatch.setattr(ors_client.requests, "get", lambda *a, **kw: _FakeResp({"features": []}))
    resp = client.get("/api/geocode/", {"text": "Atlantis"})
    assert resp.status_code == 200
    assert resp.json() == {"results": []}


# --- input guards ---------------------------------------------------------


def test_geocode_missing_text_returns_empty_results_no_upstream_call(client, monkeypatch):
    called = []
    monkeypatch.setattr(ors_client.requests, "get", lambda *a, **kw: called.append(1) or _FakeResp({}))

    resp = client.get("/api/geocode/")
    assert resp.status_code == 200
    assert resp.json() == {"results": []}
    assert called == [], "ORS should not be called for missing text"


def test_geocode_short_query_does_not_hit_upstream(client, monkeypatch):
    """Single-char queries waste quota and are useless for autocomplete."""
    called = []
    monkeypatch.setattr(ors_client.requests, "get", lambda *a, **kw: called.append(1) or _FakeResp({}))

    resp = client.get("/api/geocode/", {"text": "H"})
    assert resp.status_code == 200
    assert resp.json() == {"results": []}
    assert called == []


# --- caching --------------------------------------------------------------


def test_repeat_query_hits_cache_no_second_upstream_call(client, monkeypatch):
    """The second call for the same text must NOT hit ORS."""
    call_count = {"n": 0}
    payload = {
        "features": [
            {"geometry": {"coordinates": [-95.37, 29.76]}, "properties": {"label": "Houston, TX, USA"}},
        ]
    }
    def counted_get(*a, **kw):
        call_count["n"] += 1
        return _FakeResp(payload)
    monkeypatch.setattr(ors_client.requests, "get", counted_get)

    r1 = client.get("/api/geocode/", {"text": "Houston"})
    r2 = client.get("/api/geocode/", {"text": "Houston"})
    r3 = client.get("/api/geocode/", {"text": "Houston"})
    assert r1.status_code == r2.status_code == r3.status_code == 200
    assert r1.json() == r2.json() == r3.json()
    assert call_count["n"] == 1, f"expected 1 upstream call, got {call_count['n']}"


def test_cache_key_is_case_insensitive(client, monkeypatch):
    """`Houston`, `houston`, ` HOUSTON ` all share one cache entry."""
    call_count = {"n": 0}
    def counted_get(*a, **kw):
        call_count["n"] += 1
        return _FakeResp({"features": []})
    monkeypatch.setattr(ors_client.requests, "get", counted_get)

    client.get("/api/geocode/", {"text": "Houston"})
    client.get("/api/geocode/", {"text": "houston"})
    client.get("/api/geocode/", {"text": "  HOUSTON  "})
    assert call_count["n"] == 1


def test_different_queries_do_not_share_cache(client, monkeypatch):
    call_count = {"n": 0}
    def counted_get(*a, **kw):
        call_count["n"] += 1
        return _FakeResp({"features": []})
    monkeypatch.setattr(ors_client.requests, "get", counted_get)

    client.get("/api/geocode/", {"text": "Houston"})
    client.get("/api/geocode/", {"text": "Dallas"})
    client.get("/api/geocode/", {"text": "Chicago"})
    assert call_count["n"] == 3


# --- ORS failure → 502 ---------------------------------------------------


def test_geocode_upstream_failure_returns_502(client, monkeypatch):
    """The view binds `autocomplete` into its own namespace, so the patch
    must target trips.views.autocomplete, not ors_client.autocomplete."""
    from trips import views

    def boom(*a, **kw):
        raise ORSError("upstream blew up", status=503, body="Service Unavailable")
    monkeypatch.setattr(views, "autocomplete", boom)

    resp = client.get("/api/geocode/", {"text": "Houston"})
    assert resp.status_code == 502
    body = resp.json()
    assert "temporarily unavailable" in body["detail"].lower()
    assert "upstream_status" not in body
    assert "upstream_message" not in body


# --- autocomplete client (separate from view) ----------------------------


def test_autocomplete_client_parses_features(monkeypatch):
    payload = {
        "features": [
            {"geometry": {"coordinates": [-95.37, 29.76]}, "properties": {"label": "Houston, TX, USA"}},
            {"geometry": {"coordinates": [-95.21, 29.55]}, "properties": {"label": "Houston Hobby, TX"}},
        ]
    }
    monkeypatch.setattr(ors_client.requests, "get", lambda *a, **kw: _FakeResp(payload))

    results = ors_client.autocomplete("Houston", api_key="fake")
    assert len(results) == 2
    assert results[0].label == "Houston, TX, USA"
    assert results[0].lng == pytest.approx(-95.37)
    assert results[0].lat == pytest.approx(29.76)


def test_autocomplete_client_empty_features_returns_empty_list(monkeypatch):
    monkeypatch.setattr(ors_client.requests, "get", lambda *a, **kw: _FakeResp({"features": []}))
    assert ors_client.autocomplete("Atlantis", api_key="fake") == []


def test_autocomplete_client_raises_on_http_error(monkeypatch):
    monkeypatch.setattr(ors_client.requests, "get", lambda *a, **kw: _FakeResp({}, status=429, text="rate limit"))
    with pytest.raises(ORSError) as exc:
        ors_client.autocomplete("Houston", api_key="fake")
    assert exc.value.status == 429


def test_autocomplete_client_raises_when_api_key_missing():
    with pytest.raises(ORSError, match="not configured"):
        ors_client.autocomplete("Houston", api_key="")
