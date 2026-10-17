import os
import re
import json
import httpx
from pydantic import BaseModel
from app.models import RequirementItem, CapabilityStatus, Task1Citation
from app.task1_client import Task1MeetingClient


class ClaudeCapabilityDecision(BaseModel):
    status: CapabilityStatus
    notes: str = ""


class ProductCapabilityCheckerAgent:
    """
    Product Capability Checker Agent:
    Queries the Task 1 Knowledge Brain as the SINGLE source of truth for Brilliant Directories.
    Does NOT contain or duplicate hardcoded Brilliant Directories platform facts.
    Classifies capability based strictly on Task 1 evidence into:
    - NATIVE: natively supported out-of-the-box or standard admin settings
    - PARTIAL: native base exists but requirement requires custom styling/glue
    - CUSTOM: unsupported natively; requires custom API/code
    - UNKNOWN: evidence insufficient, ambiguous, or unverified
    """

    def __init__(
        self,
        task1_client: Task1MeetingClient | None = None,
        api_key: str | None = None,
        model: str = "claude-haiku-5-5",
    ):
        self.task1_client = task1_client or Task1MeetingClient()
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        self.model = os.getenv("ANTHROPIC_MODEL_TEXT") or model

    async def evaluate_requirement(self, requirement: RequirementItem) -> RequirementItem:
        # Query Task 1 using requirement title first (canonical feature term)
        result = await self.task1_client.query_capability(requirement.title)
        
        stopwords = {
            "custom", "automated", "member", "to", "for", "and", "the", "integration",
            "processing", "prevention", "widget", "support", "feature", "search",
            "directory", "directories", "general", "overview", "with", "into", "all",
            "records", "push", "via", "new", "site", "website", "portal", "card",
            "cards", "profile", "profiles", "page", "pages", "homepage", "bar", "modal", "modals"
        }
        topic_words = (set(requirement.title.lower().split()) | set(requirement.description.lower().split())) - stopwords
        topic_words = {w.strip(".,;:()") for w in topic_words if len(w.strip(".,;:()")) >= 3}
        
        cits_text = (" ".join([c.snippet for c in result.response.citations]) + " " + result.response.answer).lower() if result.response and result.response.citations else ""
        has_words = any(re.search(rf"\b{re.escape(w)}\b", cits_text) or (w.endswith("s") and re.search(rf"\b{re.escape(w[:-1])}\b", cits_text)) for w in topic_words)
        
        # If title query didn't retrieve topic words, fallback to full details query
        if not has_words or not result.response or not result.response.citations:
            full_res = await self.task1_client.query_capability(f"{requirement.title}: {requirement.description}")
            if full_res.success and full_res.response and full_res.response.citations:
                result = full_res

        # 1. If Task 1 is unavailable, timed out, had insufficient evidence, or requires human review
        if not result.success or not result.response or not result.response.is_known or result.response.needs_human_review:
            requirement.capability_status = CapabilityStatus.UNKNOWN
            requirement.citations = []
            requirement.native_alternative_notes = (
                f"Feature feasibility unverified in Task 1 Knowledge Brain ({result.error_reason or 'No verified documentation'}). "
                "Preserved as an open question / technical feasibility discovery spike."
            )
            return requirement

        task1_resp = result.response
        citations = task1_resp.citations

        # If Task 1 has zero verified citations, preserve uncertainty as UNKNOWN
        if not citations:
            requirement.capability_status = CapabilityStatus.UNKNOWN
            requirement.citations = []
            requirement.native_alternative_notes = (
                "Task 1 returned no verified documentation citations for this feature. "
                "Preserved as UNKNOWN feasibility spike."
            )
            return requirement

        # Map citations to our Task1Citation models
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

        # 2. Structured Evidence Classification
        decision = await self._classify_evidence(requirement, task1_resp.answer, citation_models)
        requirement.capability_status = decision.status
        requirement.native_alternative_notes = decision.notes

        return requirement

    async def _classify_evidence(
        self, requirement: RequirementItem, answer: str, citations: list[Task1Citation]
    ) -> ClaudeCapabilityDecision:
        if self.api_key:
            try:
                return await self._classify_with_claude(requirement, answer, citations)
            except Exception:
                pass  # Safely fall back to deterministic classifier

        return self._classify_deterministic(requirement, answer, citations)

    async def _classify_with_claude(
        self, requirement: RequirementItem, answer: str, citations: list[Task1Citation]
    ) -> ClaudeCapabilityDecision:
        cit_text = "\n".join([f"- {c.title} ({c.section_heading}): {c.snippet}" for c in citations])
        system_prompt = (
            "You are a strict Product Capability Classifier for Brilliant Directories consultancy.\n"
            "You are given a client's requirement and ONLY the official documentation evidence returned by Task 1 Knowledge Brain.\n"
            "You must classify the capability into one of four statuses:\n"
            "- NATIVE: The feature is built-in, natively supported out-of-the-box, or configurable through standard admin settings in Brilliant Directories as described in the evidence.\n"
            "- PARTIAL: Brilliant Directories natively provides the core feature according to the evidence, BUT the requirement specifically demands custom styling, custom code/widgets, or external bridge extensions not covered out-of-the-box.\n"
            "- CUSTOM: The feature is NOT natively provided by Brilliant Directories and requires external API development, custom webhooks, or custom development according to the evidence.\n"
            "- UNKNOWN: The evidence does not specifically confirm, document, or mention this feature, or the evidence is ambiguous.\n\n"
            "CRITICAL: Base your decision EXCLUSIVELY on the provided Task 1 answer and citations. Do NOT invent product capabilities or assume unstated platform features.\n"
            "Return valid JSON matching: {\"status\": \"NATIVE\"|\"PARTIAL\"|\"CUSTOM\"|\"UNKNOWN\", \"notes\": \"...\"}"
        )
        user_prompt = (
            f"Client Requirement:\nTitle: {requirement.title}\nDescription: {requirement.description}\n\n"
            f"Task 1 Evidence:\nAnswer: {answer}\nCitations:\n{cit_text}"
        )

        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": self.api_key or "",
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                    **({"anthropic-workspace-id": os.getenv("ANTHROPIC_WORKSPACE_ID")} if os.getenv("ANTHROPIC_WORKSPACE_ID") else {}),
                },
                json={
                    "model": self.model,
                    "max_tokens": 500,
                    "system": system_prompt,
                    "messages": [{"role": "user", "content": user_prompt}],
                },
            )

        if res.status_code == 200:
            data = res.json()
            raw_text = data["content"][0]["text"].strip()
            match = re.search(r"\{[\s\S]*\}", raw_text)
            if match:
                parsed = json.loads(match.group(0))
                return ClaudeCapabilityDecision.model_validate(parsed)

        return self._classify_deterministic(requirement, answer, citations)

    def _classify_deterministic(
        self, requirement: RequirementItem, answer: str, citations: list[Task1Citation]
    ) -> ClaudeCapabilityDecision:
        ans_lower = answer.lower()
        snippets_lower = " ".join([c.snippet.lower() for c in citations])
        evidence = f"{ans_lower} {snippets_lower}"
        req_text = f"{requirement.title} {requirement.description}".lower()

        # 1. Uncertainty check: if evidence says insufficient or cannot verify, return UNKNOWN
        if any(u in ans_lower for u in ("insufficient", "don't have enough", "not documented", "cannot verify", "is ambiguous")):
            return ClaudeCapabilityDecision(
                status=CapabilityStatus.UNKNOWN,
                notes="Task 1 documentation is insufficient or ambiguous. Assigned as UNKNOWN feasibility discovery spike."
            )

        if not citations:
            return ClaudeCapabilityDecision(
                status=CapabilityStatus.UNKNOWN,
                notes="No documentation citations found in Task 1 Knowledge Brain. Preserved as UNKNOWN."
            )

        # 2. Extract distinctive topic words from requirement (excluding common grammatical/directory stopwords)
        stopwords = {
            "custom", "automated", "member", "to", "for", "and", "the", "integration",
            "processing", "prevention", "widget", "support", "feature", "search",
            "directory", "directories", "general", "overview", "with", "into", "all",
            "records", "push", "via", "new", "site", "website", "portal", "card",
            "cards", "profile", "profiles", "page", "pages", "homepage", "bar", "modal", "modals"
        }
        topic_words = (set(re.findall(r"\w+", requirement.title.lower())) | set(re.findall(r"\w+", requirement.description.lower()))) - stopwords
        topic_words = {w for w in topic_words if len(w) >= 3}

        evidence_mentions_feature = any(
            (re.search(rf"\b{re.escape(w)}\b", evidence) or (w.endswith("s") and re.search(rf"\b{re.escape(w[:-1])}\b", evidence)))
            for w in topic_words
        )

        # Generic terminology in Task 1 evidence indicating developer endpoints / custom dev
        has_custom_dev_evidence = any(
            cd in evidence
            for cd in (
                "developer hub", "api endpoints", "api documentation", "custom webhook", "create a custom webhook",
                "api calls", "custom plugin", "custom coding", "unsupported natively", "not supported natively",
                "not available natively", "requires custom development", "requires custom api", "custom code required",
                "developer required", "external integration required", "third-party api", "get members through the api"
            )
        )

        # Generic terminology in Task 1 evidence indicating built-in or native admin settings
        has_native_admin_evidence = any(
            na in evidence
            for na in (
                "built-in", "built in", "native", "natively", "out-of-the-box", "out of the box",
                "standard setting", "standard settings", "admin portal", "admin area", "admin dashboard",
                "general settings", "design settings", "finance settings", "turn on", "enable",
                "standard configuration", "default feature", "included with",
                "section: finance", "section: my members", "section: interactions", "section: my content",
                "section: emails", "add-on", "overview"
            )
        )

        needs_custom_extension = any(
            ce in req_text
            for ce in (
                "custom css", "custom animation", "custom styling", "plus custom", "with custom",
                "custom layout", "custom widget"
            )
        )

        # Decision based strictly on Task 1 evidence:
        # If evidence doesn't even mention the topic words, preserve uncertainty as UNKNOWN
        if not evidence_mentions_feature:
            return ClaudeCapabilityDecision(
                status=CapabilityStatus.UNKNOWN,
                notes="Task 1 evidence does not document the specific feature requested. Assigned as UNKNOWN."
            )

        # Explicit custom development / Developer Hub evidence
        if has_custom_dev_evidence and any(k in req_text for k in ("integration", "wrapper", "bridge", "api", "webhook", "external", "sync")):
            return ClaudeCapabilityDecision(
                status=CapabilityStatus.CUSTOM,
                notes="Task 1 evidence indicates external developer API endpoints, Developer Hub, or custom webhooks are required."
            )

        # Explicit native admin setting evidence
        if has_native_admin_evidence:
            if needs_custom_extension:
                return ClaudeCapabilityDecision(
                    status=CapabilityStatus.PARTIAL,
                    notes="Core feature natively supported in Brilliant Directories, but requirement specifically demands custom styling/code extension. Estimated for custom glue/styling only."
                )

            top_cit = citations[0] if citations else None
            loc = f"{top_cit.title} ({top_cit.section_heading})" if top_cit else "standard admin portal"
            return ClaudeCapabilityDecision(
                status=CapabilityStatus.NATIVE,
                notes=f"Natively supported out-of-the-box in Brilliant Directories via {loc}. Standard admin configuration only ($0 custom development hours)."
            )

        # Otherwise: unverified / ambiguous
        return ClaudeCapabilityDecision(
            status=CapabilityStatus.UNKNOWN,
            notes="Task 1 evidence does not explicitly confirm native admin configuration nor verified custom dev path. Preserved as UNKNOWN."
        )

    async def evaluate_all(self, requirements: list[RequirementItem]) -> list[RequirementItem]:
        evaluated = []
        for req in requirements:
            evaluated.append(await self.evaluate_requirement(req))
        return evaluated