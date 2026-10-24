"""Deterministic report comparison helpers; inputs are validated report models."""

from __future__ import annotations

import hashlib

from local_assessment.models import (
    AssessmentFindingChange, AssessmentIssue, AssessmentReport, AssessmentRunComparison,
)


def _finding_key(issue: AssessmentIssue) -> str:
    material = f"{issue.check_id.value}\0{issue.classification}\0{issue.title}"
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]
    return f"assessment-finding-{digest}"


def compare_assessment_reports(
    current: AssessmentReport, previous_report_id: str | None,
    previous_issues: tuple[AssessmentIssue, ...],
) -> AssessmentRunComparison:
    """Compare inferred-risk identities, preserving evidence refs for human review."""
    current_by_key = {_finding_key(issue): issue for issue in current.inferred_risks}
    previous_by_key = {_finding_key(issue): issue for issue in previous_issues}
    introduced = tuple(
        AssessmentFindingChange(finding_key=key, issue_id=issue.issue_id, check_id=issue.check_id,
                                title=issue.title, evidence_refs=issue.evidence_refs)
        for key, issue in sorted(current_by_key.items()) if key not in previous_by_key
    )
    resolved = tuple(
        AssessmentFindingChange(finding_key=key, issue_id=issue.issue_id, check_id=issue.check_id,
                                title=issue.title, evidence_refs=issue.evidence_refs)
        for key, issue in sorted(previous_by_key.items()) if key not in current_by_key
    )
    unchanged = tuple(
        AssessmentFindingChange(finding_key=key, issue_id=current_by_key[key].issue_id,
                                check_id=current_by_key[key].check_id, title=current_by_key[key].title,
                                evidence_refs=current_by_key[key].evidence_refs)
        for key in sorted(current_by_key.keys() & previous_by_key.keys())
    )
    return AssessmentRunComparison(
        status="compared" if previous_report_id else "baseline",
        previous_report_id=previous_report_id,
        newly_introduced=introduced, resolved=resolved, unchanged=unchanged,
    )
