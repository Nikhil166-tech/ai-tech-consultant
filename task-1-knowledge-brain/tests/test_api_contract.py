import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient
from app.main import app
from app.models import EvidenceStatus
from app.config import settings

@pytest.fixture
def client():
    return TestClient(app, raise_server_exceptions=False)

def test_01_health_endpoint_contract(client):
    """Verifies /health contract: status 200, operational metrics, connected DB, embedding status."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ["healthy", "degraded"]
    assert data["database"] == "connected"
    assert "active_articles_count" in data
    assert "chunks_count" in data
    assert "embedding" in data
    assert "daily_sync_enabled" in data
    assert "models" in data
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

def test_06_embedding_provider_health_status(client):
    """
    Requirement 3: Expose embedding provider status through /health.
    Learned embeddings must report provider, model, and healthy status.
    """
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    emb = data["embedding"]
    assert "provider" in emb
    assert "model" in emb
    assert "status" in emb
    assert "dimensions" in emb
    assert emb["status"] in ["healthy", "test_only"]

def test_07_degraded_embedding_status_reported_on_failure(client):
    """
    Requirement 3: When learned embeddings fail to initialize, /health must clearly
    report degraded status rather than silently presenting test embeddings as healthy.
    """
    mock_degraded_status = {
        "provider": "fastembed",
        "model": "failed_initialization",
        "status": "degraded",
        "dimensions": 128,
        "error": "FastEmbed initialization failed: Model checkpoint missing. Operating in degraded non-semantic fallback."
    }
    with patch("app.main.rag_engine.retriever.embedder.get_status", return_value=mock_degraded_status):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "degraded"
        assert data["embedding"]["status"] == "degraded"
        assert "Model checkpoint missing" in data["embedding"]["error"]

def test_08_active_model_defaults_in_health(client):
    """
    Requirement 1: Verify current active configurable models (claude-haiku-5-5 and claude-sonnet-5-5).
    """
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    models = data["models"]
    assert models["text"] == "claude-haiku-5-5"
    assert models["vision"] == "claude-sonnet-5-5"
    assert data["daily_sync_enabled"] == settings.enable_background_sync
