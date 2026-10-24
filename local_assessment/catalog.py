"""Versioned definitions and result classification for fixed passive HTTP checks."""

from __future__ import annotations

from local_assessment.models import (
    AssessmentCheckDefinition, AssessmentDecision, CheckId, CheckOutcome,
)

CHECK_CATALOG_VERSION = "local-web-checks-v1"
CONFIGURATION_VERSION = "local-website-config-v1"

_NO_MAPPING = (
    "No ATT&CK technique or named defensive control is mapped: these passive configuration checks do not observe adversary behavior, "
    "and no framework-specific control mapping has been independently reviewed."
)

CHECK_CATALOG: dict[CheckId, AssessmentCheckDefinition] = {
    CheckId.HEALTH_STATUS: AssessmentCheckDefinition(
        check_id=CheckId.HEALTH_STATUS, version="1.0", category="availability",
        description="Observe the fixed local demo site's health response.", severity="informational",
        expected_result="The fixed /health endpoint returns HTTP 200.",
        mitre_attack_technique_ids=(), defensive_control_ids=(), mapping_rationale=_NO_MAPPING,
    ),
    CheckId.SECURITY_HEADERS: AssessmentCheckDefinition(
        check_id=CheckId.SECURITY_HEADERS, version="1.0", category="response_security",
        description="Observe a small allowlist of response security headers on the local demo site's home page.", severity="medium",
        expected_result="Content-Security-Policy, X-Content-Type-Options: nosniff, Referrer-Policy, and Permissions-Policy are present.",
        mitre_attack_technique_ids=(), defensive_control_ids=(), mapping_rationale=_NO_MAPPING,
    ),
    CheckId.COOKIE_ATTRIBUTES: AssessmentCheckDefinition(
        check_id=CheckId.COOKIE_ATTRIBUTES, version="1.0", category="cookie_configuration",
        description="Observe security attributes only if the fixed local health response sets a cookie.", severity="low",
        expected_result="If a cookie is returned, Secure, HttpOnly, and an explicit SameSite value are present; otherwise the check is not applicable.",
        mitre_attack_technique_ids=(), defensive_control_ids=(), mapping_rationale=_NO_MAPPING,
    ),
}


def classify_result(
    check_id: CheckId,
    decision: AssessmentDecision,
    outcome: str,
    error_category: str | None,
    facts: dict[str, str | int | bool | None],
) -> tuple[CheckOutcome, str]:
    """Return a bounded status and human-readable observation without asserting exploitability."""
    if (not decision.allowed or error_category is not None
            or outcome in {"redirect_not_followed", "redirect_denied_out_of_scope", "not_run_deadline"}):
        return CheckOutcome.ERROR, f"Check did not complete ({error_category or outcome or decision.reason_code})."

    status = facts.get("status")
    if facts.get("status_matches_expectation") is False:
        return CheckOutcome.FAIL, f"Observed HTTP {status}; expected HTTP 200."

    if check_id is CheckId.HEALTH_STATUS:
        return CheckOutcome.PASS, f"Observed HTTP {status}; expected HTTP 200."
    if check_id is CheckId.SECURITY_HEADERS:
        required = {
            "content-security-policy": None,
            "x-content-type-options": "nosniff",
            "referrer-policy": None,
            "permissions-policy": None,
        }
        missing = [name for name, expected in required.items()
                   if facts.get(name) is None or (expected is not None and str(facts.get(name)).strip().lower() != expected)]
        if missing:
            return CheckOutcome.FAIL, "Not observed or did not match: " + ", ".join(missing) + "."
        return CheckOutcome.PASS, "All catalogued response headers were observed with expected values."
    if check_id is CheckId.COOKIE_ATTRIBUTES:
        if facts.get("cookie_returned") is not True:
            return CheckOutcome.NOT_APPLICABLE, "The response did not set a cookie; cookie attribute checks do not apply."
        missing = [name for name, observed in (
            ("Secure", facts.get("secure")), ("HttpOnly", facts.get("httponly")), ("SameSite", facts.get("samesite")),
        ) if observed is False or observed is None]
        if missing:
            return CheckOutcome.FAIL, "Cookie attributes not observed: " + ", ".join(missing) + "."
        return CheckOutcome.PASS, "The returned cookie included Secure, HttpOnly, and SameSite attributes."
    return CheckOutcome.ERROR, "No catalog result classifier is available."
