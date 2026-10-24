from __future__ import annotations

from datetime import datetime, timezone

import pytest

from private_api.executive_reports import (
    ExecutiveObservation,
    ExecutiveReportInputError,
    build_executive_report,
)
from private_api.telemetry import TelemetryEventType, TelemetryFinding, TelemetrySeverity


TENANT = "synthetic-org-alpha"
GENERATED = datetime(2026, 10, 22, 12, tzinfo=timezone.utc)


def finding(finding_id: str, *, severity: str, status: str, refs: list[str]) -> TelemetryFinding:
    timestamp = datetime(2026, 10, 22, 10, tzinfo=timezone.utc)
    return TelemetryFinding(
        finding_id=finding_id, rule_id="AUTH-001", rule_version="1.0",
        severity=TelemetrySeverity(severity), confidence=0.85,
        first_seen_utc=timestamp, last_seen_utc=timestamp,
        asset_ref="synthetic-web-1", evidence_refs=refs,
        event_ids=[f"syn-{ref}" for ref in refs],
        explanation="Synthetic rule output requires human review.",
        confidence_factors=["synthetic evidence references are present"], status=status,
    )


def evidence(ref: str, *, minute: int, event_id: str | None = None, related: list[str] | None = None) -> ExecutiveObservation:
    return ExecutiveObservation(
        evidence_ref=ref, event_id=event_id or f"syn-{ref}",
        event_type=TelemetryEventType.AUTH_FAILURE,
        occurred_at_utc=datetime(2026, 10, 22, 10, minute, tzinfo=timezone.utc),
        related_finding_ids=related or [],
    )


def test_report_has_counts_timeline_existing_evidence_and_inferred_only_classification():
    findings = [
        finding("tfinding-aaaaaaaaaaaa", severity="high", status="open", refs=["synthetic-evidence-2", "synthetic-evidence-1"]),
        finding("tfinding-bbbbbbbbbbbb", severity="medium", status="closed", refs=["synthetic-evidence-1"]),
    ]
    report = build_executive_report(
        tenant_id=TENANT, findings=findings,
        evidence=[evidence("synthetic-evidence-2", minute=2), evidence("synthetic-evidence-1", minute=1)],
        generated_at_utc=GENERATED,
    )

    assert report.data_classification == "synthetic"
    assert report.label == "SYNTHETIC - NOT REAL CLIENT DATA"
    assert report.report_id.startswith("executive-report-")
    assert "inferred risks" in report.executive_summary
    assert report.finding_counts.by_severity.model_dump() == {"low": 0, "medium": 1, "high": 1, "critical": 0}
    assert report.finding_counts.by_status.model_dump() == {"open": 1, "acknowledged": 0, "closed": 1}
    assert len(report.inferred_risks) == 2
    assert all(item.classification == "inferred_risk" for item in report.inferred_risks)
    assert report.confirmed_findings == []
    assert [item.evidence_ref for item in report.observations] == ["synthetic-evidence-1", "synthetic-evidence-2"]
    assert [item.evidence_ref for item in report.timeline] == ["synthetic-evidence-1", "synthetic-evidence-2"]
    assert report.timeline[0].finding_ids == ["tfinding-aaaaaaaaaaaa", "tfinding-bbbbbbbbbbbb"]
    assert {item.category for item in report.recommendations} == {"investigation", "remediation"}
    assert all("no action is taken" in item.text or "Review the listed evidence" in item.text
               for item in report.recommendations)


def test_report_id_is_stable_for_same_inputs_and_generation_time():
    data = dict(
        tenant_id=TENANT,
        findings=[finding("tfinding-aaaaaaaaaaaa", severity="high", status="open", refs=["synthetic-evidence-1"])],
        evidence=[evidence("synthetic-evidence-1", minute=1)],
        generated_at_utc=GENERATED,
    )
    first = build_executive_report(**data)
    second = build_executive_report(**data)
    assert first.model_dump(mode="json") == second.model_dump(mode="json")


def test_missing_or_conflicting_evidence_fails_closed():
    item = finding("tfinding-aaaaaaaaaaaa", severity="high", status="open", refs=["synthetic-evidence-1"])
    with pytest.raises(ExecutiveReportInputError, match="missing evidence"):
        build_executive_report(tenant_id=TENANT, findings=[item], evidence=[], generated_at_utc=GENERATED)

    conflicting = [
        evidence("synthetic-evidence-1", minute=1),
        evidence("synthetic-evidence-1", minute=2, event_id="syn-other"),
    ]
    with pytest.raises(ExecutiveReportInputError, match="conflicting evidence"):
        build_executive_report(tenant_id=TENANT, findings=[item], evidence=conflicting, generated_at_utc=GENERATED)


def test_duplicate_findings_and_invalid_tenant_are_rejected():
    item = finding("tfinding-aaaaaaaaaaaa", severity="high", status="open", refs=["synthetic-evidence-1"])
    ref = [evidence("synthetic-evidence-1", minute=1)]
    with pytest.raises(ExecutiveReportInputError, match="tenant"):
        build_executive_report(tenant_id="tenant-from-caller", findings=[item], evidence=ref, generated_at_utc=GENERATED)
    with pytest.raises(ExecutiveReportInputError, match="finding IDs"):
        build_executive_report(tenant_id=TENANT, findings=[item, item], evidence=ref, generated_at_utc=GENERATED)


def test_unlinked_evidence_is_not_included_and_naive_time_is_rejected():
    item = finding("tfinding-aaaaaaaaaaaa", severity="high", status="open", refs=["synthetic-evidence-1"])
    report = build_executive_report(
        tenant_id=TENANT, findings=[item],
        evidence=[evidence("synthetic-evidence-1", minute=1), evidence("synthetic-unlinked", minute=2)],
        generated_at_utc=GENERATED,
    )
    assert [row.evidence_ref for row in report.observations] == ["synthetic-evidence-1"]
    with pytest.raises(ValueError, match="timezone"):
        build_executive_report(
            tenant_id=TENANT, findings=[item], evidence=[evidence("synthetic-evidence-1", minute=1)],
            generated_at_utc=datetime(2026, 10, 22),
        )
