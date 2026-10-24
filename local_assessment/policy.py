"""Independent policy gate for fixed, harmless loopback HTTP observations.

This is deliberately separate from ControllerPolicy, which authorizes and
executes Red/Blue simulator actions and cannot safely authorize HTTP requests.
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from urllib.parse import urlsplit

from local_assessment.models import AssessmentCheck, AssessmentDecision, CheckId

APPROVED_ORIGIN = "http://127.0.0.1:8767"
APPROVED_PORT = 8767
CHECK_PATHS = {
    CheckId.HEALTH_STATUS: "/health",
    CheckId.SECURITY_HEADERS: "/",
    CheckId.COOKIE_ATTRIBUTES: "/health",
}
MAX_CHECKS_PER_ASSESSMENT = 3


@dataclass(frozen=True)
class LocalAssessmentPolicy:
    """Approves only the versioned catalog and exact loopback origin."""

    def authorize(self, check: AssessmentCheck) -> AssessmentDecision:
        reason = "approved"
        try:
            parsed = urlsplit(check.target_origin)
            port = parsed.port
            host = parsed.hostname
            if (parsed.scheme != "http" or parsed.username is not None or parsed.password is not None
                    or host != "127.0.0.1" or port != APPROVED_PORT or parsed.path not in ("", "/")
                    or parsed.query or parsed.fragment):
                reason = "target_not_allowlisted"
            else:
                ip = ipaddress.ip_address(host)
                if not ip.is_loopback:
                    reason = "target_not_loopback"
        except (ValueError, TypeError):
            reason = "target_not_allowlisted"
        if check.check_id not in CHECK_PATHS:
            reason = "check_not_allowlisted"
        return AssessmentDecision(
            check_id=check.check_id, target_origin=check.target_origin,
            allowed=reason == "approved", reason_code=reason,
        )
