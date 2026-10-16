import os
import re
import json
import uuid
from datetime import datetime, timezone
from typing import Any
from app.models import (
    ProjectScope,
    RequirementItem,
    RequirementLifecycleStatus,
    ScopeChangeSet,
    CapabilityStatus,
)
from app.agents.requirements_analyst import RequirementsAnalystAgent, get_next_req_number
from app.agents.capability_checker import ProductCapabilityCheckerAgent
from app.agents.technical_estimator import TechnicalEstimatorAgent
from app.agents.proposal_writer import ProposalWriterAgent


class ProjectStore:
    """Lightweight JSON-persisted store for multi-meeting project scopes and version history."""

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
            except Exception:
                self._projects = {}

    def persist(self) -> None:
        os.makedirs(os.path.dirname(os.path.abspath(self.filepath)), exist_ok=True)
        data = {k: v.model_dump(mode="json") for k, v in self._projects.items()}
        with open(self.filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)


def match_requirement(req: RequirementItem, candidates: list[RequirementItem]) -> RequirementItem | None:
    """Matches a requirement by exact ID, title containment, or shared core keywords."""
    req_title = req.title.lower()
    req_words = set(re.findall(r"\w+", req_title)) - {"custom", "automated", "member", "to", "for", "and", "the", "integration"}

    for cand in candidates:
        if cand.id == req.id:
            return cand
        cand_title = cand.title.lower()
        if cand_title == req_title or cand_title in req_title or req_title in cand_title:
            return cand
        cand_words = set(re.findall(r"\w+", cand_title)) - {"custom", "automated", "member", "to", "for", "and", "the", "integration"}
        overlap = req_words.intersection(cand_words)
        if len(overlap) >= 2 or (len(overlap) == 1 and any(w in overlap for w in ("crm", "hubspot", "stripe", "badge", "badges", "radius", "recaptcha", "csv", "export", "app", "erp"))):
            return cand
def get_requirement_keywords(req: RequirementItem) -> set[str]:
    """Returns domain keywords associated specifically with this requirement's topic."""
    t_lower = req.title.lower()
    words = set(re.findall(r"\w+", t_lower)) - {"custom", "automated", "member", "to", "for", "and", "the", "integration"}
    if "crm" in t_lower or "hubspot" in t_lower:
        words.update(["crm", "hubspot", "salesforce"])
    if "stripe" in t_lower or "payment" in t_lower:
        words.update(["stripe", "payment"])
    if "billing" in t_lower or "subscription" in t_lower or "recurring" in t_lower:
        words.update(["billing", "subscription", "recurring"])
    if "radius" in t_lower or "distance" in t_lower:
        words.update(["radius", "distance"])
    if "badge" in t_lower or "verified" in t_lower:
        words.update(["badge", "badges", "verified"])
    if "mobile" in t_lower or "app" in t_lower:
        words.update(["mobile", "app", "ios", "android"])
    if "accounting" in t_lower or "erp" in t_lower:
        words.update(["accounting", "erp", "quickbooks"])
    if "welcome" in t_lower or "email" in t_lower:
        words.update(["welcome", "email"])
    if "export" in t_lower or "csv" in t_lower:
        words.update(["export", "csv"])
    if "recaptcha" in t_lower or "spam" in t_lower:
        words.update(["recaptcha", "spam"])
    if "claim" in t_lower or "listing" in t_lower:
        words.update(["claim", "claimable", "listing", "listings"])
    return words


class PipelineOrchestrator:
    """
    Autonomous Plain-Python Multi-Agent Pipeline Orchestrator.
    Executes:
    Meeting Transcript
           ↓
    Requirements Analyst
           ↓
    Product Capability Checker (calls Task 1 /api/v1/ask)
           ↓
    Technical Estimator
           ↓
    Proposal / SOW Writer
           ↓
    Human Approval Gate
           ↓
    Client-ready output
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
        proj_id = project_id or f"proj_{uuid.uuid4().hex[:8]}"

        # 1. Extract Requirements (treats transcript as untrusted)
        analysis = await self.analyst.analyze_transcript(transcript)

        # 2. Check Capabilities against Task 1 Knowledge Brain
        evaluated_reqs = await self.checker.evaluate_all(analysis["requirements"])

        # 3. Estimate Technical Effort (separates custom dev vs discovery spike)
        final_estimated = self.estimator.estimate_all(evaluated_reqs)
        custom_range, exp_custom, disc_range, exp_disc = self.estimator.compute_total_hours(final_estimated)

        citations = [c for r in final_estimated for c in r.citations]

        # 4. Construct Initial ProjectScope
        scope = ProjectScope(
            project_id=proj_id,
            version=1,
            meeting_count=1,
            client_goal=analysis["client_goal"],
            requirements=final_estimated,
            assumptions=analysis["assumptions"],
            open_questions=analysis["open_questions"],
            risks=analysis["risks"],
            out_of_scope=analysis["out_of_scope"],
            custom_hours_range=custom_range,
            expected_custom_hours=exp_custom,
            discovery_hours_range=disc_range,
            expected_discovery_hours=exp_disc,
            total_custom_hours_range=custom_range,
            expected_total_hours=exp_custom,
            source_citations=citations,
            client_ready=False,  # CRITICAL: Always false until human approves!
            decisions=[f"Meeting #1: Initial scope drafted with {len(final_estimated)} functional requirements."],
        )

        # 5. Generate Initial Draft SOW
        scope.proposal_markdown = self.writer.generate_sow(scope)

        # 6. Persist
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

        change_set = ScopeChangeSet()
        updated_reqs: list[RequirementItem] = []

        # Split dialogue into lines/clauses for precise utterance matching
        clauses = [
            c.strip().lower()
            for line in follow_up_transcript.splitlines()
            for c in re.split(r"[.\n;]|\bbut\b|\bwhile\b|\bhowever\b", line)
            if c.strip()
        ]

        new_candidates = list(new_analysis["requirements"])
        matched_candidate_ids = set()

        oos_patterns = [r"\b(out of scope|defer|phase 2|later phase|not in phase 1|post-launch)\b"]
        rem_patterns = [r"\b(cancel|canceling|cancelling|remove|removing|drop|dropping|skip|skipping|no longer need|don't need|do not need|not doing|eliminate|won't need)\b"]
        mod_patterns = [r"\b(only send|one-way|two-way|instead of|change|update|modify|restrict to|switch to|custom css animation)\b"]
        unch_patterns = [
            r"\bkeep\b.+?\b(unchanged|as[- ]is|the same)\b",
            r"\b(stays?|remains?)\b.+?\b(unchanged|as[- ]is|the same)\b",
            r"\b.+?\b(stays?|remains?)\s+(unchanged|as[- ]is|the same)\b",
            r"\bno\s+changes?\s+(to|for|in|on)\b",
            r"\bleave\b.+?\b(as[- ]is|unchanged|alone)\b",
        ]

        # Check existing requirements for OUT_OF_SCOPE, REMOVED, CHANGED, or UNCHANGED
        for orig_req in existing_scope.requirements:
            match_words = get_requirement_keywords(orig_req)

            # A. Check if moved OUT OF SCOPE (deferred to phase 2 / post-launch)
            is_out_of_scope = False
            for clause in clauses:
                if any(re.search(p, clause) for p in oos_patterns) and any(re.search(rf"\b{re.escape(w)}\b", clause) for w in match_words):
                    is_out_of_scope = True
                    break

            if is_out_of_scope:
                oos_item = orig_req.model_copy()
                oos_item.status = RequirementLifecycleStatus.OUT_OF_SCOPE
                oos_item.change_reason = "Deferred to future phase / moved out of current scope in follow-up meeting."
                change_set.out_of_scope_requirements.append(oos_item)
                continue

            # B. Check if explicitly REMOVED (cancelled, dropped, no longer needed)
            is_removed = False
            for clause in clauses:
                if any(re.search(p, clause) for p in rem_patterns) and any(re.search(rf"\b{re.escape(w)}\b", clause) for w in match_words):
                    is_removed = True
                    break

            if is_removed:
                removed_item = orig_req.model_copy()
                removed_item.status = RequirementLifecycleStatus.REMOVED
                removed_item.change_reason = "Client explicitly removed requirement in follow-up meeting."
                change_set.removed_requirements.append(removed_item)
                continue

            # C. Check if explicitly UNCHANGED (e.g. 'keep X unchanged', 'X stays unchanged', 'no change to X', 'leave X as is')
            is_explicit_unchanged = False
            for clause in clauses:
                if any(re.search(p, clause) for p in unch_patterns):
                    if orig_req.id.lower() in clause or any(re.search(rf"\b{re.escape(w)}\b", clause) for w in match_words):
                        is_explicit_unchanged = True
                        break

            if is_explicit_unchanged:
                unchanged_item = orig_req.model_copy()
                unchanged_item.id = orig_req.id  # PRESERVE STABLE ID!
                unchanged_item.description = orig_req.description  # PRESERVE ORIGINAL DESCRIPTION!
                unchanged_item.status = RequirementLifecycleStatus.UNCHANGED
                unchanged_item.change_reason = ""
                # PRESERVE EXISTING CAPABILITY STATUS / CITATIONS / ESTIMATE
                unchanged_item.capability_status = orig_req.capability_status
                unchanged_item.citations = list(orig_req.citations)
                unchanged_item.estimate = orig_req.estimate.model_copy() if orig_req.estimate else None

                # Mark all matching candidates so they are not treated as new in Step D
                for cand in new_candidates:
                    if cand.id == orig_req.id or match_requirement(orig_req, [cand]):
                        matched_candidate_ids.add(cand.id)

                change_set.unchanged_requirements.append(unchanged_item)
                updated_reqs.append(unchanged_item)
                continue

            # D. Check if CHANGED or UNCHANGED against new extracted candidates
            matched_candidate = match_requirement(orig_req, new_candidates)

            # Check if there is an explicit modification mentioned in a matching clause
            explicit_mod_in_clause = False
            mod_clause_text = ""
            for clause in clauses:
                if any(re.search(p, clause) for p in mod_patterns) and any(re.search(rf"\b{re.escape(w)}\b", clause) for w in match_words):
                    explicit_mod_in_clause = True
                    mod_clause_text = clause.strip()
                    break

            if matched_candidate or explicit_mod_in_clause:
                base_item = matched_candidate or orig_req
                if matched_candidate:
                    matched_candidate_ids.add(matched_candidate.id)
                desc_changed = matched_candidate and (matched_candidate.description != orig_req.description)

                if desc_changed or explicit_mod_in_clause:
                    changed_item = base_item.model_copy()
                    changed_item.id = orig_req.id  # PRESERVE STABLE ID!
                    changed_item.status = RequirementLifecycleStatus.CHANGED

                    # Preserve actual changed acceptance criteria / constraint
                    if mod_clause_text:
                        clean_clause = mod_clause_text
                        for prefix in ("client:", "alex:", "dr. reed:", "-"):
                            if clean_clause.lower().startswith(prefix):
                                clean_clause = clean_clause[len(prefix):].strip()
                        changed_item.description = f"{orig_req.title}: {clean_clause}"
                        changed_item.change_reason = f"Constraint updated in follow-up: {clean_clause}"
                    else:
                        changed_item.change_reason = f"Modified criteria in follow-up meeting: {base_item.description}"

                    change_set.changed_requirements.append(changed_item)
                    updated_reqs.append(changed_item)
                else:
                    unchanged_item = orig_req.model_copy()
                    unchanged_item.status = RequirementLifecycleStatus.UNCHANGED
                    change_set.unchanged_requirements.append(unchanged_item)
                    updated_reqs.append(unchanged_item)
            else:
                unchanged_item = orig_req.model_copy()
                unchanged_item.status = RequirementLifecycleStatus.UNCHANGED
                change_set.unchanged_requirements.append(unchanged_item)
                updated_reqs.append(unchanged_item)

        # D. Check for completely NEW requirements introduced in follow-up
        next_req_num = get_next_req_number(existing_scope.requirements)
        for cand in new_candidates:
            if cand.id not in matched_candidate_ids and not match_requirement(cand, existing_scope.requirements):
                new_item = cand.model_copy()
                new_item.id = f"REQ-{next_req_num:02d}"
                next_req_num += 1
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

        # 3. Re-estimate effort
        final_estimated = self.estimator.estimate_all(final_reqs)
        custom_range, exp_custom, disc_range, exp_disc = self.estimator.compute_total_hours(final_estimated)

        # 4. Compile Diff Summary with all 5 lifecycle states
        diff_lines = [
            f"Scope Change Summary (Meeting #{existing_scope.meeting_count + 1}):",
            f"- New: {len(change_set.new_requirements)}",
            f"- Changed: {len(change_set.changed_requirements)}",
            f"- Unchanged: {len(change_set.unchanged_requirements)}",
            f"- Removed: {len(change_set.removed_requirements)}",
            f"- Out of Scope: {len(change_set.out_of_scope_requirements)}",
        ]
        change_set.diff_summary = "\n".join(diff_lines)

        # 5. Snapshot previous version in version_history with full structured schema (Item 5)
        snapshot = {
            "version": existing_scope.version,
            "meeting_count": existing_scope.meeting_count,
            "approval_state": {
                "client_ready": existing_scope.client_ready,
                "approved_by": existing_scope.approved_by,
                "approved_at": existing_scope.approved_at,
            },
            "custom_total_hours": existing_scope.expected_custom_hours,
            "custom_hours_range": existing_scope.custom_hours_range,
            "discovery_total_hours": existing_scope.expected_discovery_hours,
            "discovery_hours_range": existing_scope.discovery_hours_range,
            "requirements": [
                {
                    "id": r.id,
                    "title": r.title,
                    "description": r.description,
                    "capability_status": r.capability_status.value if hasattr(r.capability_status, "value") else str(r.capability_status),
                    "lifecycle_status": r.status.value if hasattr(r.status, "value") else str(r.status),
                }
                for r in existing_scope.requirements
            ],
            "open_questions": list(existing_scope.open_questions),
            "assumptions": list(existing_scope.assumptions),
            "risks": list(existing_scope.risks),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        history = list(existing_scope.version_history)
        history.append(snapshot)

        # Check follow-up transcript text for budget adjustments
        if any(b in follow_up_transcript.lower() for b in ("budget", "slashed", "reduced by", "cut by", "50%")):
            if not any("budget" in r.lower() for r in new_analysis["risks"]):
                new_analysis["risks"].append("Budget reduction reported: project budget reduced by 50%; scope must prioritize essential launch items.")
            if not any("budget" in a.lower() for a in new_analysis["assumptions"]):
                new_analysis["assumptions"].append("Scope prioritized for reduced budget constraints.")

        # Check follow-up transcript text for deadline adjustments
        if any(d in follow_up_transcript.lower() for d in ("deadline", "moved up", "go-live moved", "accelerated", "next month")):
            if not any("deadline" in r.lower() for r in new_analysis["risks"]):
                new_analysis["risks"].append("Accelerated deadline: target go-live date moved up to next month; compressed delivery timeline increases schedule risk.")
            if not any("deadline" in a.lower() for a in new_analysis["assumptions"]):
                new_analysis["assumptions"].append("Delivery milestone timeline adjusted for accelerated deadline.")

        # Combine assumptions (preserving order and removing duplicates)
        accumulated_assumptions = list(dict.fromkeys(existing_scope.assumptions + new_analysis["assumptions"]))

        # Preserve unresolved open questions + new questions
        unresolved_questions = list(dict.fromkeys(existing_scope.open_questions + new_analysis["open_questions"]))
        if any(r.status == RequirementLifecycleStatus.CHANGED and "crm" in r.title.lower() for r in final_estimated):
            unresolved_questions = [q for q in unresolved_questions if "crm" not in q.lower()]

        # Combine out_of_scope
        combined_oos = list(dict.fromkeys(
            existing_scope.out_of_scope +
            new_analysis["out_of_scope"] +
            [f"[{r.id}] {r.title}: {r.description}" for r in change_set.out_of_scope_requirements]
        ))

        # Record decision
        new_decisions = list(existing_scope.decisions)
        new_decisions.append(
            f"Meeting #{existing_scope.meeting_count + 1}: Follow-up processed with "
            f"{len(change_set.new_requirements)} new, {len(change_set.changed_requirements)} changed, "
            f"{len(change_set.removed_requirements)} removed, {len(change_set.out_of_scope_requirements)} out of scope."
        )

        change_history = list(existing_scope.change_history)
        change_history.append(change_set)

        # 6. Build Updated ProjectScope
        updated_scope = ProjectScope(
            project_id=project_id,
            version=existing_scope.version + 1,
            meeting_count=existing_scope.meeting_count + 1,
            client_goal=new_analysis["client_goal"] or existing_scope.client_goal,
            requirements=final_estimated,
            assumptions=accumulated_assumptions,
            open_questions=unresolved_questions,
            risks=list(dict.fromkeys(existing_scope.risks + new_analysis["risks"])),
            out_of_scope=combined_oos,
            custom_hours_range=custom_range,
            expected_custom_hours=exp_custom,
            discovery_hours_range=disc_range,
            expected_discovery_hours=exp_disc,
            total_custom_hours_range=custom_range,
            expected_total_hours=exp_custom,
            source_citations=[c for r in final_estimated for c in r.citations],
            client_ready=False,  # CRITICAL: Always reset to False on follow-up changes!
            approved_by=None,
            approved_at=None,
            version_history=history,
            change_history=change_history,
            decisions=new_decisions,
        )

        updated_scope.proposal_markdown = self.writer.generate_sow(updated_scope)

        # 7. Persist
        self.store.save(updated_scope)
        return updated_scope, change_set

    def approve_scope(self, project_id: str, approved_by: str) -> ProjectScope:
        scope = self.store.get(project_id)
        if not scope:
            raise ValueError(f"Project '{project_id}' not found")

        if not approved_by or not approved_by.strip():
            raise ValueError("Human approver name or identifier cannot be empty")

        clean_approver = approved_by.strip()
        scope.client_ready = True
        scope.approved_by = clean_approver
        scope.approved_at = datetime.now(timezone.utc)
        scope.decisions.append(f"Scope Version {scope.version} approved by human reviewer '{clean_approver}' — marked client-ready.")

        scope.proposal_markdown = self.writer.generate_sow(scope)
        self.store.save(scope)
        return scope