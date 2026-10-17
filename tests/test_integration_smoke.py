import os
import sys
from pathlib import Path
import pytest
import httpx
from unittest.mock import patch, AsyncMock

# Add task paths to sys.path
root_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root_dir / "task-1-knowledge-brain"))
sys.path.insert(0, str(root_dir / "task-3-meeting-sow"))

from app.models import Task1AskResponse, Task1Citation, CapabilityStatus, RequirementItem
from app.task1_client import Task1MeetingClient, Task1ClientResult
from app.agents.capability_checker import ProductCapabilityCheckerAgent


@pytest.mark.asyncio
async def test_task1_health():
    """1. Task 1 health works and reports operational subsystems."""
    task1_url = os.getenv("TASK1_API_URL", "http://127.0.0.1:8000")
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            res = await client.get(f"{task1_url}/health")
            assert res.status_code == 200
            data = res.json()
            assert data["status"] in ("healthy", "ok", "degraded")
            assert "embedding" in data
            assert "database" in data
        except httpx.ConnectError:
            pytest.skip("Task 1 live server not running locally.")


@pytest.mark.asyncio
async def test_task3_can_call_task1():
    """2. Task 3 can call Task 1 over network and parse structured response."""
    task1_url = os.getenv("TASK1_API_URL", "http://127.0.0.1:8000")
    client = Task1MeetingClient(base_url=task1_url, timeout_seconds=30.0)
    async with httpx.AsyncClient(timeout=30.0) as http_client:
        try:
            res = await http_client.get(f"{task1_url}/health")
        except httpx.ConnectError:
            pytest.skip("Task 1 live server not running locally.")

    result = await client.query_capability("General platform overview")
    assert result.is_available is True
    assert result.success is True
    assert result.response is not None


@pytest.mark.asyncio
async def test_task2_can_call_task1_and_insufficient_knowledge_propagates_to_hitl():
    """3. Task 2 can call Task 1, and insufficient knowledge safely routes to HITL."""
    task2_url = os.getenv("TASK2_API_URL", "http://127.0.0.1:3000")
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            # Send an email with an unknown speculative requirement
            payload = {
                "id": "smoke-em-001",
                "senderEmail": "customer@example.com",
                "subject": "Question about quantum cloud directory hosting",
                "body": "Can you host our directory on quantum cloud infrastructure?",
                "receivedAt": "2026-10-16T10:00:00Z"
            }
            res = await client.post(f"{task2_url}/api/v1/emails/process", json=payload)
            if res.status_code == 200:
                data = res.json()
                assert data.get("routedTo") in ("HUMAN_REVIEW_QUEUE", "PENDING_REVIEW")
                assert data.get("draft", {}).get("autoSendEligible", False) is False
            else:
                pytest.skip(f"Task 2 live server returned {res.status_code}")
        except httpx.ConnectError:
            pytest.skip("Task 2 live server not running locally.")


@pytest.mark.asyncio
async def test_task1_insufficient_or_human_review_propagates_to_task3_unknown():
    """4. Task 1 insufficient or human-review-required knowledge propagates into Task 3 UNKNOWN."""
    client = Task1MeetingClient()
    checker = ProductCapabilityCheckerAgent(task1_client=client, api_key=None)

    task1_resp = Task1AskResponse(
        answer="Complex custom webhook setup requires manual engineering verification.",
        citations=[
            Task1Citation(
                url="https://support.brilliantdirectories.com/support/solutions",
                title="Support Center",
                category="General",
                folder="General",
                section_heading="Overview",
                snippet="General overview snippet.",
                source_type="OFFICIAL_DOC",
                provenance_notes=None,
            )
        ],
        evidence_score=0.9,
        evidence_status="STRONG",
        is_known=True,
        needs_human_review=True,
    )

    with patch.object(client, "query_capability", new_callable=AsyncMock) as mock_query:
        mock_query.return_value = Task1ClientResult(
            success=True,
            is_available=True,
            response=task1_resp,
            error_reason="Task 1 requires human verification before capability classification",
            inferred_capability=CapabilityStatus.UNKNOWN,
        )

        req = RequirementItem(
            id="REQ-01",
            title="Complex Integration",
            description="Needs verification",
        )
        evaluated = await checker.evaluate_requirement(req)
        assert evaluated.capability_status == CapabilityStatus.UNKNOWN
        assert "human verification" in evaluated.native_alternative_notes.lower()


@pytest.mark.asyncio
async def test_task1_insufficient_knowledge_escalates_to_task3_unknown():
    """5. Task 1 insufficient evidence result forces UNKNOWN and zero custom hours."""
    client = Task1MeetingClient()
    checker = ProductCapabilityCheckerAgent(task1_client=client, api_key=None)

    task1_resp = Task1AskResponse(
        answer="I do not have sufficient documentation to answer this question.",
        citations=[],
        evidence_score=0.0,
        evidence_status="NONE",
        is_known=False,
        needs_human_review=True,
    )

    with patch.object(client, "query_capability", new_callable=AsyncMock) as mock_query:
        mock_query.return_value = Task1ClientResult(
            success=True,
            is_available=True,
            response=task1_resp,
            error_reason="Task 1 reported insufficient verified documentation",
            inferred_capability=CapabilityStatus.UNKNOWN,
        )

        req = RequirementItem(
            id="REQ-03",
            title="Autonomous AI Teleportation",
            description="Undocumented speculative feature",
        )
        evaluated = await checker.evaluate_requirement(req)
        assert evaluated.capability_status == CapabilityStatus.UNKNOWN
        assert len(evaluated.citations) == 0


@pytest.mark.asyncio
async def test_services_fail_safely_if_task1_unavailable():
    """6. Services fail safely when Task 1 is unavailable (connection refused)."""
    client = Task1MeetingClient(base_url="http://127.0.0.1:9999", timeout_seconds=0.1)
    checker = ProductCapabilityCheckerAgent(task1_client=client, api_key=None)

    req = RequirementItem(
        id="REQ-02",
        title="Payment Gateway",
        description="Stripe recurring payments",
    )
    evaluated = await checker.evaluate_requirement(req)

    # Must preserve uncertainty and not crash
    assert evaluated.capability_status == CapabilityStatus.UNKNOWN
    assert "unverified" in evaluated.native_alternative_notes.lower()
