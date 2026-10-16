from app.models import ProjectScope, CapabilityStatus


class ProposalWriterAgent:
    """
    Proposal / SOW Writer Agent:
    Compiles structured project scope into an executive Statement of Work (SOW).
    DOES NOT invent pricing, delivery deadlines, or unverified platform capabilities.
    Clearly separates native platform configuration ($0 custom hours),
    confirmed custom development effort, and technical discovery feasibility spikes.
    """

    def generate_sow(self, scope: ProjectScope) -> str:
        native_reqs = [r for r in scope.requirements if r.capability_status == CapabilityStatus.NATIVE]
        partial_reqs = [r for r in scope.requirements if r.capability_status == CapabilityStatus.PARTIAL]
        custom_reqs = [r for r in scope.requirements if r.capability_status == CapabilityStatus.CUSTOM]
        unknown_reqs = [r for r in scope.requirements if r.capability_status == CapabilityStatus.UNKNOWN]

        status_header = (
            "## 🟢 APPROVED STATEMENT OF WORK (CLIENT-READY)"
            if scope.client_ready
            else "## 🟡 INTERNAL SCOPE DRAFT (NOT CLIENT-READY — PENDING HUMAN APPROVAL)"
        )

        approval_metadata = ""
        if scope.client_ready and scope.approved_by:
            approval_metadata = f"\n**Approved By**: {scope.approved_by} on {scope.approved_at.strftime('%Y-%m-%d %H:%M:%S UTC') if scope.approved_at else 'N/A'}\n"

        lines = [
            f"# Statement of Work (SOW) — Project {scope.project_id}",
            f"**Version**: {scope.version} | **Meeting Sessions Processed**: {scope.meeting_count}",
            status_header,
            approval_metadata,
            "### 1. Client Goal & Objectives",
            scope.client_goal,
            "",
            "### 2. Native Brilliant Directories Capabilities ($0 Custom Dev Hours)",
            "The following requirements are fulfilled through built-in Brilliant Directories configuration:",
        ]

        if native_reqs:
            for r in native_reqs:
                note = f" — *{r.native_alternative_notes}*" if r.native_alternative_notes else ""
                lines.append(f"- **[{r.id}] {r.title}**: {r.description}{note}")
        else:
            lines.append("- *(No purely native configuration requirements identified)*")

        lines.extend([
            "",
            "### 3. Confirmed Custom Engineering & Integrations",
            "The following requirements require custom software development or external API integration:",
        ])

        combined_custom = custom_reqs + partial_reqs
        if combined_custom:
            for r in combined_custom:
                est_text = (
                    f" | Estimate: {r.estimate.expected_hours}h ({r.estimate.optimistic_hours}–{r.estimate.pessimistic_hours}h, {r.estimate.complexity_level})"
                    if r.estimate
                    else ""
                )
                kind = " (Partial Native + Custom Styling/Glue)" if r.capability_status == CapabilityStatus.PARTIAL else ""
                lines.append(f"- **[{r.id}] {r.title}**{kind}: {r.description}{est_text}")
        else:
            lines.append("- *(No custom development required)*")

        if unknown_reqs:
            lines.extend([
                "",
                "### 4. Technical Feasibility & Discovery Spikes (Unverified Items)",
                "The following items could not be confirmed natively from the Solution Center knowledge base and are allocated time-boxed feasibility spikes:",
            ])
            for r in unknown_reqs:
                est_text = (
                    f" | Discovery Spike: {r.estimate.expected_hours}h ({r.estimate.optimistic_hours}–{r.estimate.pessimistic_hours}h)"
                    if r.estimate
                    else ""
                )
                lines.append(f"- **[{r.id}] {r.title}**: {r.description}{est_text}")

        lines.extend([
            "",
            "### 5. Level of Effort Summary",
            f"- **Confirmed Custom Engineering Effort**: {scope.expected_custom_hours} hours (Range: {scope.custom_hours_range[0]} – {scope.custom_hours_range[1]} hrs)",
        ])

        if scope.expected_discovery_hours > 0:
            lines.append(
                f"- **Technical Discovery & Feasibility Spikes**: {scope.expected_discovery_hours} hours (Range: {scope.discovery_hours_range[0]} – {scope.discovery_hours_range[1]} hrs)"
            )
            lines.append("  *(Note: Discovery hours represent time-boxed investigations and are strictly excluded from confirmed custom development)*")

        lines.extend([
            "",
            "### 6. Out of Scope",
        ])
        for oos in scope.out_of_scope:
            lines.append(f"- {oos}")

        lines.extend([
            "",
            "### 7. Key Assumptions & Technical Risks",
            "**Assumptions:**",
        ])
        for asm in scope.assumptions:
            lines.append(f"- {asm}")

        lines.append("\n**Risks:**")
        for rsk in scope.risks:
            lines.append(f"- {rsk}")

        if scope.open_questions:
            lines.append("\n**Open Questions for Client Clarification:**")
            for oq in scope.open_questions:
                lines.append(f"- {oq}")

        lines.append("\n### 8. Solution Center Verified Knowledge Citations")
        if scope.source_citations:
            for c in scope.source_citations:
                lines.append(f"- [{c.title} — {c.section_heading}]({c.url})")
        else:
            lines.append("- *(No documentation citations recorded)*")

        return "\n".join(lines)