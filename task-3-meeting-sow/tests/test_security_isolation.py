import os
import pytest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient
from app.server import create_app
from app.orchestrator import PipelineOrchestrator, ProjectStore
from app.models import ProjectScope, CapabilityStatus, RequirementItem


@pytest.fixture
def test_client(tmp_path):
    store_path = str(tmp_path / "test_sec_store.json")
    store = ProjectStore(filepath=store_path)
    orch = PipelineOrchestrator(store=store)
    app = create_app(orchestrator=orch)
    client = TestClient(app)
    return client, orch, store


def test_invalid_internal_service_key_rejected(test_client):
    client, _, _ = test_client
    resp = client.get("/api/v1/projects/any_proj/scope", headers={"X-Internal-Service-Key": "spoofed_key_12345"})
    assert resp.status_code == 401
    assert "Invalid internal service key" in resp.json()["detail"]


def test_production_mode_unauthenticated_rejected(test_client):
    client, _, _ = test_client
    with patch.dict(os.environ, {"ENVIRONMENT": "production"}):
        resp = client.get("/api/v1/projects/any_proj/scope")
        assert resp.status_code == 401
        assert "Authentication required" in resp.json()["detail"]


def test_cross_user_project_isolation(test_client):
    client, orch, store = test_client
    app = client.app
    from app.server import get_current_user_or_service

    # User A owns proj_alpha
    scope_a = ProjectScope(
        project_id="proj_alpha",
        user_id="user_alice_123",
        client_goal="Alice goal",
        requirements=[
            RequirementItem(id="REQ-01", title="Payment Gateway", description="Stripe setup", category="FINANCE")
        ]
    )
    store.save(scope_a)

    try:
        # 1. User Alice accesses her own project
        app.dependency_overrides[get_current_user_or_service] = lambda: {"id": "user_alice_123", "role": "user", "email": "alice@example.com"}
        resp_alice = client.get("/api/v1/projects/proj_alpha/scope")
        assert resp_alice.status_code == 200
        assert resp_alice.json()["project_id"] == "proj_alpha"

        # 2. User Bob attempts to access Alice's project -> REJECTED 403 FORBIDDEN
        app.dependency_overrides[get_current_user_or_service] = lambda: {"id": "user_bob_456", "role": "user", "email": "bob@example.com"}
        resp_bob = client.get("/api/v1/projects/proj_alpha/scope")
        assert resp_bob.status_code == 403
        assert "belongs to another user account" in resp_bob.json()["detail"]

        # 3. User Bob attempts to mutate (approve) Alice's project -> REJECTED 403 FORBIDDEN
        resp_bob_approve = client.post("/api/v1/projects/proj_alpha/approve", json={"approved_by": "Bob"})
        assert resp_bob_approve.status_code == 403
        assert "belongs to another user account" in resp_bob_approve.json()["detail"]

        # 4. Internal service key can access for orchestrating background jobs
        app.dependency_overrides[get_current_user_or_service] = lambda: {"id": "service_internal", "role": "service"}
        resp_service = client.get("/api/v1/projects/proj_alpha/scope")
        assert resp_service.status_code == 200
    finally:
        app.dependency_overrides.clear()
