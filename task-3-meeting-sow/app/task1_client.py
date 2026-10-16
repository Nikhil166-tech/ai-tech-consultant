import os
import httpx
from pydantic import ValidationError
from app.models import Task1AskResponse, CapabilityStatus


class Task1ClientResult:
    def __init__(
        self,
        success: bool,
        is_available: bool,
        response: Task1AskResponse | None = None,
        error_reason: str | None = None,
        inferred_capability: CapabilityStatus = CapabilityStatus.UNKNOWN,
    ):
        self.success = success
        self.is_available = is_available
        self.response = response
        self.error_reason = error_reason
        self.inferred_capability = inferred_capability


class Task1MeetingClient:
    """
    Typed async HTTP REST client for querying the Task 1 Knowledge Brain.
    Handles timeout, connection failures, malformed payloads, and insufficient evidence.
    Task 1 is the ONLY source of truth for Brilliant Directories product capabilities.
    """

    def __init__(self, base_url: str | None = None, timeout_seconds: float = 5.0):
        self.base_url = (base_url or os.getenv("TASK1_API_URL") or "http://127.0.0.1:8000").rstrip("/")
        self.timeout_seconds = timeout_seconds

    async def query_capability(self, feature_query: str) -> Task1ClientResult:
        url = f"{self.base_url}/api/v1/ask"
        payload = {
            "question": feature_query,
            "category_filter": None,
            "history": [],
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                res = await client.post(url, json=payload)

            if res.status_code != 200:
                return Task1ClientResult(
                    success=False,
                    is_available=False,
                    error_reason=f"Task 1 returned HTTP {res.status_code}",
                    inferred_capability=CapabilityStatus.UNKNOWN,
                )

            raw_data = res.json()
            try:
                task1_data = Task1AskResponse.model_validate(raw_data)
            except ValidationError as ve:
                return Task1ClientResult(
                    success=False,
                    is_available=True,
                    error_reason=f"Task 1 response failed schema validation: {ve}",
                    inferred_capability=CapabilityStatus.UNKNOWN,
                )

            # Check if Task 1 indicates insufficient evidence or lack of verified articles
            if not task1_data.is_known or task1_data.evidence_status in ("INSUFFICIENT", "NONE"):
                return Task1ClientResult(
                    success=True,
                    is_available=True,
                    response=task1_data,
                    error_reason="Task 1 reported insufficient verified documentation",
                    inferred_capability=CapabilityStatus.UNKNOWN,
                )

            if task1_data.needs_human_review:
                return Task1ClientResult(
                    success=True,
                    is_available=True,
                    response=task1_data,
                    error_reason="Task 1 requires human verification before capability classification",
                    inferred_capability=CapabilityStatus.UNKNOWN,
                )

            return Task1ClientResult(
                success=True,
                is_available=True,
                response=task1_data,
                inferred_capability=CapabilityStatus.UNKNOWN,
            )

        except httpx.TimeoutException:
            return Task1ClientResult(
                success=False,
                is_available=False,
                error_reason=f"Task 1 request timed out after {self.timeout_seconds}s",
                inferred_capability=CapabilityStatus.UNKNOWN,
            )
        except httpx.RequestError as req_err:
            return Task1ClientResult(
                success=False,
                is_available=False,
                error_reason=f"Task 1 Knowledge Brain unavailable: {req_err}",
                inferred_capability=CapabilityStatus.UNKNOWN,
            )