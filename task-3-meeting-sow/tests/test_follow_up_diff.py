import os
import pytest
from app.orchestrator import PipelineOrchestrator, ProjectStore
from app.models import RequirementLifecycleStatus, CapabilityStatus


@pytest.fixture
def clean_store(tmp_path):
    store_file = str(tmp_path / "test_project_store.json")
    return ProjectStore(store_file)


@pytest.mark.asyncio
async def test_follow_up_diff_classification(clean_store):
    orch = PipelineOrchestrator(store=clean_store)

    # Meeting 1: Initial Discovery
    m1_transcript = (
        "Sarah: Our goal is to build an online attorney portal.\n"
        "We need Stripe payment processing, recurring monthly billing, and a custom CRM integration with HubSpot."
    )
    scope_v1 = await orch.create_project_from_meeting(m1_transcript, project_id="proj_apex_01")

    assert scope_v1.version == 1
    assert scope_v1.meeting_count == 1
    initial_titles = [r.title for r in scope_v1.requirements]
    assert any("Stripe" in t for t in initial_titles)
    assert any("CRM" in t for t in initial_titles)
    assert scope_v1.expected_total_hours > 0  # CRM custom work has hours

    # Meeting 2: Follow-up Scope Change
    # Canceling CRM integration, adding claimable business listings
    m2_transcript = (
        "Sarah: In this follow-up, we are canceling the custom CRM integration for phase 1.\n"
        "Instead, we are adding claimable business listings for imported law firms."
    )
    scope_v2, changes = await orch.process_follow_up("proj_apex_01", m2_transcript)

    assert scope_v2.version == 2
    assert scope_v2.meeting_count == 2

    # Check change set
    removed_titles = [r.title for r in changes.removed_requirements]
    assert any("CRM" in t for t in removed_titles)

    new_titles = [r.title for r in changes.new_requirements]
    assert any("Claimable" in t for t in new_titles)

    unchanged_titles = [r.title for r in changes.unchanged_requirements]
    assert any("Stripe" in t for t in unchanged_titles)

    # Since CRM was removed and Claimable is native (0h), total custom hours dropped!
    assert scope_v2.expected_total_hours < scope_v1.expected_total_hours
    assert scope_v2.client_ready is False  # Must reset to unapproved on change
