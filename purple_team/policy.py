"""Independent authorization gate for the reviewed synthetic scenario catalog."""

from purple_team.catalog import SCENARIOS
from purple_team.models import ScenarioPolicyDecision

APPROVED_ORIGIN = "http://127.0.0.1:8767"
MAX_REQUESTS_PER_SCENARIO = 3


class LocalScenarioPolicy:
    def authorize(self, scenario_id: str, *, explicitly_authorized: bool) -> ScenarioPolicyDecision:
        scenario = SCENARIOS.get(scenario_id)
        if scenario is None:
            return ScenarioPolicyDecision(
                scenario_id=scenario_id, target_origin=APPROVED_ORIGIN, allowed=False,
                reason_code="scenario_not_allowlisted", maximum_requests=0,
            )
        if explicitly_authorized is not True:
            return ScenarioPolicyDecision(
                scenario_id=scenario_id, target_origin=APPROVED_ORIGIN, allowed=False,
                reason_code="explicit_authorization_required", maximum_requests=0,
            )
        return ScenarioPolicyDecision(
            scenario_id=scenario_id, target_origin=APPROVED_ORIGIN, allowed=True,
            reason_code="approved", maximum_requests=scenario.expected_count,
        )
