import pytest
from app.models import RequirementItem, CapabilityStatus, RequirementLifecycleStatus, Task1AskResponse, Task1Citation
from app.agents.requirements_analyst import RequirementsAnalystAgent
from app.agents.capability_checker import ProductCapabilityCheckerAgent
from app.agents.technical_estimator import TechnicalEstimatorAgent
from app.agents.proposal_writer import ProposalWriterAgent
from app.models import ProjectScope


@pytest.mark.asyncio
async def test_requirements_analyst_extraction():
    analyst = RequirementsAnalystAgent()
    transcript = (
        "Client: Our goal is to launch a nationwide healthcare provider directory.\n"
        "We need Stripe payment processing for member tiers, and a custom CRM integration with HubSpot."
    )
    result = await analyst.analyze_transcript(transcript)

    assert "healthcare" in result["client_goal"].lower()
    req_titles = [r.title for r in result["requirements"]]
    assert any("Stripe" in t for t in req_titles)
    assert any("CRM" in t for t in req_titles)
    assert len(result["assumptions"]) > 0
    assert len(result["out_of_scope"]) > 0


@pytest.mark.asyncio
async def test_capability_checker_native_vs_custom():
    class MockTask1Client:
        async def query_capability(self, query: str):
            class MockResult:
                success = True
                is_available = True
                inferred_capability = CapabilityStatus.NATIVE
                error_reason = None
                response = Task1AskResponse(
                    answer="Configure Stripe in Finance > Payment Gateways.",
                    citations=[
                        Task1Citation(
                            url="https://support.bd.com/stripe",
                            title="Finance Gateways",
                            section_heading="Credentials Setup",
                            snippet="Enter Stripe credentials."
                        )
                    ],
                    evidence_score=0.9,
                    evidence_status="STRONG",
                    is_known=True,
                    needs_human_review=False
                )
            return MockResult()

    checker = ProductCapabilityCheckerAgent(task1_client=MockTask1Client())

    native_req = RequirementItem(id="REQ-01", title="Stripe Payment Processing", description="Accept credit cards via Stripe")
    custom_req = RequirementItem(id="REQ-02", title="Custom CRM Integration", description="Sync member profiles to HubSpot CRM")

    evaluated_native = await checker.evaluate_requirement(native_req)
    evaluated_custom = await checker.evaluate_requirement(custom_req)

    assert evaluated_native.capability_status == CapabilityStatus.NATIVE
    assert "0" in evaluated_native.native_alternative_notes or "native" in evaluated_native.native_alternative_notes.lower()
    assert len(evaluated_native.citations) > 0

    assert evaluated_custom.capability_status == CapabilityStatus.CUSTOM


def test_technical_estimator_native_gets_zero_hours():
    estimator = TechnicalEstimatorAgent()

    native_req = RequirementItem(
        id="REQ-01",
        title="Stripe Setup",
        description="Configure Stripe keys",
        capability_status=CapabilityStatus.NATIVE
    )

    custom_req = RequirementItem(
        id="REQ-02",
        title="Custom CRM Integration",
        description="Sync to HubSpot",
        capability_status=CapabilityStatus.CUSTOM
    )

    est_native = estimator.estimate_requirement(native_req)
    est_custom = estimator.estimate_requirement(custom_req)

    # Native configuration must receive strictly 0 custom hours
    assert est_native.estimate.optimistic_hours == 0.0
    assert est_native.estimate.most_likely_hours == 0.0
    assert est_native.estimate.pessimistic_hours == 0.0
    assert est_native.estimate.expected_hours == 0.0

    # Custom integration receives 3-point estimate
    assert est_custom.estimate.optimistic_hours > 0
    assert est_custom.estimate.pessimistic_hours >= est_custom.estimate.most_likely_hours
    assert len(est_custom.estimate.assumptions) > 0
    assert len(est_custom.estimate.technical_risks) > 0


def test_proposal_writer_defaults_to_not_client_ready():
    writer = ProposalWriterAgent()
    scope = ProjectScope(
        project_id="test_01",
        client_goal="Launch medical directory",
        client_ready=False
    )
    sow_markdown = writer.generate_sow(scope)

    assert "# Statement of Work" in sow_markdown
    assert "DRAFT (Internal Review)" in sow_markdown
    assert scope.client_ready is False
