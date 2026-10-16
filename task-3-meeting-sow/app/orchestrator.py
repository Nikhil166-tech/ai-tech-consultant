import re
import os
import json
import uuid
from datetime import datetime, timezone
from app.models import (
    ProjectScope,
    RequirementItem,
    RequirementLifecycleStatus,
    ScopeChangeSet,
    Task1Citation,
)
from app.agents.requirements_analyst import RequirementsAnalystAgent
from app.agents.capability_checker import ProductCapabilityCheckerAgent
from app.agents.technical_estimator import TechnicalEstimatorAgent
from app.agents.proposal_writer import ProposalWriterAgent


class ProjectStore:
    def __init__(self, filepath: str | None = None):
        self.filepath = filepath or os.path.join(os.getcwd(), "data", "project_store.json")
        self._projects: dict[str, ProjectScope] = {}
        self.load()

    def get(self, project_id: str) -> ProjectScope | None:
        return self._projects.get(project_id)

    def save(self, scope: ProjectScope) -> None:
        self._projects[scope.project_id] = scope
        self.persist()

    def list_all(self) -> list[ProjectScope]:
        return list(self._projects.values())

    def load(self) -> None:
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._projects = {
                        k: ProjectScope.model_validate(v) for k, v in data.items()
                    }
            except Exception as err:
                print(f"Warning: could not load project store from {self.filepath}: {err}")

    def persist(self) -> None:
        os.makedirs(os.path.dirname(self.filepath), exist_ok=True)
        try:
            with open(self.filepath, "w", encoding="utf-8") as f:
                serializable = {
                    k: v.model_dump(mode="json") for k, v in self._projects.items()
                }
                json.dump(serializable, f, indent=2, default=str)
        except Exception as err:
            print(f"Error persisting project store: {err}")


class PipelineOrchestrator:
    """
    Coordinates the multi-agent Meeting-to-Scope pipeline and manages
    multi-meeting project history and diffing.
    """

    def __init__(
        self,
        analyst: RequirementsAnalystAgent | None = None,
        checker: ProductCapabilityCheckerAgent | None = None,
        estimator: TechnicalEstimatorAgent | None = None,
        writer: ProposalWriterAgent | None = None,
        store: ProjectStore | None = None,
    ):
        self.analyst = analyst or RequirementsAnalystAgent()
        self.checker = checker or ProductCapabilityCheckerAgent()
        self.estimator = estimator or TechnicalEstimatorAgent()
        self.writer = writer or ProposalWriterAgent()
        self.store = store or ProjectStore()

    async def create_project_from_meeting(
        self, transcript: str, project_id: str | None = None
    ) -> ProjectScope:
        pid = project_id or f"proj_{uuid.uuid4().hex[:8]}"

        # 1. Requirements Extraction
        analysis = await self.analyst.analyze_transcript(transcript)

        # 2. Capability Evaluation against Task 1
        evaluated_reqs = await self.checker.evaluate_all(analysis["requirements"])

        # 3. Technical Effort Estimation
        estimated_reqs = self.estimator.estimate_all(evaluated_reqs)
        hours_range, expected_hours = self.estimator.compute_total_hours(estimated_reqs)

        # Gather citations
        citations = []
        for r in estimated_reqs:
            citations.extend(r.citations)

        scope = ProjectScope(
            project_id=pid,
            version=1,
            meeting_count=1,
            client_goal=analysis["client_goal"],
            requirements=estimated_reqs,
            assumptions=analysis["assumptions"],
            open_questions=analysis["open_questions"],
            risks=analysis["risks"],
            out_of_scope=analysis["out_of_scope"],
            total_custom_hours_range=hours_range,
            expected_total_hours=expected_hours,
            source_citations=citations,
            client_ready=False,  # CRITICAL: Always false until human approves!
        )

        # 4. Generate Initial SOW Draft
        scope.proposal_markdown = self.writer.generate_sow(scope)

        # 5. Persist
        self.store.save(scope)
        return scope

    async def process_follow_up(
        self, project_id: str, follow_up_transcript: str
    ) -> tuple[ProjectScope, ScopeChangeSet]:
        existing_scope = self.store.get(project_id)
        if not existing_scope:
            raise ValueError(f"Project '{project_id}' not found")

        # 1. Analyze follow-up transcript with existing requirements context
        new_analysis = await self.analyst.analyze_transcript(
            follow_up_transcript, existing_requirements=existing_scope.requirements
        )

        text_lower = follow_up_transcript.lower()
        change_set = ScopeChangeSet()
        updated_reqs: list[RequirementItem] = []

        existing_req_map = {r.id: r for r in existing_scope.requirements}
        new_req_titles = {r.title.lower(): r for r in new_analysis["requirements"]}

        # Check existing requirements for REMOVED, CHANGED, or UNCHANGED
        for orig_req in existing_scope.requirements:
            t_lower = orig_req.title.lower()

            # Check if explicitly removed in follow-up dialogue
            short_keywords = [t_lower, t_lower.replace("custom ", "").strip()]
            is_explicitly_removed = False
            for kw in short_keywords:
                pattern = rf"(cancel|canceling|cancelling|remove|removing|drop|dropping|skip|skipping|don't need|do not need|no longer need|not doing)\s+(the\s+|our\s+)?{re.escape(kw)}"
                if re.search(pattern, text_lower):
                    is_explicitly_removed = True
                    break

            if is_explicitly_removed:
                removed_item = orig_req.model_copy()
                removed_item.status = RequirementLifecycleStatus.REMOVED
                removed_item.change_reason = "Client explicitly removed item in follow-up meeting."
                change_set.removed_requirements.append(removed_item)
                # Omit or mark removed in updated requirements
                continue

            # Check if requirement changed or unchanged
            if t_lower in new_req_titles:
                new_candidate = new_req_titles[t_lower]
                if new_candidate.description != orig_req.description:
                    changed_item = new_candidate.model_copy()
                    changed_item.id = orig_req.id
                    changed_item.status = RequirementLifecycleStatus.CHANGED
                    changed_item.change_reason = "Scope or acceptance criteria modified in follow-up meeting."
                    change_set.changed_requirements.append(changed_item)
                    updated_reqs.append(changed_item)
                else:
                    unchanged_item = orig_req.model_copy()
                    unchanged_item.status = RequirementLifecycleStatus.UNCHANGED
                    change_set.unchanged_requirements.append(unchanged_item)
                    updated_reqs.append(unchanged_item)
            else:
                # Not mentioned in follow-up dialogue -> remains UNCHANGED
                unchanged_item = orig_req.model_copy()
                unchanged_item.status = RequirementLifecycleStatus.UNCHANGED
                change_set.unchanged_requirements.append(unchanged_item)
                updated_reqs.append(unchanged_item)

        # Check for completely NEW requirements introduced in follow-up
        existing_titles = {r.title.lower() for r in existing_scope.requirements}
        for cand in new_analysis["requirements"]:
            if cand.title.lower() not in existing_titles:
                new_item = cand.model_copy()
                new_item.status = RequirementLifecycleStatus.NEW
                new_item.change_reason = "New requirement introduced in follow-up meeting."
                change_set.new_requirements.append(new_item)
                updated_reqs.append(new_item)

        # 2. Evaluate Capabilities on NEW and CHANGED requirements
        reqs_to_evaluate = [
            r for r in updated_reqs if r.status in (RequirementLifecycleStatus.NEW, RequirementLifecycleStatus.CHANGED)
        ]
        if reqs_to_evaluate:
            evaluated_subset = await self.checker.evaluate_all(reqs_to_evaluate)
            eval_map = {r.id: r for r in evaluated_subset}
            final_reqs = [eval_map.get(r.id, r) for r in updated_reqs]
        else:
            final_reqs = updated_reqs

        # 3. Re-estimate custom work
        final_estimated = self.estimator.estimate_all(final_reqs)
        hours_range, expected_hours = self.estimator.compute_total_hours(final_estimated)

        # 4. Diff Summary
        diff_lines = [
            f"Scope Change Summary (Meeting #{existing_scope.meeting_count + 1}):",
            f"- New: {len(change_set.new_requirements)}",
            f"- Changed: {len(change_set.changed_requirements)}",
            f"- Unchanged: {len(change_set.unchanged_requirements)}",
            f"- Removed: {len(change_set.removed_requirements)}",
        ]
        change_set.diff_summary = "\n".join(diff_lines)

        # 5. Build Updated ProjectScope
        updated_scope = ProjectScope(
            project_id=project_id,
            version=existing_scope.version + 1,
            meeting_count=existing_scope.meeting_count + 1,
            client_goal=new_analysis["client_goal"] or existing_scope.client_goal,
            requirements=final_estimated,
            assumptions=list(set(existing_scope.assumptions + new_analysis["assumptions"])),
            open_questions=new_analysis["open_questions"],
            risks=list(set(existing_scope.risks + new_analysis["risks"])),
            out_of_scope=list(set(existing_scope.out_of_scope + new_analysis["out_of_scope"])),
            total_custom_hours_range=hours_range,
            expected_total_hours=expected_hours,
            source_citations=[c for r in final_estimated for c in r.citations],
            client_ready=False,  # CRITICAL: Reset to False on follow-up changes!
        )

        updated_scope.proposal_markdown = self.writer.generate_sow(updated_scope)

        # 6. Save
        self.store.save(updated_scope)
        return updated_scope, change_set

    def approve_scope(self, project_id: str, approved_by: str) -> ProjectScope:
        scope = self.store.get(project_id)
        if not scope:
            raise ValueError(f"Project '{project_id}' not found")

        if not approved_by or not approved_by.strip():
            raise ValueError("Approval requires a valid human approver identifier")

        scope.client_ready = True
        scope.approved_by = approved_by.strip()
        scope.approved_at = datetime.now(timezone.utc)
        scope.updated_at = datetime.now(timezone.utc)

        self.store.save(scope)
        return scope
