import time
import asyncio
from unittest.mock import patch
import httpx
from fastapi.testclient import TestClient
from app.orchestrator import PipelineOrchestrator, ProjectStore
from app.server import create_app
from app.models import CapabilityStatus, RequirementLifecycleStatus, Task1AskResponse, Task1Citation
from evals.task3_eval_suite import task3_eval_cases, Task3EvalCase


async def run_task3_evaluations():
    print("=========================================================================================================")
    print("                      BUSINESS LABS TASK 3 EVALUATION SUITE: MEETING-TO-SCOPE                            ")
    print("=========================================================================================================")

    total_cases = len(task3_eval_cases)
    extraction_passes = 0
    capability_passes = 0
    diff_passes = 0
    diff_applicable = 0
    estimate_passes = 0
    citation_passes = 0
    native_eval_count = 0
    approval_policy_passes = 0
    latencies = []

    for tc in task3_eval_cases:
        t0 = time.perf_counter()

        # Temporary in-memory store for isolation
        store = ProjectStore(filepath=f"data/eval_{tc.id}.json")
        orch = PipelineOrchestrator(store=store)

        # Handle mocked failure cases if specified
        if tc.simulate_task1_failure == "TIMEOUT":
            async def mock_timeout(*args, **kwargs):
                raise httpx.TimeoutException("Mocked Task 1 timeout")
            patcher = patch("httpx.AsyncClient.post", side_effect=mock_timeout)
            patcher.start()
        elif tc.simulate_task1_failure == "MALFORMED":
            class MockMalformedResp:
                status_code = 200
                def json(self): return {"corrupt": "data"}
            async def mock_malformed(*args, **kwargs):
                return MockMalformedResp()
            patcher = patch("httpx.AsyncClient.post", side_effect=mock_malformed)
            patcher.start()
        else:
            patcher = None

        try:
            proj_id = f"proj_{tc.id}"

            # 1. Process Initial Meeting
            scope = await orch.create_project_from_meeting(tc.transcript, project_id=proj_id)

            # 2. Process Follow-up Meeting if present
            changes = None
            if tc.follow_up_transcript:
                scope, changes = await orch.process_follow_up(proj_id, tc.follow_up_transcript)

            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            latencies.append(elapsed_ms)

            # --- 1. Extraction Quality Scoring ---
            has_goal = len(scope.client_goal.strip()) > 0
            if tc.scenario_type == "VAGUE_REQUEST":
                ext_ok = has_goal and len(scope.open_questions) > 0
            else:
                has_reqs = len(scope.requirements) > 0
                all_scope_titles = " ".join([r.title.lower() for r in scope.requirements])
                if changes:
                    all_scope_titles += " " + " ".join([r.title.lower() for r in changes.out_of_scope_requirements])

                contains_all = all(m.lower() in all_scope_titles for m in tc.must_contain_in_scope)
                excludes_all = all(m.lower() not in " ".join([r.title.lower() for r in scope.requirements]) for m in tc.must_not_contain)
                ext_ok = has_goal and has_reqs and contains_all and excludes_all

            # --- Context Keyword Assertions (Changed Budget, Deadline, Contradictory) ---
            if tc.expected_context_keywords:
                all_context_pieces = list(scope.assumptions + scope.risks + scope.open_questions + scope.decisions)
                for ch in scope.change_history:
                    if hasattr(ch, "diff_summary"):
                        all_context_pieces.append(ch.diff_summary)
                if changes:
                    all_context_pieces.append(changes.diff_summary)
                    for r in changes.changed_requirements + changes.removed_requirements + changes.out_of_scope_requirements:
                        if r.change_reason:
                            all_context_pieces.append(r.change_reason)
                        if r.description:
                            all_context_pieces.append(r.description)
                all_context_text = " ".join(all_context_pieces)
                context_ok = any(kw.lower() in all_context_text.lower() for kw in tc.expected_context_keywords)
                if not context_ok:
                    ext_ok = False

            if ext_ok:
                extraction_passes += 1

            # --- 2. Capability Decision Accuracy (NON-VACUOUS) ---
            if tc.expected_capabilities:
                cap_ok = True
                for match_key, expected_cap in tc.expected_capabilities.items():
                    # Must find the requirement
                    matching_req = next(
                        (r for r in scope.requirements if match_key.lower() in r.title.lower()),
                        None
                    )
                    if not matching_req:
                        cap_ok = False
                    elif matching_req.capability_status != expected_cap:
                        cap_ok = False

                if cap_ok:
                    capability_passes += 1
            else:
                capability_passes += 1

            # --- 3. Estimate Validity ---
            # Native must strictly have 0 hours.
            # Custom work must have custom hours > 0.
            # Unknown must contribute to discovery hours, NOT custom hours.
            est_ok = True
            for r in scope.requirements:
                if r.capability_status == CapabilityStatus.NATIVE:
                    if r.estimate and r.estimate.expected_hours > 0:
                        est_ok = False

            if tc.expected_has_custom_hours and scope.expected_custom_hours == 0:
                est_ok = False
            if not tc.expected_has_custom_hours and scope.expected_custom_hours > 0:
                est_ok = False
            if tc.expected_has_discovery_hours and scope.expected_discovery_hours == 0:
                est_ok = False

            if est_ok:
                estimate_passes += 1

            # --- 4. Citation Coverage on Expected Native Items ---
            for match_key, expected_cap in tc.expected_capabilities.items():
                if expected_cap == CapabilityStatus.NATIVE and not tc.simulate_task1_failure:
                    native_eval_count += 1
                    matching_req = next(
                        (r for r in scope.requirements if match_key.lower() in r.title.lower()),
                        None
                    )
                    if matching_req and len(matching_req.citations) > 0:
                        citation_passes += 1

            # --- 5. Scope Change-Diff Accuracy ---
            if tc.expected_diff_check:
                diff_applicable += 1
                if tc.expected_diff_check == "REMOVED" and changes:
                    if len(changes.removed_requirements) > 0:
                        diff_passes += 1
                elif tc.expected_diff_check == "NEW" and changes:
                    if len(changes.new_requirements) > 0:
                        diff_passes += 1
                elif tc.expected_diff_check == "CHANGED" and changes:
                    if len(changes.changed_requirements) > 0:
                        diff_passes += 1
                elif tc.expected_diff_check == "OUT_OF_SCOPE" and changes:
                    if len(changes.out_of_scope_requirements) > 0:
                        diff_passes += 1

            # --- 6. Human Approval Policy Compliance ---
            # A) Scope object must default to client_ready = False
            state_ok = (scope.client_ready is False and scope.approved_by is None)

            # B) API endpoint must strictly return HTTP 403 Forbidden before approval
            app = create_app(orch)
            test_client = TestClient(app)
            blocked_res = test_client.get(f"/api/v1/projects/{proj_id}/proposal")
            api_gating_ok = (blocked_res.status_code == 403)

            # C) Explicit human approval must transition client_ready = True
            appr_res = test_client.post(f"/api/v1/projects/{proj_id}/approve", json={"approved_by": "Eval Reviewer"})
            post_appr_ok = (appr_res.status_code == 200 and appr_res.json()["client_ready"] is True)

            # D) After approval, client proposal endpoint must return 200
            allowed_res = test_client.get(f"/api/v1/projects/{proj_id}/proposal")
            release_ok = (allowed_res.status_code == 200 and allowed_res.json()["client_ready"] is True)

            if state_ok and api_gating_ok and post_appr_ok and release_ok:
                approval_policy_passes += 1

        finally:
            if patcher:
                patcher.stop()

    avg_latency = sum(latencies) / len(latencies) if latencies else 0.0
    extraction_rate = (extraction_passes / total_cases) * 100.0
    capability_rate = (capability_passes / total_cases) * 100.0
    approval_rate = (approval_policy_passes / total_cases) * 100.0
    estimate_rate = (estimate_passes / total_cases) * 100.0
    diff_rate = (diff_passes / diff_applicable * 100.0) if diff_applicable > 0 else 100.0
    citation_rate = (citation_passes / native_eval_count * 100.0) if native_eval_count > 0 else 100.0

    print("\n=========================================================================================================")
    print("                               ACTUAL EMPIRICAL TASK 3 EVALUATION RESULTS                                ")
    print("=========================================================================================================")
    print(f"Total Held-Out Benchmark Cases: {total_cases}")
    print(f"- Requirement Extraction Quality:   {extraction_rate:.1f}% ({extraction_passes}/{total_cases})")
    print(f"- Native vs Custom Decision Acc:    {capability_rate:.1f}% ({capability_passes}/{total_cases})")
    print(f"- Scope Change-Diff Accuracy:       {diff_rate:.1f}% ({diff_passes}/{diff_applicable})")
    print(f"- Estimate Validity (Native=0h):    {estimate_rate:.1f}% ({estimate_passes}/{total_cases})")
    print(f"- Citation Coverage on Native:      {citation_rate:.1f}% ({citation_passes}/{native_eval_count})")
    print(f"- Human Approval Policy Compliance: {approval_rate:.1f}% ({approval_policy_passes}/{total_cases})")
    print(f"- Average Pipeline Latency:         {avg_latency:.1f}ms")
    print("=========================================================================================================\n")


if __name__ == "__main__":
    asyncio.run(run_task3_evaluations())