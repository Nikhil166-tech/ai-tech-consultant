from app.models import ProjectScope, CapabilityStatus


class ProposalWriterAgent:
    """
    Proposal / Statement of Work (SOW) Writer Agent:
    Transforms approved internal scope and capability evaluations into a clean,
    concise, client-facing proposal and Statement of Work.
    CRITICAL POLICY: Does not invent arbitrary prices, deadlines, or platform features.
    Outputs markdown formatted SOW with client_ready = False.
    """

    def generate_sow(self, scope: ProjectScope) -> str:
        native_reqs = [r for r in scope.requirements if r.capability_status == CapabilityStatus.NATIVE]
        custom_reqs = [r for r in scope.requirements if r.capability_status in (CapabilityStatus.CUSTOM, CapabilityStatus.PARTIAL)]
        unknown_reqs = [r for r in scope.requirements if r.capability_status == CapabilityStatus.UNKNOWN]

        min_hrs, max_hrs = scope.total_custom_hours_range
        exp_hrs = scope.expected_total_hours

        lines = [
            f"# Statement of Work (SOW) & Project Scope",
            f"**Project ID:** `{scope.project_id}` | **Scope Version:** v{scope.version} | **Status:** DRAFT (Internal Review)",
            f"",
            f"## 1. Executive Summary & Objective",
            f"{scope.client_goal}",
            f"",
            f"## 2. Brilliant Directories Native Capabilities (Standard Configuration - 0 Custom Hours)",
            f"The following deliverables will be configured directly using native Brilliant Directories features, requiring zero custom software development:",
        ]

        if native_reqs:
            for r in native_reqs:
                citation_info = f" *(Ref: {r.citations[0].title})*" if r.citations else ""
                lines.append(f"- **[{r.id}] {r.title}**: {r.description}{citation_info}")
                if r.native_alternative_notes:
                    lines.append(f"  - *Implementation Note:* {r.native_alternative_notes}")
        else:
            lines.append("- *No strictly native items identified in this scope.*")

        lines.extend([
            f"",
            f"## 3. Custom Engineering & Integration Scope",
            f"The following items require custom software engineering, custom widget creation, or third-party API integration:",
        ])

        if custom_reqs:
            for r in custom_reqs:
                est = r.estimate
                hrs_str = f"{est.optimistic_hours}h - {est.pessimistic_hours}h (Expected: ~{est.expected_hours}h)" if est else "TBD"
                lines.append(f"- **[{r.id}] {r.title}** [{r.capability_status}]: {r.description}")
                lines.append(f"  - *Estimated Effort:* {hrs_str} | Complexity: {est.complexity_level if est else 'TBD'}")
                if est and est.assumptions:
                    lines.append(f"  - *Assumptions:* {'; '.join(est.assumptions)}")
        else:
            lines.append("- *No custom engineering required. All items fulfilled through native configuration.*")

        if unknown_reqs:
            lines.extend([
                f"",
                f"## 4. Pending Technical Spikes (Unverified Platform Items)",
                f"The following items could not be confirmed in the Brilliant Directories documentation and will undergo a technical discovery spike:",
            ])
            for r in unknown_reqs:
                lines.append(f"- **[{r.id}] {r.title}**: {r.description}")
                if r.native_alternative_notes:
                    lines.append(f"  - *Feasibility Spike:* {r.native_alternative_notes}")

        lines.extend([
            f"",
            f"## 5. Effort Summary",
            f"- **Native Configuration Effort:** Standard setup (Included)",
            f"- **Custom Development Hours:** {min_hrs} - {max_hrs} Hours (Expected: ~{exp_hrs} Hours)",
            f"",
            f"## 6. Assumptions & Prerequisites",
        ])
        for a in scope.assumptions:
            lines.append(f"- {a}")

        lines.extend([
            f"",
            f"## 7. Out of Scope",
        ])
        for o in scope.out_of_scope:
            lines.append(f"- {o}")

        if scope.open_questions:
            lines.extend([
                f"",
                f"## 8. Open Questions for Client Clarification",
            ])
            for q in scope.open_questions:
                lines.append(f"- {q}")

        lines.extend([
            f"",
            f"---",
            f"*Confidential - Prepared for Client Review upon Formal Consultant Approval*",
        ])

        return "\n".join(lines)
