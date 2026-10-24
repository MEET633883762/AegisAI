"""Reviewed, fixed catalog of synthetic-only local website scenarios."""

from purple_team.models import ScenarioDefinition

CATALOG_VERSION = "aegisai-purple-scenarios-v1"

SCENARIOS = {
    "local-health-baseline": ScenarioDefinition(
        scenario_id="local-health-baseline", version="1.0",
        purpose="Confirm that one ordinary request to the local synthetic health endpoint produces a benign access record.",
        prerequisites=("The AegisAI loopback demo site is running on 127.0.0.1:8767.",),
        expected_telemetry_type="synthetic_http_access", expected_route_code="health",
        expected_status=200, expected_count=1, expected_detection_rule_ids=(),
        assessment_check_ids=("health_status_v1",),
        cleanup_requirements="No site data changes; the request adds a bounded synthetic access-log record retained by normal log rotation.",
        request_method="GET", request_path="/health",
    ),
    "synthetic-auth-rejection": ScenarioDefinition(
        scenario_id="synthetic-auth-rejection", version="1.0",
        purpose="Exercise the site's fixed credential-free rejection route and observe whether three synthetic failures reach the existing AUTH-001 rule.",
        prerequisites=("The AegisAI loopback demo site is running on 127.0.0.1:8767.",),
        expected_telemetry_type="auth_failure", expected_route_code="login",
        expected_status=401, expected_count=3, expected_detection_rule_ids=("AUTH-001",),
        assessment_check_ids=(),
        cleanup_requirements="No account or site data changes; three empty-body requests add synthetic access-log records retained by normal log rotation.",
        request_method="POST", request_path="/login-failure",
    ),
}
