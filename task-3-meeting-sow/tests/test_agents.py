import pytest
from unittest.mock import patch, AsyncMock
from app.agents.requirements_analyst import RequirementsAnalystAgent
from app.agents.capability_checker import ProductCapabilityCheckerAgent
from app.agents.technical_estimator import TechnicalEstimatorAgent
from app.agents.proposal_writer import ProposalWriterAgent
from app.models import (
    RequirementItem,
    CapabilityStatus,
    RequirementLifecycleStatus,
    ProjectScope,
    Task1AskResponse,
    Task1Citation,
)
from app.task1_client import Task1MeetingClient, Task1ClientResult


@pytest.mark.asyncio
async def test_requirements_analyst_claude_structured_output():
    analyst = RequirementsAnalystAgent(api_key="mock_key")

    mock_claude_response = {
        "content": [{
            "text": (
                '{\n'
                '  "client_goal": "Launch modern attorney directory platform",\n'
                '  "requirements": [\n'
                '    {"title": "Stripe Payments", "description": "Recurring attorney memberships via Stripe", "category": "FINANCE"}\n'
                '  ],\n'
                '  "assumptions": ["Client provides credentials"],\n'
                '  "open_questions": ["Launch timeline?"],\n'
                '  "risks": ["API limits"],\n'
                '  "out_of_scope": ["Dispute mediation"]\n'
                '}'
            )
        }]
    }

    class MockResp:
        status_code = 200
        def json(self): return mock_claude_response

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = MockResp()
        result = await analyst.analyze_transcript("Client wants Stripe billing.")

    assert result["client_goal"] == "Launch modern attorney directory platform"
    assert len(result["requirements"]) == 1
    req = result["requirements"][0]
    assert isinstance(req, RequirementItem)
    assert req.id == "REQ-01"
    assert req.title == "Stripe Payments"


@pytest.mark.asyncio
async def test_requirements_analyst_malformed_claude_fallback():
    analyst = RequirementsAnalystAgent(api_key="mock_key")

    class MockMalformedResp:
        status_code = 200
        def json(self): return {"content": [{"text": "Sorry, I cannot process this."}]}

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = MockMalformedResp()
        # Should gracefully fall back to deterministic extraction without raising exception
        result = await analyst.analyze_transcript("Client: We need Stripe payment processing for members.")

    assert "Stripe" in result["client_goal"] or len(result["requirements"]) > 0
    assert any("stripe" in r.title.lower() for r in result["requirements"])
    assert all(isinstance(r, RequirementItem) for r in result["requirements"])


@pytest.mark.asyncio
async def test_capability_checker_zero_knowledge_duplication():
    """Verifies ProductCapabilityCheckerAgent relies strictly on Task 1 evidence without local knowledge."""
    client = Task1MeetingClient()
    checker = ProductCapabilityCheckerAgent(task1_client=client)

    # Mock Task 1 response confirming native feature
    task1_resp = Task1AskResponse(
        answer="Stripe payment gateway is available natively out-of-the-box in Brilliant Directories via Finance > Payment Gateways.",
        citations=[
            Task1Citation(
                url="https://support.brilliantdirectories.com/stripe",
                title="Stripe Setup",
                section_heading="How to Connect Stripe",
                snippet="How to connect Stripe in admin portal",
            )
        ],
        evidence_score=0.95,
        evidence_status="STRONG",
        is_known=True,
        needs_human_review=False,
    )

    with patch.object(client, "query_capability", new_callable=AsyncMock) as mock_query:
        mock_query.return_value = Task1ClientResult(
            success=True, is_available=True, response=task1_resp
        )
        req = RequirementItem(
            id="REQ-01",
            title="Stripe Payment Processing",
            description="Process credit cards via Stripe",
        )
        evaluated = await checker.evaluate_requirement(req)

    assert evaluated.capability_status == CapabilityStatus.NATIVE
    assert len(evaluated.citations) == 1
    assert "0 in custom development" in evaluated.native_alternative_notes or "Natively supported" in evaluated.native_alternative_notes


@pytest.mark.asyncio
async def test_capability_checker_partial_native_plus_custom():
    client = Task1MeetingClient()
    checker = ProductCapabilityCheckerAgent(task1_client=client)

    # Task 1 confirms member badges exist natively
    task1_resp = Task1AskResponse(
        answer="Member badges are a built-in feature in Brilliant Directories settings.",
        citations=[
            Task1Citation(
                url="https://support.brilliantdirectories.com/badges",
                title="Member Badges",
                section_heading="Overview of Badges",
                snippet="Configure badges in admin",
            )
        ],
        is_known=True,
        evidence_status="STRONG",
        needs_human_review=False,
    )

    with patch.object(client, "query_capability", new_callable=AsyncMock) as mock_query:
        mock_query.return_value = Task1ClientResult(success=True, is_available=True, response=task1_resp)
        # Client requests native badges WITH custom CSS animation styling
        req = RequirementItem(
            id="REQ-03",
            title="Member Verified Badges",
            description="Display verified badges on cards plus custom CSS animation styling.",
        )
        evaluated = await checker.evaluate_requirement(req)

    assert evaluated.capability_status == CapabilityStatus.PARTIAL
    assert "custom styling" in evaluated.native_alternative_notes.lower()


@pytest.mark.asyncio
async def test_capability_checker_ambiguous_evidence_yields_unknown():
    client = Task1MeetingClient()
    checker = ProductCapabilityCheckerAgent(task1_client=client)

    # Task 1 response is ambiguous/unclear
    task1_resp = Task1AskResponse(
        answer="I don't have enough verified information about custom quantum encryption modules in Brilliant Directories.",
        citations=[],
        is_known=False,
        evidence_status="INSUFFICIENT",
    )

    with patch.object(client, "query_capability", new_callable=AsyncMock) as mock_query:
        mock_query.return_value = Task1ClientResult(success=True, is_available=True, response=task1_resp)
        req = RequirementItem(
            id="REQ-04",
            title="Quantum Encryption",
            description="Proprietary encryption module",
        )
        evaluated = await checker.evaluate_requirement(req)

    assert evaluated.capability_status == CapabilityStatus.UNKNOWN


@pytest.mark.asyncio
async def test_capability_checker_external_sounding_name_with_ambiguous_evidence_yields_unknown():
    """Item 1: Requirement name sounds like an external/custom integration,
    but Task 1 evidence is ambiguous; result MUST be UNKNOWN, not CUSTOM."""
    client = Task1MeetingClient()
    checker = ProductCapabilityCheckerAgent(task1_client=client)

    # Ambiguous overview citation that does NOT document the feature nor Developer Hub
    task1_resp = Task1AskResponse(
        answer="Based on Brilliant Directories 'What Do You Need Help With?' (Overview): Solutions home. Get Started Here.",
        citations=[
            Task1Citation(
                url="https://support.brilliantdirectories.com/support/home",
                title="What Do You Need Help With?",
                category="General",
                folder="Overview",
                section_heading="Overview",
                snippet="General overview of directory portal setup.",
                source_type="article",
            )
        ],
        is_known=True,
        evidence_status="PARTIAL",
    )

    with patch.object(client, "query_capability", new_callable=AsyncMock) as mock_query:
        mock_query.return_value = Task1ClientResult(success=True, is_available=True, response=task1_resp)
        req = RequirementItem(
            id="REQ-05",
            title="Custom External CRM Integration",
            description="Sync member records to external CRM platform",
        )
        evaluated = await checker.evaluate_requirement(req)

    assert evaluated.capability_status == CapabilityStatus.UNKNOWN, (
        f"Expected UNKNOWN for ambiguous evidence without verified documentation, but got {evaluated.capability_status}"
    )


def test_technical_estimator_hours_separation():
    estimator = TechnicalEstimatorAgent()

    native_req = RequirementItem(
        id="REQ-01",
        title="Stripe Payment Processing",
        description="Native Stripe configuration",
        capability_status=CapabilityStatus.NATIVE,
    )
    custom_req = RequirementItem(
        id="REQ-02",
        title="Custom CRM Integration",
        description="Sync members to HubSpot",
        capability_status=CapabilityStatus.CUSTOM,
    )
    partial_req = RequirementItem(
        id="REQ-03",
        title="Member Verified Badges",
        description="Native badges with custom CSS animation",
        capability_status=CapabilityStatus.PARTIAL,
    )
    unknown_req = RequirementItem(
        id="REQ-04",
        title="AI Voice Search Widget",
        description="Unverified capability",
        capability_status=CapabilityStatus.UNKNOWN,
    )

    estimated = estimator.estimate_all([native_req, custom_req, partial_req, unknown_req])

    # 1. Native must strictly have 0 hours
    assert estimated[0].estimate.expected_hours == 0.0

    # 2. Compute totals
    custom_range, exp_custom, disc_range, exp_disc = estimator.compute_total_hours(estimated)

    # Confirmed custom dev must include custom and partial only
    assert exp_custom > 0.0
    assert custom_range[0] > 0.0

    # UNKNOWN feasibility spike must be strictly separated into discovery hours
    assert exp_disc > 0.0
    assert disc_range[0] > 0.0

    # Custom hours must NOT include the UNKNOWN hours
    assert exp_custom == round(estimated[1].estimate.expected_hours + estimated[2].estimate.expected_hours, 1)


def test_proposal_writer_defaults_to_not_client_ready():
    writer = ProposalWriterAgent()
    scope = ProjectScope(
        project_id="proj_test",
        version=1,
        client_goal="Launch legal directory",
        requirements=[],
        client_ready=False,
    )
    sow = writer.generate_sow(scope)
    assert "NOT CLIENT-READY" in sow
    assert "PENDING HUMAN APPROVAL" in sow