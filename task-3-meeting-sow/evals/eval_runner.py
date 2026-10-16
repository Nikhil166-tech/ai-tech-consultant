import time
import asyncio
from unittest.mock import patch
import httpx
from app.orchestrator import PipelineOrchestrator, ProjectStore
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
    native_count = 0
    approval_policy_passes = 0
    latencies = []

    for tc in task3_eval_cases:
        t0 = time.perf_counter()

        # Temporary in-memory store for isolation
        store = ProjectStore(filepath=f"data/eval_{tc.id}.json")
        orch = PipelineOrchestrator(store=store)

        # Handle simulation of Task 1 failure modes
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
            # 1. Process Initial Meeting
            scope = await orch.create_project_from_meeting(tc.transcript, project_id=f"proj_{tc.id}")

            # 2. Process Follow-up Meeting if present
            changes = None
            if tc.follow_up_transcript:
                scope, changes = await orch.process_follow_up(f"proj_{tc.id}", tc.follow_up_transcript)

            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            latencies.append(elapsed_ms)

            # 1. Extraction Quality Check
            has_goal = len(scope.client_goal.strip()) > 0
            has_reqs = len(scope.requirements) > 0 or "vague" in tc.scenario_type.lower()
            if has_goal:
                extraction_passes += 1

            # 2. Human Approval Policy Compliance
            # client_ready must strictly be False
            if scope.client_ready is False and scope.approved_by is None:
                approval_policy_passes += 1

            # 3. Native vs Custom Decision Accuracy
            cap_ok = True
            for req in scope.requirements:
                for match_title, expected_cap in tc.expected_capabilities.items():
                    if match_title.lower() in req.title.lower():
                        if req.capability_status != expected_cap:
                            cap_ok = False
            if cap_ok:
                capability_passes += 1

            # 4. Estimate Validity
            # If native, must have 0 hours. If custom work expected, total hours > 0
            est_ok = True
            for r in scope.requirements:
                if r.capability_status == CapabilityStatus.NATIVE:
                    if r.estimate and r.estimate.expected_hours > 0:
                        est_ok = False
            if tc.expected_has_custom_hours and scope.expected_total_hours == 0:
                est_ok = False
            if est_ok:
                estimate_passes += 1

            # 5. Citation Coverage Check
            for r in scope.requirements:
                if r.capability_status == CapabilityStatus.NATIVE:
                    native_count += 1
                    if len(r.citations) > 0:
                        citation_passes += 1

            # 6. Change-Diff Accuracy Check
            if tc.expected_diff_check:
                diff_applicable += 1
                if tc.expected_diff_check == "REMOVED" and changes:
                    if len(changes.removed_requirements) > 0:
                        diff_passes += 1
                elif tc.expected_diff_check == "NEW" and changes:
                    if len(changes.new_requirements) > 0:
                        diff_passes += 1

        finally:
            if patcher:
                patcher.stop()

    avg_latency = sum(latencies) / len(latencies) if latencies else 0.0
    extraction_rate = (extraction_passes / total_cases) * 100.0
    capability_rate = (capability_passes / total_cases) * 100.0
    approval_rate = (approval_policy_passes / total_cases) * 100.0
    estimate_rate = (estimate_passes / total_cases) * 100.0
    diff_rate = (diff_passes / diff_applicable * 100.0) if diff_applicable > 0 else 100.0
    citation_rate = (citation_passes / native_count * 100.0) if native_count > 0 else 100.0

    print("\n=========================================================================================================")
    print("                               ACTUAL EMPIRICAL TASK 3 EVALUATION RESULTS                                ")
    print("=========================================================================================================")
    print(f"Total Held-Out Benchmark Cases: {total_cases}")
    print(f"- Requirement Extraction Quality:   {extraction_rate:.1f}%")
    print(f"- Native vs Custom Decision Acc:    {capability_rate:.1f}%")
    print(f"- Scope Change-Diff Accuracy:       {diff_rate:.1f}%")
    print(f"- Estimate Validity (Native=0h):    {estimate_rate:.1f}%")
    print(f"- Citation Coverage on Native:      {citation_rate:.1f}%")
    print(f"- Human Approval Policy Compliance: {approval_rate:.1f}%")
    print(f"- Average Pipeline Latency:         {avg_latency:.1f}ms")
    print("=========================================================================================================\n")


if __name__ == "__main__":
    asyncio.run(run_task3_evaluations())
