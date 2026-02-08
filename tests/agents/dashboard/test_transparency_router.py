"""API tests for transparency router."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from agents.dashboard.transparency_router import router


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_transparency_status_endpoint():
    client = _client()
    response = client.get("/transparency/status")
    assert response.status_code == 200
    payload = response.json()
    assert "counts" in payload
    assert payload["counts"]["facts"] >= 1


def test_transparency_fact_endpoint():
    client = _client()
    response = client.get("/transparency/facts/fact-2025-10-25-ap-election-001")
    assert response.status_code == 200
    payload = response.json()
    assert payload["fact"]["fact_id"] == "fact-2025-10-25-ap-election-001"
    assert payload["evidence"]
