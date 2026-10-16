import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient
from app.main import app
from app.models import EvidenceStatus

@pytest.fixture
def client():
    return TestClient(app, raise_server_exceptions=False)

def test_01_health_endpoint_contract(client):
    """Verifies /health contract: status 200, operational metrics, connected DB."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["database"] == "connected"
    assert "active_articles_count" in data
    assert "chunks_count" in data
    assert isinstance(data["active_articles_count"], int)
    assert isinstance(data["chunks_count"], int)

def test_02_sync_status_endpoint_contract(client):
    """Verifies /api/v1/sync/status contract: status 200, schema keys."""
    response = client.get("/api/v1/sync/status")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert data["status"] in ["idle", "running", "completed", "failed"]
    assert "current_step" in data
    assert "pages_crawled" in data
    assert "total_sitemap_urls" in data

def test_03_ask_endpoint_contract(client):
    """Verifies /api/v1/ask contract: status 200, AskResponse schema."""
    payload = {
        "question": "Where can I configure Stripe payment gateway keys?",
        "category_filter": None,
        "history": []
    }
    response = client.post("/api/v1/ask", json=payload)
    assert response.status_code == 200
    data = response.json()
    
    # Contract schema validation
    assert "answer" in data
    assert "citations" in data
    assert "evidence_score" in data
    assert "confidence_score" in data  # Alias preserved
    assert "evidence_status" in data
    assert data["evidence_status"] in ["STRONG", "PARTIAL", "INSUFFICIENT", "NONE"]
    assert "is_known" in data
    assert "needs_human_review" in data
    assert "visual_references" in data
    assert isinstance(data["evidence_score"], (int, float))

def test_04_invalid_request_validation(client):
    """Verifies FastAPI request validation returns 422 for malformed payloads."""
    # Missing required 'question' field
    invalid_payload = {
        "bogus_field": "Not a valid AskRequest",
        "category_filter": 12345
    }
    response = client.post("/api/v1/ask", json=invalid_payload)
    assert response.status_code == 422
    data = response.json()
    assert "detail" in data
    errors = data["detail"]
    assert any("question" in str(err.get("loc", [])) for err in errors)

def test_05_simulated_model_api_failure(client):
    """Verifies that an unhandled downstream engine/model failure returns 500 error."""
    with patch("app.main.rag_engine.ask", side_effect=RuntimeError("Simulated LLM API outage")):
        payload = {"question": "How do I setup webhooks?"}
        response = client.post("/api/v1/ask", json=payload)
        assert response.status_code == 500
