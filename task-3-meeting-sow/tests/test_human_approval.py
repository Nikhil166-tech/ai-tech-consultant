import pytest
from app.orchestrator import PipelineOrchestrator, ProjectStore


@pytest.fixture
def clean_store(tmp_path):
    store_file = str(tmp_path / "test_approval_store.json")
    return ProjectStore(store_file)


@pytest.mark.asyncio
async def test_human_approval_lifecycle(clean_store):
    orch = PipelineOrchestrator(store=clean_store)

    transcript = "Client: We need Stripe payment processing and recurring monthly billing."
    scope = await orch.create_project_from_meeting(transcript, project_id="proj_appr_01")

    # 1. Draft scope must strictly default to client_ready = False
    assert scope.client_ready is False
    assert scope.approved_by is None
    assert scope.approved_at is None

    # 2. Reject blank/invalid approver
    with pytest.raises(ValueError):
        orch.approve_scope("proj_appr_01", approved_by="")

    # 3. Valid human approval
    approved_scope = orch.approve_scope("proj_appr_01", approved_by="senior_consultant_dave")
    assert approved_scope.client_ready is True
    assert approved_scope.approved_by == "senior_consultant_dave"
    assert approved_scope.approved_at is not None

    # 4. Follow-up meeting resets client_ready to False
    followup_transcript = "Client: In follow-up, please also enable Google Analytics 4."
    scope_v2, _ = await orch.process_follow_up("proj_appr_01", followup_transcript)
    assert scope_v2.client_ready is False
