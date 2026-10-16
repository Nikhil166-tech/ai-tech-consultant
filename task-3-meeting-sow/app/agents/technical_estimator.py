from app.models import RequirementItem, CapabilityStatus, EstimateRange


class TechnicalEstimatorAgent:
    """
    Technical Estimator Agent:
    Estimates custom engineering effort using 3-point estimation (Optimistic, Most Likely, Pessimistic).
    CRITICAL POLICY: Native configuration items receive strictly 0 custom-development hours.
    Explicitly documents assumptions and technical risks.
    """

    def estimate_requirement(self, requirement: RequirementItem) -> RequirementItem:
        status = requirement.capability_status
        title_lower = requirement.title.lower()

        # 1. Native Configuration -> STRICTLY 0 Custom Hours
        if status == CapabilityStatus.NATIVE:
            requirement.estimate = EstimateRange.calculate(
                optimistic=0.0,
                most_likely=0.0,
                pessimistic=0.0,
                complexity="NONE",
                assumptions=["Standard Brilliant Directories platform setting; native configuration only."],
                risks=[],
            )
            return requirement

        # 2. Custom Engineering
        if status == CapabilityStatus.CUSTOM:
            if "crm" in title_lower or "hubspot" in title_lower or "salesforce" in title_lower:
                # API integration
                requirement.estimate = EstimateRange.calculate(
                    optimistic=12.0,
                    most_likely=20.0,
                    pessimistic=32.0,
                    complexity="MEDIUM",
                    assumptions=[
                        "Client provides sandbox API credentials with sufficient rate limits.",
                        "Standard two-way contact syncing without custom object schemas.",
                    ],
                    risks=[
                        "3rd-party webhook failure or schema breaking changes.",
                        "Field mapping discrepancies between BD member fields and CRM contacts.",
                    ],
                )
            elif "mobile app" in title_lower or "react native" in title_lower:
                # Mobile wrapper/app
                requirement.estimate = EstimateRange.calculate(
                    optimistic=40.0,
                    most_likely=60.0,
                    pessimistic=90.0,
                    complexity="HIGH",
                    assumptions=[
                        "WebView-based container with native push notifications wrapper.",
                        "Client supplies Apple Developer & Google Play accounts.",
                    ],
                    risks=[
                        "App store review rejection due to guideline 4.2 (minimum functionality for web wrappers).",
                        "Push notification certificate expiration.",
                    ],
                )
            else:
                # General custom widget / PHP logic
                requirement.estimate = EstimateRange.calculate(
                    optimistic=8.0,
                    most_likely=14.0,
                    pessimistic=24.0,
                    complexity="MEDIUM",
                    assumptions=["Custom code implemented via BD Widget Manager without core framework modifications."],
                    risks=["Custom CSS/JS conflicts with native BD theme updates."],
                )
            return requirement

        # 3. Partial Support (Native add-on + custom glue)
        if status == CapabilityStatus.PARTIAL:
            requirement.estimate = EstimateRange.calculate(
                optimistic=4.0,
                most_likely=8.0,
                pessimistic=16.0,
                complexity="LOW",
                assumptions=["Native add-on provides base functionality; hours allocated solely for custom bridge."],
                risks=["Add-on version compatibility with future BD core releases."],
            )
            return requirement

        # 4. Unknown Status (Technical spike estimate)
        requirement.estimate = EstimateRange.calculate(
            optimistic=4.0,
            most_likely=8.0,
            pessimistic=16.0,
            complexity="HIGH",
            assumptions=["Allocated as a time-boxed technical feasibility spike."],
            risks=["Feature may prove infeasible natively and require custom architecture."],
        )
        return requirement

    def estimate_all(self, requirements: list[RequirementItem]) -> list[RequirementItem]:
        estimated = []
        for req in requirements:
            estimated.append(self.estimate_requirement(req))
        return estimated

    def compute_total_hours(self, requirements: list[RequirementItem]) -> tuple[tuple[float, float], float]:
        """
        Calculates (min_hours, max_hours) range and expected total hours.
        """
        min_total = 0.0
        max_total = 0.0
        expected_total = 0.0

        for req in requirements:
            if req.estimate and req.capability_status != CapabilityStatus.NATIVE:
                min_total += req.estimate.optimistic_hours
                max_total += req.estimate.pessimistic_hours
                expected_total += req.estimate.expected_hours

        return (round(min_total, 1), round(max_total, 1)), round(expected_total, 1)
