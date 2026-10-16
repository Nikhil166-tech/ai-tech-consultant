import pytest
import httpx
from unittest.mock import patch
from app.task1_client import Task1MeetingClient
from app.models import CapabilityStatus


@pytest.mark.asyncio
async def test_task1_timeout_handling():
    client = Task1MeetingClient(base_url="http://127.0.0.1:9999", timeout_seconds=0.01)

    async def mock_timeout(*args, **kwargs):
        raise httpx.TimeoutException("Connection timed out")

    with patch("httpx.AsyncClient.post", side_effect=mock_timeout):
        result = await client.query_capability("Stripe Gateway")
        assert result.success is False
        assert result.is_available is False
        assert result.inferred_capability == CapabilityStatus.UNKNOWN
        assert "timed out" in result.error_reason


@pytest.mark.asyncio
async def test_task1_unavailable_handling():
    client = Task1MeetingClient(base_url="http://127.0.0.1:9999", timeout_seconds=0.01)

    async def mock_conn_error(*args, **kwargs):
        raise httpx.ConnectError("Connection refused")

    with patch("httpx.AsyncClient.post", side_effect=mock_conn_error):
        result = await client.query_capability("Stripe Gateway")
        assert result.success is False
        assert result.is_available is False
        assert result.inferred_capability == CapabilityStatus.UNKNOWN
        assert "unavailable" in result.error_reason.lower()


@pytest.mark.asyncio
async def test_task1_malformed_response():
    client = Task1MeetingClient()

    class MockResponse:
        status_code = 200
        def json(self):
            # Missing required Task1AskResponse fields
            return {"corrupt": "data"}

    async def mock_post(*args, **kwargs):
        return MockResponse()

    with patch("httpx.AsyncClient.post", side_effect=mock_post):
        result = await client.query_capability("Custom Widget")
        assert result.success is False
        assert result.is_available is True
        assert result.inferred_capability == CapabilityStatus.UNKNOWN
        assert "failed schema validation" in result.error_reason


@pytest.mark.asyncio
async def test_task1_insufficient_evidence():
    client = Task1MeetingClient()

    class MockResponse:
        status_code = 200
        def json(self):
            return {
                "answer": "No verified documentation in Solution Center.",
                "citations": [],
                "evidence_score": 0.1,
                "evidence_status": "INSUFFICIENT",
                "is_known": False,
                "needs_human_review": True
            }

    async def mock_post(*args, **kwargs):
        return MockResponse()

    with patch("httpx.AsyncClient.post", side_effect=mock_post):
        result = await client.query_capability("Quantum teleportation module")
        assert result.success is True
        assert result.is_available is True
        # Must preserve uncertainty as UNKNOWN!
        assert result.inferred_capability == CapabilityStatus.UNKNOWN
        assert "insufficient verified documentation" in result.error_reason



@pytest.mark.asyncio
async def test_task1_needs_human_review_preserves_unknown():
    from app.agents.capability_checker import ProductCapabilityCheckerAgent
    from app.models import RequirementItem

    client = Task1MeetingClient()

    class MockResponse:
        status_code = 200
        def json(self):
            return {
                "answer": "Stripe is supported via Finance Settings.",
                "citations": [
                    {
                        "url": "https://support.brilliantdirectories.com/support/solutions/12000001520",
                        "title": "Payment Gateway Settings",
                        "category": "Finance",
                        "folder": "Finance",
                        "section_heading": "Payment Gateways",
                        "snippet": "Connect Stripe in Finance Settings to accept payments.",
                        "source_type": "OFFICIAL_DOC",
                        "provenance_notes": None,
                    }
                ],
                "evidence_score": 0.95,
                "evidence_status": "STRONG",
                "is_known": True,
                "needs_human_review": True,
            }

    async def mock_post(*args, **kwargs):
        return MockResponse()

    with patch("httpx.AsyncClient.post", side_effect=mock_post):
        # 1. Direct Task1MeetingClient query assertion
        result = await client.query_capability("Stripe Gateway")
        assert result.inferred_capability == CapabilityStatus.UNKNOWN
        assert result.error_reason is not None
        assert "human verification" in result.error_reason

        # 2. ProductCapabilityCheckerAgent pipeline assertion
        checker = ProductCapabilityCheckerAgent(task1_client=client, api_key=None)
        req = RequirementItem(
            id="REQ-01",
            title="Stripe Payment Processing",
            description="Accept credit card payments via Stripe gateway",
        )
        evaluated = await checker.evaluate_requirement(req)
        assert evaluated.capability_status == CapabilityStatus.UNKNOWN
        assert "human verification" in evaluated.native_alternative_notes
