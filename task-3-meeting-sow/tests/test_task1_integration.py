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
