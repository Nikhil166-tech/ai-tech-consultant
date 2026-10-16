from app.models import RequirementItem, CapabilityStatus, EstimateRange


class TechnicalEstimatorAgent:
    """
    Technical Estimator Agent:
    Estimates custom engineering effort using 3-point estimation (Optimistic, Most Likely, Pessimistic).
    CRITICAL POLICIES:
    - Native configuration items receive strictly 0 custom-development hours.
    - Partial items receive custom hours only for the custom code/styling portion.
    - UNKNOWN items receive time-boxed discovery spikes that are strictly SEPARATED
      from confirmed custom development hours.
    """

    def estimate_requirement(self, requirement: RequirementItem) -> RequirementItem:
        status = requirement.capability_status
        title_lower = requirement.title.lower()
        desc_lower = requirement.description.lower()

        # 1. Native Configuration -> STRICTLY 0 Custom Hours
        if status == CapabilityStatus.NATIVE:
            requirement.estimate = EstimateRange.calculate(
                optimistic=0.0,
                most_likely=0.0,
                pessimistic=0.0,
                complexity="NONE",
                assumptions=["Standard Brilliant Directories platform setting; native configuration only ($0 custom dev)."],
                risks=[],
            )
            return requirement

        # 2. Custom Engineering
        if status == CapabilityStatus.CUSTOM:
            if "crm" in title_lower or "hubspot" in title_lower or "salesforce" in title_lower:
                requirement.estimate = EstimateRange.calculate(
                    optimistic=12.0,
                    most_likely=20.0,
                    pessimistic=32.0,
                    complexity="MEDIUM",
                    assumptions=[
                        "Client provides sandbox API credentials with sufficient rate limits.",
                        "Contact synchronization without complex custom object relational schemas.",
                    ],
                    risks=[
                        "3rd-party webhook delivery failure or schema breaking changes.",
                        "Field mapping discrepancies between BD member fields and external CRM contacts.",
                    ],
                )
            elif "mobile app" in title_lower or "react native" in title_lower:
                requirement.estimate = EstimateRange.calculate(
                    optimistic=40.0,
                    most_likely=60.0,
                    pessimistic=90.0,
                    complexity="HIGH",
                    assumptions=[
                        "WebView-based container with native push notifications wrapper.",
                        "Client supplies Apple Developer & Google Play organizational accounts.",
                    ],
                    risks=[
                        "App store review rejection due to guideline 4.2 (minimum functionality for web wrappers).",
                        "Push notification certificate expiration.",
                    ],
                )
            else:
                requirement.estimate = EstimateRange.calculate(
                    optimistic=8.0,
                    most_likely=14.0,
                    pessimistic=24.0,
                    complexity="MEDIUM",
                    assumptions=["Custom code implemented via BD Widget Manager without core framework modifications."],
                    risks=["Custom CSS/JS conflicts with native BD theme updates."],
                )
            return requirement

        # 3. Partial Support (Native add-on + custom glue/styling)
        if status == CapabilityStatus.PARTIAL:
            requirement.estimate = EstimateRange.calculate(
                optimistic=4.0,
                most_likely=8.0,
                pessimistic=16.0,
                complexity="LOW",
                assumptions=[
                    "Native BD feature provides base data model and display.",
                    "Hours allocated strictly for custom CSS/JavaScript extensions or glue logic.",
                ],
                risks=["Theme updates may require re-testing custom CSS/JS."],
            )
            return requirement

        # 4. Unknown Status (Technical Feasibility Discovery Spike)
        requirement.estimate = EstimateRange.calculate(
            optimistic=4.0,
            most_likely=8.0,
            pessimistic=16.0,
            complexity="HIGH",
            assumptions=[
                "Allocated strictly as a time-boxed technical feasibility discovery spike.",
                "Does NOT represent committed custom engineering hours.",
            ],
            risks=[
                "Feature may require significant external infrastructure if not supported natively in BD.",
                "Discovery outcome may recommend alternative architecture.",
            ],
        )
        return requirement

    def estimate_all(self, requirements: list[RequirementItem]) -> list[RequirementItem]:
        estimated = []
        for req in requirements:
            estimated.append(self.estimate_requirement(req))
        return estimated

    def compute_total_hours(
        self, requirements: list[RequirementItem]
    ) -> tuple[tuple[float, float], float, tuple[float, float], float]:
        """
        Calculates:
        - (custom_min, custom_max), custom_expected (from CUSTOM and PARTIAL only)
        - (discovery_min, discovery_max), discovery_expected (from UNKNOWN only)
        NATIVE items strictly contribute 0 to both totals.
        """
        custom_min = 0.0
        custom_max = 0.0
        custom_expected = 0.0

        discovery_min = 0.0
        discovery_max = 0.0
        discovery_expected = 0.0

        for req in requirements:
            if not req.estimate:
                continue

            if req.capability_status in (CapabilityStatus.CUSTOM, CapabilityStatus.PARTIAL):
                custom_min += req.estimate.optimistic_hours
                custom_max += req.estimate.pessimistic_hours
                custom_expected += req.estimate.expected_hours
            elif req.capability_status == CapabilityStatus.UNKNOWN:
                discovery_min += req.estimate.optimistic_hours
                discovery_max += req.estimate.pessimistic_hours
                discovery_expected += req.estimate.expected_hours

        return (
            (round(custom_min, 1), round(custom_max, 1)),
            round(custom_expected, 1),
            (round(discovery_min, 1), round(discovery_max, 1)),
            round(discovery_expected, 1),
        )