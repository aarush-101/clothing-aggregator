"""HTTP surface: search, SSE, clicks, accounts, health and error handling."""

from __future__ import annotations

import json
from typing import Optional

import pytest

QUERY = "Find me a relaxed black linen shirt under $120 that ships to Sydney"


def read_sse(client, url: str, headers: Optional[dict] = None):
    """Read an SSE stream to completion and return parsed frames."""
    frames = []
    with client.stream("GET", url, headers=headers or {}) as response:
        assert response.status_code == 200
        event_name = None
        for line in response.iter_lines():
            if line.startswith("event: "):
                event_name = line[7:]
            elif line.startswith("data: "):
                frames.append((event_name, json.loads(line[6:])))
                if event_name == "search_completed":
                    break
    return frames


def run_search(client, query: str = QUERY):
    created = client.post("/api/search", json={"query": query})
    assert created.status_code == 202
    search_id = created.json()["search_id"]
    return search_id, read_sse(client, f"/api/search/{search_id}/events")


# --------------------------------------------------------------------------
# Health
# --------------------------------------------------------------------------


def test_liveness(api_client):
    body = api_client.get("/health").json()
    assert body["status"] == "ok"
    assert body["checks"]["connectors"] > 0


def test_readiness_reports_dependencies(api_client):
    body = api_client.get("/health/ready").json()
    assert body["status"] == "ok"
    assert body["checks"]["cache"] == "ok"
    assert body["checks"]["database"] == "ok"
    assert body["checks"]["query_parser"] == "deterministic"


def test_root_document(api_client):
    assert api_client.get("/").json()["name"] == "Clothing Aggregator API"


def test_openapi_schema_is_served(api_client):
    schema = api_client.get("/openapi.json").json()
    assert "/api/search" in schema["paths"]
    assert "/api/search/{search_id}/events" in schema["paths"]


# --------------------------------------------------------------------------
# Search creation and validation
# --------------------------------------------------------------------------


def test_create_search_returns_immediately_with_an_id(api_client):
    response = api_client.post("/api/search", json={"query": QUERY})
    assert response.status_code == 202
    body = response.json()
    assert body["search_id"]
    assert body["events_url"].endswith("/events")
    assert body["query"] == QUERY


@pytest.mark.parametrize(
    "payload",
    [
        {"query": ""},
        {"query": "   "},
        {"query": "x" * 5000},
        {},
        {"query": "shirt", "unexpected": True},
    ],
)
def test_invalid_search_payloads_are_rejected(api_client, payload):
    response = api_client.post("/api/search", json=payload)
    assert response.status_code == 422
    assert response.json()["error"] == "invalid_request"


def test_query_longer_than_the_configured_limit_is_rejected(api_client):
    response = api_client.post("/api/search", json={"query": "linen shirt " * 60})
    assert response.status_code == 422


def test_requests_carry_a_request_id_header(api_client):
    assert api_client.get("/health").headers.get("X-Request-ID")


# --------------------------------------------------------------------------
# Server-Sent Events
# --------------------------------------------------------------------------


def test_sse_stream_delivers_the_full_lifecycle(api_client):
    _, frames = run_search(api_client)
    names = [name for name, _ in frames]
    assert names[0] == "search_started"
    assert names[1] == "intent_parsed"
    assert frames[1][1]["parser"] == "deterministic"
    assert "retailer_started" in names
    assert "products_added" in names
    assert names[-1] == "search_completed"


def test_sse_frames_include_sequence_and_search_id(api_client):
    search_id, frames = run_search(api_client)
    for _, payload in frames:
        assert payload["search_id"] == search_id
        assert isinstance(payload["sequence"], int)


def test_sse_products_have_everything_the_ui_needs(api_client):
    _, frames = run_search(api_client)
    ranking = next(payload for name, payload in frames if name == "ranking_completed")
    assert ranking["groups"]
    primary = ranking["groups"][0]["primary"]
    for field in (
        "title",
        "brand",
        "retailer",
        "retailer_name",
        "product_url",
        "affiliate_url",
        "image_url",
        "price",
        "currency",
        "in_stock",
        "available_sizes",
        "match_score",
        "match_reasons",
        "retrieved_at",
    ):
        assert field in primary, f"missing {field}"


def test_sse_reconnect_with_last_event_id_replays_only_newer_events(api_client):
    search_id, frames = run_search(api_client)
    last = frames[2][1]["sequence"]
    replayed = read_sse(
        api_client, f"/api/search/{search_id}/events", headers={"Last-Event-ID": str(last)}
    )
    assert replayed
    assert all(payload["sequence"] > last for _, payload in replayed)


def test_sse_for_an_unknown_search_is_a_404(api_client):
    response = api_client.get("/api/search/does-not-exist/events")
    assert response.status_code == 404
    assert response.json()["error"] == "not_found"


def test_snapshot_endpoint_returns_the_completed_search(api_client):
    search_id, _ = run_search(api_client)
    snapshot = api_client.get(f"/api/search/{search_id}").json()
    assert snapshot["search_id"] == search_id
    assert snapshot["status"] in {"completed", "partial"}
    assert snapshot["groups"]
    assert snapshot["results_updated_at"]


def test_snapshot_for_an_unknown_search_is_a_404(api_client):
    assert api_client.get("/api/search/nope").status_code == 404


# --------------------------------------------------------------------------
# Retailers and ranking transparency
# --------------------------------------------------------------------------


def test_retailers_endpoint_lists_reviewed_websites(api_client):
    retailers = api_client.get("/api/retailers").json()
    assert retailers
    keys = {retailer["key"] for retailer in retailers}
    assert "assemblylabel" in keys
    assert sum(r["enabled"] for r in retailers) == 8
    assert all(retailer["requires_permission"] is False for retailer in retailers)


def test_retailers_endpoint_can_include_health(api_client):
    retailers = api_client.get("/api/retailers?include_health=true").json()
    assert all(retailer["healthy"] is not None for retailer in retailers)


def test_ranking_weights_are_published(api_client):
    body = api_client.get("/api/ranking").json()
    assert pytest.approx(sum(body["weights"].values()), abs=1e-9) == 1.0
    assert body["notes"]


# --------------------------------------------------------------------------
# Click tracking
# --------------------------------------------------------------------------


def test_click_is_recorded(api_client):
    response = api_client.post(
        "/api/clicks",
        json={
            "retailer": "northbound",
            "product_id": "northbound-ksl-lns-01",
            "destination_url": "https://northbound-supply.example/products/kessler-shirt",
            "price": 119.0,
            "currency": "AUD",
            "position": 1,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["recorded"] is True
    assert body["click_id"]


def test_click_rejects_an_unsafe_destination(api_client):
    response = api_client.post(
        "/api/clicks",
        json={
            "retailer": "x",
            "product_id": "1",
            "destination_url": "javascript:alert(1)",
        },
    )
    assert response.status_code == 422


# --------------------------------------------------------------------------
# Optional accounts
# --------------------------------------------------------------------------


def test_account_endpoints_require_a_token(api_client):
    assert api_client.get("/api/account/favourites").status_code == 401


def test_anonymous_session_enables_saved_searches_and_favourites(api_client):
    session = api_client.post("/api/auth/session")
    assert session.status_code == 201
    token = session.json()["token"]
    auth = {"Authorization": f"Bearer {token}"}

    saved = api_client.post(
        "/api/account/saved-searches", json={"query": QUERY, "label": "Linen shirts"}, headers=auth
    )
    assert saved.status_code == 201
    assert saved.json()["intent"]["colours"] == ["black"]

    listed = api_client.get("/api/account/saved-searches", headers=auth).json()
    assert len(listed) == 1

    favourite = api_client.post(
        "/api/account/favourites",
        json={
            "product": {
                "retailer": "northbound",
                "product_id": "p1",
                "title": "Kessler Relaxed Linen Shirt",
                "price": 119.0,
                "currency": "AUD",
            },
            "group_id": "g1",
        },
        headers=auth,
    )
    assert favourite.status_code == 201
    assert len(api_client.get("/api/account/favourites", headers=auth).json()) == 1

    assert (
        api_client.delete("/api/account/favourites/northbound/p1", headers=auth).status_code == 204
    )
    assert api_client.get("/api/account/favourites", headers=auth).json() == []

    assert (
        api_client.delete(
            f"/api/account/saved-searches/{listed[0]['id']}", headers=auth
        ).status_code
        == 204
    )


def test_an_invalid_token_is_treated_as_anonymous(api_client):
    response = api_client.get(
        "/api/account/favourites", headers={"Authorization": "Bearer nonsense"}
    )
    assert response.status_code == 401


def test_saving_the_same_search_twice_is_idempotent(api_client):
    token = api_client.post("/api/auth/session").json()["token"]
    auth = {"Authorization": f"Bearer {token}"}
    api_client.post("/api/account/saved-searches", json={"query": QUERY}, headers=auth)
    api_client.post("/api/account/saved-searches", json={"query": QUERY}, headers=auth)
    assert len(api_client.get("/api/account/saved-searches", headers=auth).json()) == 1


# --------------------------------------------------------------------------
# Rate limiting
# --------------------------------------------------------------------------


def test_search_rate_limit_returns_429_when_exceeded(monkeypatch, api_client):
    context = api_client.app.state.context
    monkeypatch.setattr(context.settings, "rate_limit_enabled", True)
    monkeypatch.setattr(context.settings, "rate_limit_searches_per_minute", 2)

    statuses = [
        api_client.post("/api/search", json={"query": f"linen shirt {i}"}).status_code
        for i in range(4)
    ]
    assert 429 in statuses
    limited = api_client.post("/api/search", json={"query": "another shirt"})
    assert limited.status_code == 429
    assert limited.json()["error"] == "rate_limited"
    assert limited.headers.get("Retry-After")


def test_health_is_exempt_from_rate_limiting(monkeypatch, api_client):
    context = api_client.app.state.context
    monkeypatch.setattr(context.settings, "rate_limit_enabled", True)
    monkeypatch.setattr(context.settings, "rate_limit_requests_per_minute", 1)
    for _ in range(5):
        assert api_client.get("/health").status_code == 200


# --------------------------------------------------------------------------
# CORS
# --------------------------------------------------------------------------


def test_cors_allows_the_configured_origin(api_client):
    response = api_client.options(
        "/api/search",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"


def test_cors_rejects_an_unknown_origin(api_client):
    response = api_client.options(
        "/api/search",
        headers={
            "Origin": "https://evil.example",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert response.headers.get("access-control-allow-origin") is None
