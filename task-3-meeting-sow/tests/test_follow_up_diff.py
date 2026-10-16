import pytest
from app.orchestrator import PipelineOrchestrator, ProjectStore
from app.models import RequirementLifecycleStatus, CapabilityStatus, RequirementItem


@pytest.mark.asyncio
async def test_follow_up_stable_ids_over_multiple_meetings():
    store = ProjectStore(filepath="data/test_store_multi.json")
    orch = PipelineOrchestrator(store=store)

    # Meeting 1: Initial Discovery
    m1_transcript = "Client: We need Stripe payment processing and location radius search."
    scope1 = await orch.create_project_from_meeting(m1_transcript, project_id="proj_multi_m")

    req_ids_m1 = [r.id for r in scope1.requirements]
    assert "REQ-01" in req_ids_m1
    assert "REQ-02" in req_ids_m1

    # Meeting 2: Adds automated welcome emails
    m2_transcript = "Client: We also want automated welcome email templates sent upon registration."
    scope2, changes2 = await orch.process_follow_up("proj_multi_m", m2_transcript)

    req_ids_m2 = [r.id for r in scope2.requirements]
    # Check that new requirement received REQ-03 (strictly after max existing REQ-02)
    assert "REQ-03" in req_ids_m2
    # Ensure existing requirements kept their stable IDs
    assert "REQ-01" in req_ids_m2
    assert "REQ-02" in req_ids_m2
    assert len(set(req_ids_m2)) == len(req_ids_m2)  # Zero collisions

    # Meeting 3: Adds data export to CSV
    m3_transcript = "Client: We also need data export to CSV for monthly audits."
    scope3, changes3 = await orch.process_follow_up("proj_multi_m", m3_transcript)

    req_ids_m3 = [r.id for r in scope3.requirements]
    assert "REQ-04" in req_ids_m3
    assert len(set(req_ids_m3)) == len(req_ids_m3)  # Zero collisions
    assert req_ids_m3 == ["REQ-01", "REQ-02", "REQ-03", "REQ-04"]


@pytest.mark.asyncio
async def test_follow_up_five_lifecycle_states():
    store = ProjectStore(filepath="data/test_store_states.json")
    orch = PipelineOrchestrator(store=store)

    # Initial Meeting with:
    # 1. Stripe Payment Processing
    # 2. Custom Mobile App Wrapper
    # 3. Custom CRM Integration
    # 4. Accounting ERP Integration
    # 5. Member Verified Badges
    init_transcript = (
        "Client: We need Stripe payment processing for billing, "
        "custom mobile app wrapper, "
        "custom CRM integration with HubSpot, "
        "accounting ERP integration, "
        "and member verified badges."
    )
    scope1 = await orch.create_project_from_meeting(init_transcript, project_id="proj_states")
    assert len(scope1.requirements) >= 4

    # Follow-up:
    # - REMOVE mobile app ("we are canceling the custom mobile app")
    # - OUT_OF_SCOPE for accounting ("accounting ERP integration is out of scope / deferred to phase 2")
    # - CHANGE CRM sync ("HubSpot CRM sync should now only send new members one-way")
    # - NEW requirement ("add claimable business listings")
    # - UNCHANGED (Stripe, Badges)
    follow_up_transcript = (
        "Client: We have several scope changes today.\n"
        "First, we are canceling the custom mobile app wrapper.\n"
        "Second, accounting ERP integration is out of scope for phase 1 and deferred to phase 2.\n"
        "Third, for HubSpot CRM sync, make it one-way only instead of two-way.\n"
        "Fourth, we want to add claimable business listings with email claim verification."
    )
    scope2, change_set = await orch.process_follow_up("proj_states", follow_up_transcript)

    # Verify all 5 states are populated in change_set
    assert len(change_set.removed_requirements) > 0
    assert any("mobile" in r.title.lower() for r in change_set.removed_requirements)

    assert len(change_set.out_of_scope_requirements) > 0
    assert any("accounting" in r.title.lower() or "erp" in r.title.lower() for r in change_set.out_of_scope_requirements)

    assert len(change_set.changed_requirements) > 0
    changed_crm = next(r for r in change_set.changed_requirements if "crm" in r.title.lower())
    assert changed_crm.status == RequirementLifecycleStatus.CHANGED
    assert "one-way" in changed_crm.description.lower() or "modified" in changed_crm.change_reason.lower()

    assert len(change_set.new_requirements) > 0
    assert any("claimable" in r.title.lower() for r in change_set.new_requirements)

    assert len(change_set.unchanged_requirements) > 0
    assert any("stripe" in r.title.lower() for r in change_set.unchanged_requirements)

    # Verify diff summary displays all five counts
    assert "Out of Scope:" in change_set.diff_summary
    assert "New:" in change_set.diff_summary
    assert "Changed:" in change_set.diff_summary
    assert "Unchanged:" in change_set.diff_summary
    assert "Removed:" in change_set.diff_summary


@pytest.mark.asyncio
async def test_context_and_open_questions_preserved_across_meetings():
    store = ProjectStore(filepath="data/test_store_ctx.json")
    orch = PipelineOrchestrator(store=store)

    scope1 = await orch.create_project_from_meeting(
        "Client: We need Stripe payment processing. Target launch is November.",
        project_id="proj_ctx"
    )
    assert len(scope1.assumptions) > 0
    orig_assumptions = list(scope1.assumptions)

    # Follow-up
    scope2, _ = await orch.process_follow_up(
        "proj_ctx",
        "Client: We also need data export to CSV. We will provide marketing materials next week."
    )

    # Verify assumptions are accumulated
    for a in orig_assumptions:
        assert a in scope2.assumptions

    # Verify version history snapshot
    assert len(scope2.version_history) == 1
    assert scope2.version_history[0]["version"] == 1

    # Verify decisions history
    assert len(scope2.decisions) >= 2

@pytest.mark.asyncio
async def test_changed_acceptance_criteria_preserved_in_follow_up():
    """Item 2 & 5: Verifies that follow-up changes to requirements (e.g. 'one-way only and new members')
    are preserved in the updated requirement description and change metadata rather than
    overwritten with generic boilerplate, and version_history preserves full schema."""
    store = ProjectStore(filepath="data/test_changed_criteria.json")
    orch = PipelineOrchestrator(store=store)

    # Initial meeting
    init_transcript = "Client: We need custom CRM integration to synchronize contacts to HubSpot."
    scope1 = await orch.create_project_from_meeting(init_transcript, project_id="proj_criteria")
    assert any("crm" in r.title.lower() for r in scope1.requirements)

    # Follow-up with specific constraint modification
    follow_up_transcript = "Client: CRM sync should now only send new members one-way."
    scope2, change_set = await orch.process_follow_up("proj_criteria", follow_up_transcript)

    crm_req = next(r for r in scope2.requirements if "crm" in r.title.lower())
    assert crm_req.status == RequirementLifecycleStatus.CHANGED

    # Must preserve actual changed acceptance criteria
    combined_text = f"{crm_req.description} {crm_req.change_reason}".lower()
    assert "one-way" in combined_text, f"Expected 'one-way' in updated requirement, got: {combined_text}"
    assert "new members" in combined_text or "only send" in combined_text, (
        f"Expected 'new members' constraint in updated requirement, got: {combined_text}"
    )

    # Verify version_history snapshot preserved all required fields (Item 5)
    assert len(scope2.version_history) == 1
    prior_snap = scope2.version_history[0]
    assert "requirements" in prior_snap
    assert len(prior_snap["requirements"]) > 0
    assert prior_snap["requirements"][0]["id"] == "REQ-01"
    assert "title" in prior_snap["requirements"][0]
    assert "description" in prior_snap["requirements"][0]
    assert "capability_status" in prior_snap["requirements"][0]
    assert "open_questions" in prior_snap
    assert "assumptions" in prior_snap
    assert "custom_total_hours" in prior_snap
    assert "discovery_total_hours" in prior_snap
    assert "approval_state" in prior_snap


@pytest.mark.asyncio
async def test_follow_up_explicit_unchanged_lifecycle():
    """Exact failing scenario:
    Initial requirements:
    - REQ-01 Stripe Payment Processing
    - REQ-02 Recurring Subscription Billing
    - REQ-03 Location Radius Search
    - REQ-04 Custom CRM Integration
    Follow-up transcript:
    'Change the HubSpot CRM integration from bidirectional synchronization to one-way synchronization for new members only. Remove the 25-mile radius search requirement from phase 1. Keep Stripe subscription billing unchanged.'
    Required result:
    - Stripe Payment Processing = UNCHANGED
    - Recurring Subscription Billing = UNCHANGED
    - Custom CRM Integration = CHANGED
    - Location Radius Search = REMOVED
    Diff summary:
    - New: 0, Changed: 1, Unchanged: 2, Removed: 1, Out of Scope: 0
    """
    store = ProjectStore(filepath="data/test_store_exact_unchanged.json")
    orch = PipelineOrchestrator(store=store)

    init_transcript = (
        "Client: We need Stripe payment processing to accept credit cards for memberships, "
        "recurring monthly subscription billing, "
        "location radius search within 25 miles of zip code, "
        "and custom CRM integration to synchronize contacts to HubSpot."
    )
    scope1 = await orch.create_project_from_meeting(init_transcript, project_id="proj_exact_lifecycle")
    assert len(scope1.requirements) == 4

    stripe_m1 = next(r for r in scope1.requirements if "stripe" in r.title.lower() and "payment" in r.title.lower())
    billing_m1 = next(r for r in scope1.requirements if "recurring" in r.title.lower() or "subscription" in r.title.lower())
    radius_m1 = next(r for r in scope1.requirements if "radius" in r.title.lower())
    crm_m1 = next(r for r in scope1.requirements if "crm" in r.title.lower())

    follow_up_transcript = (
        "Change the HubSpot CRM integration from bidirectional synchronization to one-way synchronization for new members only. "
        "Remove the 25-mile radius search requirement from phase 1. "
        "Keep Stripe subscription billing unchanged."
    )
    scope2, change_set = await orch.process_follow_up("proj_exact_lifecycle", follow_up_transcript)

    # 1. Check exact required lifecycle statuses
    stripe_m2 = next(r for r in change_set.unchanged_requirements if r.id == stripe_m1.id)
    assert stripe_m2.status == RequirementLifecycleStatus.UNCHANGED
    assert stripe_m2.description == stripe_m1.description
    assert stripe_m2.capability_status == stripe_m1.capability_status
    assert stripe_m2.estimate is not None
    assert stripe_m2.estimate.expected_hours == stripe_m1.estimate.expected_hours

    billing_m2 = next(r for r in change_set.unchanged_requirements if r.id == billing_m1.id)
    assert billing_m2.status == RequirementLifecycleStatus.UNCHANGED
    assert billing_m2.description == billing_m1.description
    assert billing_m2.capability_status == billing_m1.capability_status
    assert billing_m2.estimate is not None
    assert billing_m2.estimate.expected_hours == billing_m1.estimate.expected_hours

    crm_m2 = next(r for r in change_set.changed_requirements if r.id == crm_m1.id)
    assert crm_m2.status == RequirementLifecycleStatus.CHANGED
    assert "one-way" in crm_m2.description.lower() or "one-way" in crm_m2.change_reason.lower()

    radius_m2 = next(r for r in change_set.removed_requirements if r.id == radius_m1.id)
    assert radius_m2.status == RequirementLifecycleStatus.REMOVED

    # 2. Check exact required diff counts
    assert len(change_set.new_requirements) == 0
    assert len(change_set.changed_requirements) == 1
    assert len(change_set.unchanged_requirements) == 2
    assert len(change_set.removed_requirements) == 1
    assert len(change_set.out_of_scope_requirements) == 0

    # 3. Check diff summary text
    assert "- New: 0" in change_set.diff_summary
    assert "- Changed: 1" in change_set.diff_summary
    assert "- Unchanged: 2" in change_set.diff_summary
    assert "- Removed: 1" in change_set.diff_summary
    assert "- Out of Scope: 0" in change_set.diff_summary


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "follow_up_phrase",
    [
        "Keep Stripe payment processing unchanged.",
        "Stripe payment processing stays unchanged.",
        "No change to Stripe payment processing.",
        "Leave Stripe payment processing as is.",
    ],
)
async def test_follow_up_explicit_unchanged_semantics_phrases(follow_up_phrase):
    """Verifies all explicit unchanged phrasing patterns:
    - 'keep X unchanged'
    - 'X stays unchanged'
    - 'no change to X'
    - 'leave X as is'
    """
    store = ProjectStore(filepath=f"data/test_store_phrase_{abs(hash(follow_up_phrase))}.json")
    orch = PipelineOrchestrator(store=store)

    scope1 = await orch.create_project_from_meeting(
        "Client: We need Stripe payment processing for credit cards and custom CRM integration with HubSpot.",
        project_id=f"proj_ph_{abs(hash(follow_up_phrase))}",
    )
    stripe_m1 = next(r for r in scope1.requirements if "stripe" in r.title.lower())

    follow_up = f"Client: For HubSpot CRM integration, make it one-way only. {follow_up_phrase}"
    scope2, change_set = await orch.process_follow_up(f"proj_ph_{abs(hash(follow_up_phrase))}", follow_up)

    stripe_m2 = next(r for r in change_set.unchanged_requirements if r.id == stripe_m1.id)
    assert stripe_m2.status == RequirementLifecycleStatus.UNCHANGED
    assert stripe_m2.description == stripe_m1.description
    assert stripe_m2.id == stripe_m1.id

