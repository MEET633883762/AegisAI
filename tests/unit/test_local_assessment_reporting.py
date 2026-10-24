from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from local_assessment.models import (
    AssessmentCheck, AssessmentDecision, AssessmentEvidence, AssessmentObservation,
    AssessmentReport, AssessmentResult, CheckId,
)
from private_api.store import SQLiteStore

TENANT_A = "synthetic-org-alpha"
TENANT_B = "synthetic-org-beta"
ORIGIN = "http://127.0.0.1:8767"


def observation(*, minute: int = 0, duration: int = 12, body: bytes = b"safe synthetic body",
                complete_headers: bool = False) -> AssessmentObservation:
    now = datetime(2026, 10, 22, 12, minute, tzinfo=timezone.utc)
    decision = AssessmentDecision(check_id=CheckId.SECURITY_HEADERS, target_origin=ORIGIN,
                                  allowed=True, reason_code="approved")
    evidence = AssessmentEvidence(
        evidence_ref=f"web-assessment-{minute}-security_headers_v1",
        observed_at_utc=now, request_path="/", response_status=200,
        response_bytes=len(body), response_sha256=hashlib.sha256(body).hexdigest(),
    )
    return AssessmentObservation(
        check_id=CheckId.SECURITY_HEADERS, decision=decision,
        outcome="headers_observed", duration_ms=duration,
        facts={"status": 200, "expected_status": 200, "status_matches_expectation": True,
               "content-security-policy": "default-src 'self'" if complete_headers else None,
               "x-content-type-options": "nosniff",
               "referrer-policy": "no-referrer" if complete_headers else None,
               "permissions-policy": "camera=()" if complete_headers else None},
        evidence=evidence,
    )


def report_for(*observations: AssessmentObservation) -> AssessmentReport:
    decisions = tuple(item.decision for item in observations)
    result = AssessmentResult(decisions=decisions, observations=observations)
    return AssessmentReport.from_result(result)


def test_report_links_raw_observations_to_inferred_risks_not_confirmed_findings():
    report = report_for(observation())
    refs = {item.evidence.evidence_ref for item in report.raw_observations if item.evidence}
    assert refs
    assert report.inferred_risks
    assert all(issue.classification == "inferred_risk" for issue in report.inferred_risks)
    assert all(set(issue.evidence_refs).issubset(refs) for issue in report.inferred_risks)
    assert report.confirmed_findings == ()
    assert all("safe synthetic body" not in str(item.model_dump()) for item in report.raw_observations)
    assert report.schema_version == "2.0"
    assert report.provenance == "fixed_loopback_synthetic_website"
    assert report.configuration_version and report.check_catalog_version


def test_observation_and_report_ids_are_deterministic_and_duplicates_collapse():
    first = observation(minute=0, duration=12)
    duplicate = observation(minute=8, duration=99)
    combined = report_for(first, duplicate)
    repeated = report_for(observation(minute=20, duration=4))
    assert len(combined.raw_observations) == 1
    assert combined.duplicate_observation_count == 1
    assert combined.report_id == repeated.report_id
    assert combined.raw_observations[0].evidence.evidence_ref == repeated.raw_observations[0].evidence.evidence_ref
    assert report_for(observation(body=b"a"), observation(body=b"b")).report_id == report_for(
        observation(body=b"b"), observation(body=b"a"),
    ).report_id


def test_malformed_observations_and_dangling_evidence_fail_validation():
    with pytest.raises(ValidationError):
        AssessmentEvidence(evidence_ref="bad", observed_at_utc=datetime.now(timezone.utc),
                           request_path="/arbitrary", response_status=200, response_bytes=0,
                           response_sha256="0" * 64)
    with pytest.raises(ValidationError):
        AssessmentObservation.model_validate({
            **observation().model_dump(mode="python"), "facts": {"too_long": "x" * 513},
        })
    good = report_for(observation())
    malformed = good.model_dump(mode="python")
    refs = {item.evidence.evidence_ref for item in good.raw_observations if item.evidence}
    malformed["inferred_risks"] = [{
        **good.inferred_risks[0].model_dump(), "evidence_refs": ("unknown-evidence",),
    }]
    with pytest.raises(ValidationError, match="unknown evidence"):
        AssessmentReport.validate_for_storage(malformed)
    malformed_confirmed = good.model_dump(mode="python")
    malformed_confirmed["confirmed_findings"] = [{
        "issue_id": "assessment-issue-0123456789abcdef", "check_id": "security_headers_v1",
        "classification": "confirmed_finding", "title": "Unsupported claim",
        "rationale": "The current checks cannot confirm vulnerabilities.",
        "evidence_refs": (next(iter(refs)),),
    }]
    with pytest.raises(ValidationError, match="do not support confirmed findings"):
        AssessmentReport.validate_for_storage(malformed_confirmed)


def test_schema_one_report_payload_remains_readable_without_database_migration():
    current = report_for(observation())
    legacy = current.model_dump(mode="json")
    legacy["schema_version"] = "1.0"
    for name in ("run_id", "started_at_utc", "configuration_version", "check_catalog_version", "provenance", "comparison"):
        legacy.pop(name, None)
    for item in legacy["raw_observations"]:
        for name in ("category", "description", "severity", "check_version", "configuration_version",
                     "expected_result", "observed_result", "outcome_status", "observed_at_utc"):
            item.pop(name, None)
    for issue in (*legacy["inferred_risks"], *legacy["confirmed_findings"]):
        issue.pop("severity", None)
        issue.pop("recommendation", None)
    loaded = AssessmentReport.validate_for_storage(legacy)
    assert loaded.schema_version == "1.0"
    assert loaded.raw_observations[0].check_version == "legacy"
    assert loaded.raw_observations[0].evidence.evidence_ref == current.raw_observations[0].evidence.evidence_ref


def test_tenant_scoped_storage_deduplicates_evidence_and_audits_each_store(tmp_path):
    db_path = tmp_path / "assessment.sqlite3"
    store = SQLiteStore(db_path)
    report = report_for(observation())
    store.save_assessment_report(TENANT_A, report)
    repeated_run = report_for(observation(minute=8, duration=99))
    assert repeated_run.report_id == report.report_id and repeated_run.run_id != report.run_id
    stored_repeat = store.save_assessment_report(TENANT_A, repeated_run)

    loaded = store.latest_assessment_report(TENANT_A)
    assert loaded is not None and loaded.report_id == report.report_id
    assert loaded.run_id == stored_repeat.run_id
    assert store.latest_assessment_report(TENANT_B) is None
    with sqlite3.connect(db_path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 6
        assert connection.execute("SELECT COUNT(*) FROM website_assessment_reports WHERE tenant_id = ?", (TENANT_A,)).fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM website_assessment_observations WHERE tenant_id = ?", (TENANT_A,)).fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM website_assessment_reports WHERE tenant_id = ?", (TENANT_B,)).fetchone()[0] == 0
    audit = store.audit_snapshot()
    assert len(audit) == 2
    assert all(row["tenant_id"] == TENANT_A and row["event_type"] == "protected_operation"
               and row["route"] == "assessment.report.store"
               and row["details_code"] == "assessment_report_saved" for row in audit)
    assert loaded.comparison.status == "compared"
    assert len(loaded.comparison.unchanged) == len(report.inferred_risks)


def test_tenant_scoped_report_comparison_identifies_new_and_resolved_risks(tmp_path):
    store = SQLiteStore(tmp_path / "assessment-comparison.sqlite3")
    initial = store.save_assessment_report(TENANT_A, report_for(observation(minute=1)))
    assert initial.comparison.status == "baseline"
    assert initial.comparison.previous_report_id is None

    safe = store.save_assessment_report(TENANT_A, report_for(observation(minute=2, complete_headers=True)))
    assert safe.comparison.status == "compared"
    assert safe.comparison.previous_report_id == initial.report_id
    assert len(safe.comparison.resolved) == len(initial.inferred_risks)
    assert not safe.comparison.newly_introduced

    regressed = store.save_assessment_report(TENANT_A, report_for(observation(minute=3)))
    assert regressed.comparison.previous_report_id == safe.report_id
    assert len(regressed.comparison.newly_introduced) == len(regressed.inferred_risks)
    assert not regressed.comparison.resolved
    assert store.latest_assessment_report(TENANT_B) is None


def test_storage_rejects_untrusted_tenant_and_invalid_report(tmp_path):
    store = SQLiteStore(tmp_path / "assessment.sqlite3")
    with pytest.raises(ValueError, match="invalid synthetic tenant"):
        store.save_assessment_report("tenant-from-caller", report_for(observation()))
    invalid = report_for(observation()).model_copy(update={"raw_observations": ()})
    with pytest.raises(ValidationError):
        store.save_assessment_report(TENANT_A, invalid)
    assert store.audit_snapshot() == []


def test_additive_schema_upgrade_from_version_three_preserves_existing_audit(tmp_path):
    db_path = tmp_path / "upgrade.sqlite3"
    SQLiteStore(db_path)
    with sqlite3.connect(db_path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 6
        connection.execute("INSERT INTO audit_events (occurred_at_utc, tenant_id, event_type, method, route, outcome, details_code) VALUES (?, NULL, ?, ?, ?, ?, ?)",
                           (datetime.now(timezone.utc).isoformat(), "request_rejected", "GET", "health", "success", "kept"))
        connection.execute("DROP TABLE website_assessment_report_observations")
        connection.execute("DROP TABLE website_assessment_reports")
        connection.execute("DROP TABLE website_assessment_observations")
        connection.execute("PRAGMA user_version = 3")
    upgraded = SQLiteStore(db_path)
    with sqlite3.connect(db_path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 6
        assert connection.execute("SELECT details_code FROM audit_events").fetchone()[0] == "kept"
        names = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"website_assessment_reports", "website_assessment_observations",
                "website_assessment_report_observations"}.issubset(names)
    assert upgraded.latest_assessment_report(TENANT_A) is None
