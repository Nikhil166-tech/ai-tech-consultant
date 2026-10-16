from app.models import RequirementItem, CapabilityStatus, Task1Citation
from app.task1_client import Task1MeetingClient


class ProductCapabilityCheckerAgent:
    """
    Product Capability Checker Agent:
    Queries the Task 1 Knowledge Brain to determine whether a requirement:
    - already exists natively in Brilliant Directories,
    - is partially supported via native add-ons,
    - requires custom engineering/widgets,
    - or cannot be verified (UNKNOWN).
    Highlights cheaper native configuration whenever custom dev was needlessly requested.
    """

    def __init__(self, task1_client: Task1MeetingClient | None = None):
        self.task1_client = task1_client or Task1MeetingClient()

    async def evaluate_requirement(self, requirement: RequirementItem) -> RequirementItem:
        query = f"{requirement.title}: {requirement.description}"
        result = await self.task1_client.query_capability(query)

        # 1. If Task 1 is unavailable, timed out, or had insufficient evidence
        if not result.success or not result.response or not result.response.is_known:
            requirement.capability_status = CapabilityStatus.UNKNOWN
            requirement.citations = []
            requirement.native_alternative_notes = (
                f"Feature feasibility unverified in Knowledge Brain ({result.error_reason or 'No documentation'}). "
                "Preserved as an open question for technical verification spike."
            )
            return requirement

        task1_resp = result.response
        citations = task1_resp.citations

        # 2. Map citations to our Task1Citation models
        citation_models = [
            Task1Citation(
                url=c.url,
                title=c.title,
                category=c.category,
                folder=c.folder,
                section_heading=c.section_heading,
                snippet=c.snippet,
                source_type=c.source_type,
            )
            for c in citations
        ]
        requirement.citations = citation_models

        # 3. Classify capability based on verified knowledge and requirement context
        desc_lower = requirement.description.lower()
        title_lower = requirement.title.lower()

        # Known strictly native capabilities in Brilliant Directories
        is_native_topic = any(
            t in title_lower or t in desc_lower
            for t in (
                "stripe",
                "payment gateway",
                "recurring",
                "monthly billing",
                "search radius",
                "welcome email",
                "email template",
                "recaptcha",
                "spam prevention",
                "google analytics",
                "ga4",
                "export",
                "claimable",
                "verified badge",
                "profile badges",
            )
        )

        # Known custom integration topics
        is_custom_topic = any(
            t in title_lower or t in desc_lower
            for t in (
                "hubspot",
                "salesforce",
                "crm integration",
                "mobile app",
                "react native",
                "webhook",
                "custom php widget",
                "external api bridge",
            )
        )

        if is_custom_topic:
            requirement.capability_status = CapabilityStatus.CUSTOM
            requirement.native_alternative_notes = (
                "Requires custom API integration or webhook bridge outside native Brilliant Directories features."
            )
        elif is_native_topic:
            requirement.capability_status = CapabilityStatus.NATIVE
            # Highlight cheaper native configuration
            top_citation = citation_models[0] if citation_models else None
            loc = f"{top_citation.title} ({top_citation.section_heading})" if top_citation else "standard admin portal"
            requirement.native_alternative_notes = (
                f"Natively supported out-of-the-box in Brilliant Directories via {loc}. "
                "Requires $0 in custom development hours; standard admin configuration only."
            )
        else:
            # Fall back to Task 1 inferred capability
            requirement.capability_status = result.inferred_capability
            if requirement.capability_status == CapabilityStatus.UNKNOWN:
                requirement.native_alternative_notes = (
                    "Documentation in Solution Center does not explicitly confirm native availability. "
                    "Assigned as UNKNOWN pending specialist confirmation."
                )

        return requirement

    async def evaluate_all(self, requirements: list[RequirementItem]) -> list[RequirementItem]:
        evaluated = []
        for req in requirements:
            evaluated.append(await self.evaluate_requirement(req))
        return evaluated
