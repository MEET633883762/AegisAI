"""Operator-invoked runner for the fixed local website assessment catalog."""

from local_assessment.controller import LocalAssessmentController
from local_assessment.models import AssessmentCheck, AssessmentReport, AssessmentResult, CheckId
from local_assessment.policy import APPROVED_ORIGIN

ASSESSMENT_TENANT_ID = "synthetic-org-demo"


class LocalAssessmentRunner:
    """Runs the complete fixed catalog; accepts no target or path input."""

    def __init__(self, controller: LocalAssessmentController | None = None) -> None:
        self._controller = controller or LocalAssessmentController()

    def run(self) -> AssessmentResult:
        checks = [
            AssessmentCheck(check_id=check_id, target_origin=APPROVED_ORIGIN)
            for check_id in (CheckId.HEALTH_STATUS, CheckId.SECURITY_HEADERS, CheckId.COOKIE_ATTRIBUTES)
        ]
        return self._controller.run(checks)

    def run_and_store(self, store) -> AssessmentReport:
        """Persist the fixed local assessment under the local demo tenant only."""
        report = AssessmentReport.from_result(self.run())
        return store.save_assessment_report(ASSESSMENT_TENANT_ID, report)
