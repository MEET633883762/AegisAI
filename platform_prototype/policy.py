"""Independent policy gate for explicitly requested synthetic action simulations."""

from __future__ import annotations

from platform_prototype.models import ActionRequest, Finding, SimulatedActionOutcome

ALLOWED_SIMULATIONS = frozenset({"increase_monitoring", "create_review_task"})
MIN_CONFIDENCE_FOR_SIMULATION = 0.70


def evaluate_simulated_actions(
    findings: list[Finding], requests: list[ActionRequest]
) -> list[SimulatedActionOutcome]:
    findings_by_id = {finding.finding_id: finding for finding in findings}
    seen: set[tuple[str, str]] = set()
    outcomes: list[SimulatedActionOutcome] = []
    for request in requests:
        key = (request.finding_id, request.action_type)
        finding = findings_by_id.get(request.finding_id)
        if key in seen:
            status, reason = "denied", "duplicate action request in this report was rejected"
        elif request.action_type not in ALLOWED_SIMULATIONS:
            status, reason = "denied", "action type is not in the synthetic simulation allowlist"
        elif finding is None:
            status, reason = "denied", "finding does not exist in this synthetic report"
        elif not finding.evidence_refs:
            status, reason = "denied", "finding has no evidence references"
        elif finding.confidence < MIN_CONFIDENCE_FOR_SIMULATION:
            status, reason = "denied", "finding confidence is below the simulation policy threshold"
        else:
            status, reason = "simulated", "policy allowed a labeled simulation; no system action was executed"
        seen.add(key)
        outcomes.append(SimulatedActionOutcome(
            finding_id=request.finding_id,
            action_type=request.action_type,
            status=status,
            executed=False,
            reason=reason,
        ))
    return outcomes
