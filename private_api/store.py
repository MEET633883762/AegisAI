"""Tenant-scoped SQLite store for synthetic reports and append-only audit rows."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from pydantic import ValidationError

from platform_prototype.models import Finding, IncidentReport
from local_assessment.models import (
    AssessmentIssue, AssessmentObservation, AssessmentReport, AssessmentRunComparison, assessment_observation_digest,
    assessment_observation_reference,
)
from local_assessment.reporting import compare_assessment_reports
from private_api.auth import TENANT_PATTERN
from private_api.models import (
    EvidenceReferenceResponse,
    IncidentReportResponse,
    IncidentSummary,
)
from private_api.investigations import (
    AddAnalystNoteRequest, AddContextRequest, AddEvidenceLinkRequest, AddFindingLinkRequest,
    CreateCaseRequest, InvestigationCaseSummary, UpdateCaseStatusRequest,
)
from private_api.telemetry import (
    MAX_DETECTION_EVENTS,
    MAX_RETAINED_OBSERVATIONS_PER_FINDING,
    MAX_RETAINED_RUNS_PER_TENANT,
    MAX_STORED_EVENTS_PER_TENANT,
    SyntheticTelemetryBatch,
    SyntheticTelemetryEvent,
    TelemetryConflictError,
    TelemetryFinding,
    TelemetryReport,
    detect_findings,
    make_telemetry_report,
    normalize_and_deduplicate,
)
from purple_team.models import ScenarioExecutionReport


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SQLiteStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=2.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 2000")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version > 6:
                raise RuntimeError("database schema version is newer than this application")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS tenants (
                    tenant_id TEXT PRIMARY KEY,
                    data_classification TEXT NOT NULL CHECK(data_classification = 'synthetic'),
                    created_at_utc TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS incidents (
                    tenant_id TEXT NOT NULL,
                    incident_id TEXT NOT NULL,
                    report_id TEXT NOT NULL,
                    dataset_id TEXT NOT NULL,
                    generated_at_utc TEXT NOT NULL,
                    report_json TEXT NOT NULL,
                    PRIMARY KEY (tenant_id, incident_id),
                    FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id)
                );
                CREATE TABLE IF NOT EXISTS findings (
                    tenant_id TEXT NOT NULL,
                    finding_id TEXT NOT NULL,
                    incident_id TEXT NOT NULL,
                    severity TEXT NOT NULL CHECK(severity IN ('medium', 'high')),
                    finding_json TEXT NOT NULL,
                    PRIMARY KEY (tenant_id, finding_id),
                    FOREIGN KEY (tenant_id, incident_id) REFERENCES incidents(tenant_id, incident_id)
                );
                CREATE TABLE IF NOT EXISTS evidence (
                    tenant_id TEXT NOT NULL,
                    finding_id TEXT NOT NULL,
                    evidence_ref TEXT NOT NULL,
                    evidence_json TEXT NOT NULL,
                    PRIMARY KEY (tenant_id, finding_id, evidence_ref),
                    FOREIGN KEY (tenant_id, finding_id) REFERENCES findings(tenant_id, finding_id)
                );
                CREATE TABLE IF NOT EXISTS audit_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    occurred_at_utc TEXT NOT NULL,
                    tenant_id TEXT,
                    event_type TEXT NOT NULL CHECK(event_type IN (
                        'authentication_failure', 'access_denial', 'protected_operation', 'request_rejected'
                    )),
                    method TEXT NOT NULL,
                    route TEXT NOT NULL,
                    outcome TEXT NOT NULL,
                    details_code TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS findings_by_tenant ON findings(tenant_id, finding_id);
                CREATE INDEX IF NOT EXISTS incidents_by_tenant ON incidents(tenant_id, generated_at_utc DESC);
                CREATE INDEX IF NOT EXISTS audit_by_time ON audit_events(occurred_at_utc, event_id);
                CREATE TABLE IF NOT EXISTS telemetry_events (
                    tenant_id TEXT NOT NULL,
                    event_id TEXT NOT NULL,
                    evidence_ref TEXT NOT NULL,
                    occurred_at_utc TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    event_json TEXT NOT NULL,
                    source_id TEXT NOT NULL CHECK(source_id = 'local_synthetic_fixture_v1'),
                    ingested_at_utc TEXT NOT NULL,
                    PRIMARY KEY (tenant_id, event_id),
                    UNIQUE (tenant_id, evidence_ref),
                    FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id)
                );
                CREATE TABLE IF NOT EXISTS telemetry_findings (
                    tenant_id TEXT NOT NULL,
                    finding_id TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('open', 'acknowledged', 'closed')),
                    severity TEXT NOT NULL CHECK(severity IN ('low', 'medium', 'high', 'critical')),
                    first_seen_utc TEXT NOT NULL,
                    last_seen_utc TEXT NOT NULL,
                    finding_json TEXT NOT NULL,
                    created_at_utc TEXT NOT NULL,
                    updated_at_utc TEXT NOT NULL,
                    PRIMARY KEY (tenant_id, finding_id),
                    FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id)
                );
                CREATE TABLE IF NOT EXISTS telemetry_finding_evidence (
                    tenant_id TEXT NOT NULL,
                    finding_id TEXT NOT NULL,
                    evidence_ref TEXT NOT NULL,
                    event_id TEXT NOT NULL,
                    PRIMARY KEY (tenant_id, finding_id, evidence_ref),
                    FOREIGN KEY (tenant_id, finding_id) REFERENCES telemetry_findings(tenant_id, finding_id),
                    FOREIGN KEY (tenant_id, event_id) REFERENCES telemetry_events(tenant_id, event_id)
                );
                CREATE TABLE IF NOT EXISTS telemetry_finding_observations (
                    tenant_id TEXT NOT NULL,
                    finding_id TEXT NOT NULL,
                    observation_hash TEXT NOT NULL,
                    observed_at_utc TEXT NOT NULL,
                    observation_json TEXT NOT NULL,
                    PRIMARY KEY (tenant_id, finding_id, observation_hash),
                    FOREIGN KEY (tenant_id, finding_id) REFERENCES telemetry_findings(tenant_id, finding_id)
                );
                CREATE TABLE IF NOT EXISTS telemetry_runs (
                    run_id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    source_id TEXT NOT NULL CHECK(source_id = 'local_synthetic_fixture_v1'),
                    status TEXT NOT NULL CHECK(status IN ('started', 'completed', 'skipped', 'failed')),
                    scheduled_at_utc TEXT NOT NULL,
                    started_at_utc TEXT NOT NULL,
                    completed_at_utc TEXT,
                    attempt INTEGER NOT NULL CHECK(attempt >= 1),
                    input_event_count INTEGER NOT NULL DEFAULT 0,
                    accepted_event_count INTEGER NOT NULL DEFAULT 0,
                    duplicate_event_count INTEGER NOT NULL DEFAULT 0,
                    finding_count INTEGER NOT NULL DEFAULT 0,
                    error_code TEXT,
                    FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id)
                );
                CREATE TABLE IF NOT EXISTS telemetry_reports (
                    tenant_id TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    report_id TEXT NOT NULL,
                    generated_at_utc TEXT NOT NULL,
                    report_json TEXT NOT NULL,
                    PRIMARY KEY (tenant_id, run_id),
                    UNIQUE (tenant_id, report_id),
                    FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id),
                    FOREIGN KEY (run_id) REFERENCES telemetry_runs(run_id)
                );
                CREATE INDEX IF NOT EXISTS telemetry_events_window
                    ON telemetry_events(tenant_id, occurred_at_utc DESC);
                CREATE INDEX IF NOT EXISTS telemetry_findings_by_tenant
                    ON telemetry_findings(tenant_id, status, severity);
                CREATE INDEX IF NOT EXISTS telemetry_runs_by_tenant
                    ON telemetry_runs(tenant_id, started_at_utc DESC);
                CREATE INDEX IF NOT EXISTS telemetry_observations_by_finding
                    ON telemetry_finding_observations(tenant_id, finding_id, observed_at_utc DESC, observation_hash);
                CREATE TABLE IF NOT EXISTS telemetry_source_status (
                    tenant_id TEXT NOT NULL,
                    source_key TEXT NOT NULL CHECK(source_key = 'synthetic_demo_site_live_logs_v1'),
                    last_attempt_at_utc TEXT NOT NULL,
                    last_success_at_utc TEXT,
                    status TEXT NOT NULL CHECK(status IN ('running', 'healthy', 'failed')),
                    input_event_count INTEGER NOT NULL DEFAULT 0 CHECK(input_event_count >= 0),
                    accepted_event_count INTEGER NOT NULL DEFAULT 0 CHECK(accepted_event_count >= 0),
                    duplicate_event_count INTEGER NOT NULL DEFAULT 0 CHECK(duplicate_event_count >= 0),
                    rejected_record_count INTEGER NOT NULL DEFAULT 0 CHECK(rejected_record_count >= 0),
                    position_sha256 TEXT,
                    position_bytes INTEGER NOT NULL DEFAULT 0 CHECK(position_bytes >= 0),
                    error_code TEXT,
                    PRIMARY KEY (tenant_id, source_key),
                    FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id)
                );
                CREATE TABLE IF NOT EXISTS website_assessment_observations (
                    tenant_id TEXT NOT NULL,
                    observation_ref TEXT NOT NULL,
                    observation_hash TEXT NOT NULL,
                    observation_json TEXT NOT NULL,
                    created_at_utc TEXT NOT NULL,
                    PRIMARY KEY (tenant_id, observation_ref),
                    UNIQUE (tenant_id, observation_hash),
                    FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id)
                );
                CREATE TABLE IF NOT EXISTS website_assessment_reports (
                    tenant_id TEXT NOT NULL,
                    report_id TEXT NOT NULL,
                    generated_at_utc TEXT NOT NULL,
                    report_metadata_json TEXT NOT NULL,
                    PRIMARY KEY (tenant_id, report_id),
                    FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id)
                );
                CREATE TABLE IF NOT EXISTS website_assessment_report_observations (
                    tenant_id TEXT NOT NULL,
                    report_id TEXT NOT NULL,
                    observation_ref TEXT NOT NULL,
                    position INTEGER NOT NULL CHECK(position >= 0),
                    PRIMARY KEY (tenant_id, report_id, observation_ref),
                    FOREIGN KEY (tenant_id, report_id)
                        REFERENCES website_assessment_reports(tenant_id, report_id) ON DELETE CASCADE,
                    FOREIGN KEY (tenant_id, observation_ref)
                        REFERENCES website_assessment_observations(tenant_id, observation_ref)
                );
                CREATE TABLE IF NOT EXISTS investigation_cases (
                    tenant_id TEXT NOT NULL,
                    case_id TEXT NOT NULL,
                    title TEXT NOT NULL CHECK(length(title) BETWEEN 1 AND 120),
                    status TEXT NOT NULL CHECK(status IN ('open', 'under_review', 'closed')),
                    created_at_utc TEXT NOT NULL,
                    updated_at_utc TEXT NOT NULL,
                    PRIMARY KEY (tenant_id, case_id),
                    FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id)
                );
                CREATE TABLE IF NOT EXISTS investigation_case_findings (
                    tenant_id TEXT NOT NULL,
                    case_id TEXT NOT NULL,
                    finding_id TEXT NOT NULL,
                    relationship TEXT NOT NULL CHECK(relationship IN ('inferred_relationship', 'analyst_conclusion')),
                    rationale TEXT NOT NULL CHECK(length(rationale) BETWEEN 1 AND 500),
                    linked_at_utc TEXT NOT NULL,
                    PRIMARY KEY (tenant_id, case_id, finding_id),
                    FOREIGN KEY (tenant_id, case_id) REFERENCES investigation_cases(tenant_id, case_id) ON DELETE CASCADE,
                    FOREIGN KEY (tenant_id, finding_id) REFERENCES telemetry_findings(tenant_id, finding_id)
                );
                CREATE TABLE IF NOT EXISTS investigation_case_evidence (
                    tenant_id TEXT NOT NULL,
                    case_id TEXT NOT NULL,
                    finding_id TEXT NOT NULL,
                    evidence_ref TEXT NOT NULL,
                    rationale TEXT NOT NULL CHECK(length(rationale) BETWEEN 1 AND 500),
                    linked_at_utc TEXT NOT NULL,
                    PRIMARY KEY (tenant_id, case_id, finding_id, evidence_ref),
                    FOREIGN KEY (tenant_id, case_id) REFERENCES investigation_cases(tenant_id, case_id) ON DELETE CASCADE,
                    FOREIGN KEY (tenant_id, finding_id, evidence_ref)
                        REFERENCES telemetry_finding_evidence(tenant_id, finding_id, evidence_ref)
                );
                CREATE TABLE IF NOT EXISTS investigation_case_context (
                    tenant_id TEXT NOT NULL,
                    case_id TEXT NOT NULL,
                    source_type TEXT NOT NULL CHECK(source_type IN ('assessment_report', 'evaluation_run')),
                    source_id TEXT NOT NULL,
                    linked_at_utc TEXT NOT NULL,
                    PRIMARY KEY (tenant_id, case_id, source_type, source_id),
                    FOREIGN KEY (tenant_id, case_id) REFERENCES investigation_cases(tenant_id, case_id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS investigation_case_history (
                    history_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tenant_id TEXT NOT NULL,
                    case_id TEXT NOT NULL,
                    occurred_at_utc TEXT NOT NULL,
                    event_type TEXT NOT NULL CHECK(event_type IN ('created', 'status_changed', 'note_added', 'finding_linked', 'evidence_linked', 'context_linked')),
                    classification TEXT NOT NULL CHECK(classification IN ('analyst_conclusion', 'unresolved_hypothesis', 'inferred_relationship', 'verified_evidence', 'context', 'case_activity')),
                    reference_id TEXT NOT NULL,
                    description TEXT NOT NULL CHECK(length(description) BETWEEN 1 AND 1000),
                    FOREIGN KEY (tenant_id, case_id) REFERENCES investigation_cases(tenant_id, case_id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS investigation_cases_by_tenant
                    ON investigation_cases(tenant_id, updated_at_utc DESC, case_id);
                CREATE INDEX IF NOT EXISTS investigation_history_by_case
                    ON investigation_case_history(tenant_id, case_id, occurred_at_utc, history_id);
                CREATE TABLE IF NOT EXISTS purple_team_scenario_runs (
                    tenant_id TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    scenario_id TEXT NOT NULL CHECK(length(scenario_id) BETWEEN 3 AND 64),
                    status TEXT NOT NULL CHECK(status IN ('NOT_RUN', 'PASSED', 'FAILED', 'ERROR', 'NOT_APPLICABLE')),
                    started_at_utc TEXT NOT NULL,
                    report_json TEXT NOT NULL,
                    PRIMARY KEY (tenant_id, run_id),
                    FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id)
                );
                CREATE INDEX IF NOT EXISTS purple_scenario_history
                    ON purple_team_scenario_runs(tenant_id, scenario_id, started_at_utc DESC, run_id DESC);
                CREATE TABLE IF NOT EXISTS purple_team_scenario_locks (
                    tenant_id TEXT PRIMARY KEY,
                    lease_token TEXT NOT NULL,
                    expires_at_utc TEXT NOT NULL,
                    FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id)
                );
                """
            )
            connection.execute("PRAGMA user_version = 6")

    LIVE_SOURCE_KEY = "synthetic_demo_site_live_logs_v1"

    def start_live_source_attempt(self, tenant_id: str) -> None:
        if not TENANT_PATTERN.fullmatch(tenant_id):
            raise ValueError("invalid synthetic tenant")
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO telemetry_source_status
                   (tenant_id, source_key, last_attempt_at_utc, status)
                   VALUES (?, ?, ?, 'running')
                   ON CONFLICT(tenant_id, source_key) DO UPDATE SET
                     last_attempt_at_utc = excluded.last_attempt_at_utc,
                     status = 'running', error_code = NULL""",
                (tenant_id, self.LIVE_SOURCE_KEY, _utc_now()),
            )

    def finish_live_source_attempt(
        self, tenant_id: str, *, status: str, input_count: int = 0,
        accepted_count: int = 0, duplicate_count: int = 0, rejected_count: int = 0,
        position_sha256: str | None = None, position_bytes: int = 0,
        error_code: str | None = None,
    ) -> None:
        if not TENANT_PATTERN.fullmatch(tenant_id) or status not in {"healthy", "failed"}:
            raise ValueError("invalid live source status")
        if error_code not in {None, "source_invalid", "processing_error", "store_error"}:
            raise ValueError("invalid live source error category")
        if min(input_count, accepted_count, duplicate_count, rejected_count, position_bytes) < 0:
            raise ValueError("invalid live source counters")
        if position_sha256 is not None and not re.fullmatch(r"[0-9a-f]{64}", position_sha256):
            raise ValueError("invalid source position digest")
        with self._connect() as connection:
            updated = connection.execute(
                """UPDATE telemetry_source_status SET status = ?,
                   last_success_at_utc = CASE WHEN ? = 'healthy' THEN ? ELSE last_success_at_utc END,
                   input_event_count = ?, accepted_event_count = ?, duplicate_event_count = ?,
                   rejected_record_count = ?, position_sha256 = COALESCE(?, position_sha256),
                   position_bytes = CASE WHEN ? IS NULL THEN position_bytes ELSE ? END, error_code = ?
                   WHERE tenant_id = ? AND source_key = ?""",
                (status, status, _utc_now(), input_count, accepted_count, duplicate_count,
                 rejected_count, position_sha256, position_sha256, position_bytes,
                 error_code, tenant_id, self.LIVE_SOURCE_KEY),
            )
            if updated.rowcount != 1:
                raise ValueError("live source attempt was not started")

    def live_source_status(self, tenant_id: str) -> dict[str, Any] | None:
        if not TENANT_PATTERN.fullmatch(tenant_id):
            raise ValueError("invalid synthetic tenant")
        with self._connect() as connection:
            row = connection.execute(
                """SELECT last_attempt_at_utc, last_success_at_utc, status, input_event_count,
                          accepted_event_count, duplicate_event_count, rejected_record_count,
                          position_sha256, position_bytes, error_code
                   FROM telemetry_source_status WHERE tenant_id = ? AND source_key = ?""",
                (tenant_id, self.LIVE_SOURCE_KEY),
            ).fetchone()
        return dict(row) if row is not None else None

    def seed_tenant(self, tenant_id: str, report: IncidentReport) -> str:
        report = IncidentReport.model_validate(report.model_dump(mode="python"))
        digest = hashlib.sha256(f"{tenant_id}\0{report.report_id}".encode()).hexdigest()[:12]
        incident_id = f"incident-{digest}"
        evidence_by_ref = {item.evidence_ref: item for item in report.evidence_catalog}
        with self._connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO tenants VALUES (?, 'synthetic', ?)", (tenant_id, _utc_now())
            )
            connection.execute(
                """INSERT OR IGNORE INTO incidents
                   (tenant_id, incident_id, report_id, dataset_id, generated_at_utc, report_json)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (tenant_id, incident_id, report.report_id, report.dataset_id,
                 report.generated_at_utc.isoformat(), report.model_dump_json()),
            )
            for finding in report.findings:
                connection.execute(
                    """INSERT OR IGNORE INTO findings
                       (tenant_id, finding_id, incident_id, severity, finding_json)
                       VALUES (?, ?, ?, ?, ?)""",
                    (tenant_id, finding.finding_id, incident_id, finding.severity.value, finding.model_dump_json()),
                )
                for evidence_ref in finding.evidence_refs:
                    evidence = evidence_by_ref[evidence_ref]
                    connection.execute(
                        """INSERT OR IGNORE INTO evidence
                           (tenant_id, finding_id, evidence_ref, evidence_json)
                           VALUES (?, ?, ?, ?)""",
                        (tenant_id, finding.finding_id, evidence_ref, evidence.model_dump_json()),
                    )
        return incident_id

    def ping(self) -> bool:
        with self._connect() as connection:
            connection.execute("SELECT 1").fetchone()
        return True

    def list_findings(self, tenant_id: str) -> list[Finding]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT finding_json FROM findings WHERE tenant_id = ? ORDER BY finding_id", (tenant_id,)
            ).fetchall()
        return [Finding.model_validate_json(row["finding_json"]) for row in rows]

    def get_evidence(self, tenant_id: str, finding_id: str) -> list[EvidenceReferenceResponse] | None:
        with self._connect() as connection:
            exists = connection.execute(
                "SELECT 1 FROM findings WHERE tenant_id = ? AND finding_id = ?", (tenant_id, finding_id)
            ).fetchone()
            if exists is None:
                return None
            rows = connection.execute(
                """SELECT evidence_json FROM evidence
                   WHERE tenant_id = ? AND finding_id = ? ORDER BY evidence_ref""",
                (tenant_id, finding_id),
            ).fetchall()
        return [EvidenceReferenceResponse.model_validate_json(row["evidence_json"]) for row in rows]

    def list_incidents(self, tenant_id: str) -> list[IncidentSummary]:
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT incident_id, report_id, dataset_id, generated_at_utc, report_json
                   FROM incidents WHERE tenant_id = ? ORDER BY generated_at_utc DESC, incident_id""",
                (tenant_id,),
            ).fetchall()
        summaries = []
        for row in rows:
            report = IncidentReport.model_validate_json(row["report_json"])
            summaries.append(IncidentSummary(
                incident_id=row["incident_id"], report_id=row["report_id"], dataset_id=row["dataset_id"],
                data_classification="synthetic", label=report.label,
                generated_at_utc=row["generated_at_utc"], finding_count=len(report.findings),
                high_severity_count=sum(item.severity.value == "high" for item in report.findings),
            ))
        return summaries

    def get_incident_report(self, tenant_id: str, incident_id: str) -> IncidentReportResponse | None:
        with self._connect() as connection:
            row = connection.execute(
                """SELECT incident_id, report_json FROM incidents
                   WHERE tenant_id = ? AND incident_id = ?""", (tenant_id, incident_id)
            ).fetchone()
        if row is None:
            return None
        report = IncidentReport.model_validate_json(row["report_json"])
        return IncidentReportResponse(
            data_classification="synthetic", label=report.label, tenant_id=tenant_id,
            incident_id=row["incident_id"], report=report,
        )

    def record_audit(
        self, *, tenant_id: str | None, event_type: str, method: str,
        route: str, outcome: str, details_code: str,
    ) -> None:
        # Only fixed route names and categorical details are passed here; credentials and request bodies are omitted.
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO audit_events
                   (occurred_at_utc, tenant_id, event_type, method, route, outcome, details_code)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (_utc_now(), tenant_id, event_type, method[:12], route[:100], outcome[:24], details_code[:80]),
            )

    def audit_snapshot(self) -> list[dict[str, Any]]:
        """Test and local operator helper; deliberately not exposed as an HTTP endpoint."""
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT event_id, occurred_at_utc, tenant_id, event_type, method, route, outcome, details_code "
                "FROM audit_events ORDER BY event_id"
            ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def _validate_case_tenant(tenant_id: str) -> None:
        if not TENANT_PATTERN.fullmatch(tenant_id):
            raise ValueError("invalid synthetic tenant")

    @staticmethod
    def _append_case_history(connection, tenant_id: str, case_id: str, event_type: str,
                             classification: str, reference_id: str, description: str) -> None:
        count = connection.execute(
            "SELECT count(*) FROM investigation_case_history WHERE tenant_id = ? AND case_id = ?",
            (tenant_id, case_id),
        ).fetchone()[0]
        if count >= 2000:
            raise ValueError("investigation history limit reached")
        connection.execute(
            """INSERT INTO investigation_case_history
               (tenant_id, case_id, occurred_at_utc, event_type, classification, reference_id, description)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (tenant_id, case_id, _utc_now(), event_type, classification, reference_id, description),
        )

    def create_investigation_case(self, tenant_id: str, request: CreateCaseRequest) -> str:
        self._validate_case_tenant(tenant_id)
        request = CreateCaseRequest.model_validate(request.model_dump())
        now = _utc_now()
        with self._connect() as connection:
            count = connection.execute(
                "SELECT count(*) FROM investigation_cases WHERE tenant_id = ?", (tenant_id,),
            ).fetchone()[0]
            if count >= 200:
                raise ValueError("investigation case limit reached")
            connection.execute(
                "INSERT OR IGNORE INTO tenants VALUES (?, 'synthetic', ?)", (tenant_id, now),
            )
            case_id = "case-" + uuid.uuid4().hex[:16]
            connection.execute(
                "INSERT INTO investigation_cases VALUES (?, ?, ?, 'open', ?, ?)",
                (tenant_id, case_id, request.title, now, now),
            )
            self._append_case_history(connection, tenant_id, case_id, "created", "case_activity",
                                      case_id, "Investigation case created.")
        return case_id

    def list_investigation_cases(self, tenant_id: str, *, status: str | None = None,
                                 search: str | None = None) -> list[InvestigationCaseSummary]:
        self._validate_case_tenant(tenant_id)
        clauses = ["c.tenant_id = ?"]
        args: list[Any] = [tenant_id]
        if status is not None:
            if status not in {"open", "under_review", "closed"}:
                raise ValueError("invalid investigation status")
            clauses.append("c.status = ?")
            args.append(status)
        if search:
            escaped = search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            clauses.append("c.title LIKE ? ESCAPE '\\'")
            args.append(f"%{escaped}%")
        with self._connect() as connection:
            rows = connection.execute(
                f"""SELECT c.case_id, c.title, c.status, c.created_at_utc, c.updated_at_utc,
                           (SELECT count(*) FROM investigation_case_findings f
                             WHERE f.tenant_id=c.tenant_id AND f.case_id=c.case_id) AS finding_count,
                           (SELECT count(*) FROM investigation_case_evidence e
                             WHERE e.tenant_id=c.tenant_id AND e.case_id=c.case_id) AS evidence_count
                    FROM investigation_cases c WHERE {' AND '.join(clauses)}
                    ORDER BY c.updated_at_utc DESC, c.case_id LIMIT 200""", args,
            ).fetchall()
        return [InvestigationCaseSummary(**dict(row)) for row in rows]

    def get_investigation_case(self, tenant_id: str, case_id: str) -> dict[str, Any] | None:
        self._validate_case_tenant(tenant_id)
        with self._connect() as connection:
            row = connection.execute(
                """SELECT case_id, title, status, created_at_utc, updated_at_utc
                   FROM investigation_cases WHERE tenant_id = ? AND case_id = ?""",
                (tenant_id, case_id),
            ).fetchone()
            if row is None:
                return None
            findings = connection.execute(
                """SELECT finding_id, relationship, rationale, linked_at_utc
                   FROM investigation_case_findings WHERE tenant_id = ? AND case_id = ? ORDER BY finding_id""",
                (tenant_id, case_id),
            ).fetchall()
            evidence = connection.execute(
                """SELECT finding_id, evidence_ref, rationale, linked_at_utc
                   FROM investigation_case_evidence WHERE tenant_id = ? AND case_id = ?
                   ORDER BY linked_at_utc, evidence_ref LIMIT 500""", (tenant_id, case_id),
            ).fetchall()
            contexts = connection.execute(
                """SELECT source_type, source_id, linked_at_utc FROM investigation_case_context
                   WHERE tenant_id = ? AND case_id = ? ORDER BY linked_at_utc, source_type, source_id""",
                (tenant_id, case_id),
            ).fetchall()
            history = connection.execute(
                """SELECT occurred_at_utc, event_type, classification, reference_id, description
                   FROM investigation_case_history WHERE tenant_id = ? AND case_id = ?
                   ORDER BY occurred_at_utc, history_id LIMIT 2000""", (tenant_id, case_id),
            ).fetchall()
            finding_rows = connection.execute(
                """SELECT f.finding_json FROM telemetry_findings f
                   JOIN investigation_case_findings l
                     ON l.tenant_id=f.tenant_id AND l.finding_id=f.finding_id
                   WHERE l.tenant_id = ? AND l.case_id = ? ORDER BY f.finding_id""", (tenant_id, case_id),
            ).fetchall()
            linked_evidence = connection.execute(
                """SELECT DISTINCT e.event_json FROM telemetry_events e
                   JOIN telemetry_finding_evidence fe
                     ON fe.tenant_id=e.tenant_id AND fe.event_id=e.event_id
                   JOIN investigation_case_findings l
                     ON l.tenant_id=fe.tenant_id AND l.finding_id=fe.finding_id
                   WHERE l.tenant_id = ? AND l.case_id = ?
                   ORDER BY e.occurred_at_utc, e.event_id LIMIT 10000""",
                (tenant_id, case_id),
            ).fetchall()
        return {
            "case": dict(row), "findings": [dict(item) for item in findings],
            "evidence": [dict(item) for item in evidence], "contexts": [dict(item) for item in contexts],
            "history": [dict(item) for item in history],
            "finding_records": [item["finding_json"] for item in finding_rows],
            "evidence_records": [item["event_json"] for item in linked_evidence],
        }

    def add_case_finding(self, tenant_id: str, case_id: str, request: AddFindingLinkRequest) -> bool:
        self._validate_case_tenant(tenant_id)
        request = AddFindingLinkRequest.model_validate(request.model_dump())
        with self._connect() as connection:
            count = connection.execute(
                "SELECT count(*) FROM investigation_case_findings WHERE tenant_id=? AND case_id=?",
                (tenant_id, case_id),
            ).fetchone()[0]
            if connection.execute("SELECT 1 FROM investigation_cases WHERE tenant_id=? AND case_id=?",
                                   (tenant_id, case_id)).fetchone() is None:
                return False
            if connection.execute("SELECT 1 FROM telemetry_findings WHERE tenant_id=? AND finding_id=?",
                                  (tenant_id, request.finding_id)).fetchone() is None:
                return False
            existing = connection.execute(
                "SELECT relationship, rationale FROM investigation_case_findings WHERE tenant_id=? AND case_id=? AND finding_id=?",
                (tenant_id, case_id, request.finding_id),
            ).fetchone()
            if existing is not None:
                if existing["relationship"] != request.relationship or existing["rationale"] != request.rationale:
                    raise ValueError("finding association already exists with different details")
                return True
            if count >= 100:
                raise ValueError("case finding limit reached")
            connection.execute(
                """INSERT INTO investigation_case_findings VALUES (?, ?, ?, ?, ?, ?)""",
                (tenant_id, case_id, request.finding_id, request.relationship, request.rationale, _utc_now()),
            )
            self._append_case_history(connection, tenant_id, case_id, "finding_linked", request.relationship,
                                      request.finding_id, request.rationale)
            connection.execute("UPDATE investigation_cases SET updated_at_utc=? WHERE tenant_id=? AND case_id=?",
                               (_utc_now(), tenant_id, case_id))
        return True

    def add_case_evidence(self, tenant_id: str, case_id: str, request: AddEvidenceLinkRequest) -> bool:
        self._validate_case_tenant(tenant_id)
        request = AddEvidenceLinkRequest.model_validate(request.model_dump())
        with self._connect() as connection:
            if connection.execute("SELECT 1 FROM investigation_case_findings WHERE tenant_id=? AND case_id=? AND finding_id=?",
                                  (tenant_id, case_id, request.finding_id)).fetchone() is None:
                return False
            if connection.execute("""SELECT 1 FROM telemetry_finding_evidence
                                    WHERE tenant_id=? AND finding_id=? AND evidence_ref=?""",
                                  (tenant_id, request.finding_id, request.evidence_ref)).fetchone() is None:
                return False
            count = connection.execute(
                "SELECT count(*) FROM investigation_case_evidence WHERE tenant_id=? AND case_id=?",
                (tenant_id, case_id),
            ).fetchone()[0]
            existing = connection.execute(
                """SELECT rationale FROM investigation_case_evidence
                   WHERE tenant_id=? AND case_id=? AND finding_id=? AND evidence_ref=?""",
                (tenant_id, case_id, request.finding_id, request.evidence_ref),
            ).fetchone()
            if existing is not None:
                if existing["rationale"] != request.rationale:
                    raise ValueError("evidence association already exists with different details")
                return True
            if count >= 500:
                raise ValueError("case evidence limit reached")
            connection.execute(
                "INSERT INTO investigation_case_evidence VALUES (?, ?, ?, ?, ?, ?)",
                (tenant_id, case_id, request.finding_id, request.evidence_ref, request.rationale, _utc_now()),
            )
            self._append_case_history(connection, tenant_id, case_id, "evidence_linked", "verified_evidence",
                                      request.evidence_ref, request.rationale)
            connection.execute("UPDATE investigation_cases SET updated_at_utc=? WHERE tenant_id=? AND case_id=?",
                               (_utc_now(), tenant_id, case_id))
        return True

    def add_case_note(self, tenant_id: str, case_id: str, request: AddAnalystNoteRequest) -> bool:
        self._validate_case_tenant(tenant_id)
        request = AddAnalystNoteRequest.model_validate(request.model_dump())
        with self._connect() as connection:
            if connection.execute("SELECT 1 FROM investigation_cases WHERE tenant_id=? AND case_id=?",
                                  (tenant_id, case_id)).fetchone() is None:
                return False
            note_count = connection.execute(
                """SELECT count(*) FROM investigation_case_history
                   WHERE tenant_id=? AND case_id=? AND event_type='note_added'""", (tenant_id, case_id),
            ).fetchone()[0]
            if note_count >= 500:
                raise ValueError("case note limit reached")
            self._append_case_history(connection, tenant_id, case_id, "note_added", request.classification,
                                      case_id, request.text)
            connection.execute("UPDATE investigation_cases SET updated_at_utc=? WHERE tenant_id=? AND case_id=?",
                               (_utc_now(), tenant_id, case_id))
        return True

    def update_case_status(self, tenant_id: str, case_id: str, request: UpdateCaseStatusRequest) -> bool:
        self._validate_case_tenant(tenant_id)
        request = UpdateCaseStatusRequest.model_validate(request.model_dump())
        now = _utc_now()
        with self._connect() as connection:
            row = connection.execute("SELECT status FROM investigation_cases WHERE tenant_id=? AND case_id=?",
                                     (tenant_id, case_id)).fetchone()
            if row is None:
                return False
            if row["status"] == request.status:
                return True
            connection.execute("UPDATE investigation_cases SET status=?, updated_at_utc=? WHERE tenant_id=? AND case_id=?",
                               (request.status, now, tenant_id, case_id))
            self._append_case_history(connection, tenant_id, case_id, "status_changed", "case_activity",
                                      request.status, f"Case status changed from {row['status']} to {request.status}.")
        return True

    def add_case_context(self, tenant_id: str, case_id: str, request: AddContextRequest,
                         *, generated_at_utc: str) -> bool:
        self._validate_case_tenant(tenant_id)
        request = AddContextRequest.model_validate(request.model_dump())
        with self._connect() as connection:
            if connection.execute("SELECT 1 FROM investigation_cases WHERE tenant_id=? AND case_id=?",
                                  (tenant_id, case_id)).fetchone() is None:
                return False
            if request.source_type == "assessment_report" and connection.execute(
                "SELECT 1 FROM website_assessment_reports WHERE tenant_id=? AND report_id=?",
                (tenant_id, request.source_id),
            ).fetchone() is None:
                return False
            count = connection.execute(
                "SELECT count(*) FROM investigation_case_context WHERE tenant_id=? AND case_id=?",
                (tenant_id, case_id),
            ).fetchone()[0]
            existing = connection.execute(
                """SELECT 1 FROM investigation_case_context WHERE tenant_id=? AND case_id=?
                   AND source_type=? AND source_id=?""",
                (tenant_id, case_id, request.source_type, request.source_id),
            ).fetchone()
            if existing is not None:
                return True
            if count >= 40:
                raise ValueError("case context limit reached")
            connection.execute("INSERT INTO investigation_case_context VALUES (?, ?, ?, ?, ?)",
                               (tenant_id, case_id, request.source_type, request.source_id, _utc_now()))
            self._append_case_history(connection, tenant_id, case_id, "context_linked", "context",
                                      request.source_id, f"Linked {request.source_type} context generated at {generated_at_utc}.")
            connection.execute("UPDATE investigation_cases SET updated_at_utc=? WHERE tenant_id=? AND case_id=?",
                               (_utc_now(), tenant_id, case_id))
        return True

    def save_purple_scenario_run(self, tenant_id: str, report: ScenarioExecutionReport) -> None:
        """Persist a bounded scenario report for the fixed local synthetic tenant."""
        if not TENANT_PATTERN.fullmatch(tenant_id):
            raise ValueError("invalid synthetic tenant")
        report = ScenarioExecutionReport.model_validate(report.model_dump(mode="python"))
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "INSERT OR IGNORE INTO tenants VALUES (?, 'synthetic', ?)", (tenant_id, _utc_now())
            )
            connection.execute(
                """INSERT INTO purple_team_scenario_runs
                   (tenant_id, run_id, scenario_id, status, started_at_utc, report_json)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (tenant_id, report.run_id, report.scenario_id, report.status,
                 report.started_at_utc.isoformat(), report.model_dump_json()),
            )
            connection.execute(
                """DELETE FROM purple_team_scenario_runs WHERE tenant_id=? AND run_id NOT IN
                   (SELECT run_id FROM purple_team_scenario_runs WHERE tenant_id=?
                    ORDER BY started_at_utc DESC, run_id DESC LIMIT 100)""",
                (tenant_id, tenant_id),
            )
            connection.execute(
                """INSERT INTO audit_events (occurred_at_utc, tenant_id, event_type, method, route, outcome, details_code)
                   VALUES (?, ?, 'protected_operation', 'LOCAL', 'purple_team.scenario.run', ?, ?)""",
                (_utc_now(), tenant_id, "completed" if report.status != "ERROR" else "failed", report.status.lower()),
            )

    def acquire_purple_scenario_slot(self, tenant_id: str, lease_token: str, *, lease_seconds: int = 30) -> bool:
        """Claim the single tenant execution slot across local processes."""
        if not TENANT_PATTERN.fullmatch(tenant_id) or not re.fullmatch(r"[a-f0-9]{32}", lease_token):
            raise ValueError("invalid synthetic scenario lease")
        now = datetime.now(timezone.utc)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "INSERT OR IGNORE INTO tenants VALUES (?, 'synthetic', ?)", (tenant_id, now.isoformat())
            )
            row = connection.execute(
                "SELECT expires_at_utc FROM purple_team_scenario_locks WHERE tenant_id=?", (tenant_id,),
            ).fetchone()
            if row is not None and row["expires_at_utc"] > now.isoformat():
                return False
            expires = (now + timedelta(seconds=lease_seconds)).isoformat()
            connection.execute(
                """INSERT INTO purple_team_scenario_locks VALUES (?, ?, ?)
                   ON CONFLICT(tenant_id) DO UPDATE SET lease_token=excluded.lease_token,
                   expires_at_utc=excluded.expires_at_utc""",
                (tenant_id, lease_token, expires),
            )
        return True

    def release_purple_scenario_slot(self, tenant_id: str, lease_token: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM purple_team_scenario_locks WHERE tenant_id=? AND lease_token=?",
                (tenant_id, lease_token),
            )

    def latest_purple_scenario_run(self, tenant_id: str, scenario_id: str) -> ScenarioExecutionReport | None:
        if not TENANT_PATTERN.fullmatch(tenant_id):
            raise ValueError("invalid synthetic tenant")
        with self._connect() as connection:
            row = connection.execute(
                """SELECT report_json FROM purple_team_scenario_runs
                   WHERE tenant_id=? AND scenario_id=?
                   ORDER BY started_at_utc DESC, run_id DESC LIMIT 1""",
                (tenant_id, scenario_id),
            ).fetchone()
        return ScenarioExecutionReport.model_validate_json(row["report_json"]) if row else None

    def list_purple_scenario_runs(self, tenant_id: str, *, limit: int = 20) -> list[ScenarioExecutionReport]:
        """Return a bounded, tenant-scoped history of stored synthetic scenario runs."""
        if not TENANT_PATTERN.fullmatch(tenant_id) or not 1 <= limit <= 20:
            raise ValueError("invalid scenario history request")
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT report_json FROM purple_team_scenario_runs WHERE tenant_id=?
                   ORDER BY started_at_utc DESC, run_id DESC LIMIT ?""",
                (tenant_id, limit),
            ).fetchall()
        return [ScenarioExecutionReport.model_validate_json(row["report_json"]) for row in rows]

    def save_assessment_report(self, tenant_id: str, report: AssessmentReport) -> AssessmentReport:
        """Store validated local assessment evidence and audit it in one transaction."""
        if not TENANT_PATTERN.fullmatch(tenant_id):
            raise ValueError("invalid synthetic tenant")
        report = AssessmentReport.validate_for_storage(report.model_dump(mode="python"))
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "INSERT OR IGNORE INTO tenants VALUES (?, 'synthetic', ?)", (tenant_id, _utc_now())
            )
            previous = connection.execute(
                """SELECT report_id, report_metadata_json FROM website_assessment_reports
                   WHERE tenant_id = ? ORDER BY generated_at_utc DESC, report_id DESC LIMIT 1""",
                (tenant_id,),
            ).fetchone()
            previous_id = None
            previous_issues: tuple[AssessmentIssue, ...] = ()
            if previous is not None:
                try:
                    metadata = json.loads(previous["report_metadata_json"])
                    previous_issues = tuple(AssessmentIssue.model_validate(item)
                                            for item in metadata.get("inferred_risks", []))
                    previous_id = previous["report_id"]
                except (TypeError, ValueError, json.JSONDecodeError, ValidationError):
                    # Invalid/legacy-incomplete history cannot serve as a comparison baseline.
                    previous_id = None
                    previous_issues = ()
            report = report.model_copy(update={
                "comparison": compare_assessment_reports(report, previous_id, previous_issues),
            })
            report = AssessmentReport.validate_for_storage(report.model_dump(mode="python"))
            metadata_json = json.dumps(
                report.model_dump(mode="json", exclude={"raw_observations"}),
                sort_keys=True, separators=(",", ":"),
            )
            for observation in report.raw_observations:
                digest = assessment_observation_digest(observation)
                observation_ref = assessment_observation_reference(observation)
                connection.execute(
                    """INSERT OR IGNORE INTO website_assessment_observations
                       (tenant_id, observation_ref, observation_hash, observation_json, created_at_utc)
                       VALUES (?, ?, ?, ?, ?)""",
                    (tenant_id, observation_ref, digest, observation.model_dump_json(), _utc_now()),
                )
                stored = connection.execute(
                    """SELECT observation_ref, observation_hash FROM website_assessment_observations
                       WHERE tenant_id = ? AND (observation_ref = ? OR observation_hash = ?)""",
                    (tenant_id, observation_ref, digest),
                ).fetchone()
                if stored is None or stored["observation_ref"] != observation_ref or stored["observation_hash"] != digest:
                    raise ValueError("assessment observation identity conflict")
            connection.execute(
                """INSERT INTO website_assessment_reports
                   (tenant_id, report_id, generated_at_utc, report_metadata_json)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(tenant_id, report_id) DO UPDATE SET
                     generated_at_utc = excluded.generated_at_utc,
                     report_metadata_json = excluded.report_metadata_json""",
                (tenant_id, report.report_id, report.generated_at_utc.isoformat(), metadata_json),
            )
            stored_report = connection.execute(
                "SELECT 1 FROM website_assessment_reports WHERE tenant_id = ? AND report_id = ?",
                (tenant_id, report.report_id),
            ).fetchone()
            if stored_report is None:
                raise ValueError("assessment report could not be stored")
            for position, observation in enumerate(report.raw_observations):
                connection.execute(
                    """INSERT OR IGNORE INTO website_assessment_report_observations
                       (tenant_id, report_id, observation_ref, position) VALUES (?, ?, ?, ?)""",
                    (tenant_id, report.report_id, assessment_observation_reference(observation), position),
                )
            connection.execute(
                """DELETE FROM website_assessment_reports WHERE tenant_id = ? AND report_id NOT IN (
                     SELECT report_id FROM website_assessment_reports WHERE tenant_id = ?
                     ORDER BY generated_at_utc DESC, report_id DESC LIMIT 20)""",
                (tenant_id, tenant_id),
            )
            connection.execute(
                """DELETE FROM website_assessment_observations WHERE tenant_id = ? AND observation_ref NOT IN (
                     SELECT observation_ref FROM website_assessment_report_observations WHERE tenant_id = ?)""",
                (tenant_id, tenant_id),
            )
            connection.execute(
                """INSERT INTO audit_events
                   (occurred_at_utc, tenant_id, event_type, method, route, outcome, details_code)
                   VALUES (?, ?, 'protected_operation', 'LOCAL', 'assessment.report.store', 'success', 'assessment_report_saved')""",
                (_utc_now(), tenant_id),
            )
        return report

    def latest_assessment_report(self, tenant_id: str) -> AssessmentReport | None:
        if not TENANT_PATTERN.fullmatch(tenant_id):
            raise ValueError("invalid synthetic tenant")
        with self._connect() as connection:
            row = connection.execute(
                """SELECT report_id, report_metadata_json FROM website_assessment_reports
                   WHERE tenant_id = ? ORDER BY generated_at_utc DESC, report_id DESC LIMIT 1""",
                (tenant_id,),
            ).fetchone()
            if row is None:
                return None
            observation_rows = connection.execute(
                """SELECT o.observation_json FROM website_assessment_report_observations r
                   JOIN website_assessment_observations o
                     ON o.tenant_id = r.tenant_id AND o.observation_ref = r.observation_ref
                   WHERE r.tenant_id = ? AND r.report_id = ? ORDER BY r.position""",
                (tenant_id, row["report_id"]),
            ).fetchall()
        metadata = json.loads(row["report_metadata_json"])
        observations = [AssessmentObservation.model_validate_json(item["observation_json"]) for item in observation_rows]
        return AssessmentReport.validate_for_storage({**metadata, "raw_observations": observations})

    def assessment_report_history(self, tenant_id: str, *, limit: int = 20) -> list[dict[str, Any]]:
        """Project only bounded summary fields from the tenant's retained assessment history."""
        if not TENANT_PATTERN.fullmatch(tenant_id) or not 1 <= limit <= 20:
            raise ValueError("invalid assessment history request")
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT report_id, generated_at_utc, report_metadata_json FROM website_assessment_reports
                   WHERE tenant_id=? ORDER BY generated_at_utc DESC, report_id DESC LIMIT ?""",
                (tenant_id, limit),
            ).fetchall()
        history: list[dict[str, Any]] = []
        for row in rows:
            metadata = json.loads(row["report_metadata_json"])
            if (not isinstance(metadata, dict) or metadata.get("report_id") != row["report_id"]
                    or not isinstance(metadata.get("inferred_risks"), list)
                    or not isinstance(metadata.get("confirmed_findings"), list)
                    or (metadata.get("comparison") is not None and not isinstance(metadata.get("comparison"), dict))):
                raise ValueError("stored assessment history is invalid")
            comparison = metadata.get("comparison")
            if comparison is not None:
                comparison = AssessmentRunComparison.model_validate(comparison)
            history.append({
                "report_id": row["report_id"],
                "generated_at_utc": row["generated_at_utc"],
                "inferred_risk_count": len(metadata.get("inferred_risks", [])),
                "confirmed_finding_count": len(metadata.get("confirmed_findings", [])),
                "comparison_status": comparison.status if comparison else None,
                "previous_report_id": comparison.previous_report_id if comparison else None,
                "newly_introduced_count": len(comparison.newly_introduced) if comparison else 0,
                "resolved_count": len(comparison.resolved) if comparison else 0,
            })
        return history

    def assessment_report_time(self, tenant_id: str, report_id: str) -> str | None:
        self._validate_case_tenant(tenant_id)
        with self._connect() as connection:
            row = connection.execute(
                "SELECT generated_at_utc FROM website_assessment_reports WHERE tenant_id=? AND report_id=?",
                (tenant_id, report_id),
            ).fetchone()
        return row["generated_at_utc"] if row else None

    def assessment_report_time(self, tenant_id: str, report_id: str) -> str | None:
        self._validate_case_tenant(tenant_id)
        with self._connect() as connection:
            row = connection.execute(
                "SELECT generated_at_utc FROM website_assessment_reports WHERE tenant_id=? AND report_id=?",
                (tenant_id, report_id),
            ).fetchone()
        return row["generated_at_utc"] if row else None

    def start_telemetry_run(
        self, *, run_id: str, tenant_id: str, source_id: str,
        scheduled_at_utc: str, attempt: int,
    ) -> None:
        if not TENANT_PATTERN.fullmatch(tenant_id):
            raise ValueError("invalid synthetic tenant")
        now = _utc_now()
        with self._connect() as connection:
            self._prune_telemetry_history(connection, tenant_id, max_runs=MAX_RETAINED_RUNS_PER_TENANT - 1)
            connection.execute(
                """INSERT INTO telemetry_runs
                   (run_id, tenant_id, source_id, status, scheduled_at_utc, started_at_utc, attempt)
                   VALUES (?, ?, ?, 'started', ?, ?, ?)""",
                (run_id, tenant_id, source_id, scheduled_at_utc, now, attempt),
            )

    def skip_telemetry_run(
        self, *, run_id: str, tenant_id: str, source_id: str, scheduled_at_utc: str,
        details_code: str = "overlap",
    ) -> None:
        if not TENANT_PATTERN.fullmatch(tenant_id):
            raise ValueError("invalid synthetic tenant")
        now = _utc_now()
        with self._connect() as connection:
            self._prune_telemetry_history(connection, tenant_id, max_runs=MAX_RETAINED_RUNS_PER_TENANT - 1)
            connection.execute(
                """INSERT INTO telemetry_runs
                   (run_id, tenant_id, source_id, status, scheduled_at_utc, started_at_utc,
                    completed_at_utc, attempt, error_code)
                   VALUES (?, ?, ?, 'skipped', ?, ?, ?, 1, ?)""",
                (run_id, tenant_id, source_id, scheduled_at_utc, now, now, details_code[:80]),
            )

    def fail_telemetry_run(self, run_id: str, error_code: str) -> None:
        with self._connect() as connection:
            row = connection.execute("SELECT tenant_id FROM telemetry_runs WHERE run_id = ?", (run_id,)).fetchone()
            connection.execute(
                """UPDATE telemetry_runs SET status = 'failed', completed_at_utc = ?, error_code = ?
                   WHERE run_id = ? AND status = 'started'""",
                (_utc_now(), error_code[:80], run_id),
            )
            if row is not None:
                self._prune_telemetry_history(connection, row["tenant_id"])

    @staticmethod
    def _prune_telemetry_history(
        connection: sqlite3.Connection, tenant_id: str, *, max_runs: int = MAX_RETAINED_RUNS_PER_TENANT,
    ) -> None:
        """Keep bounded run/report and per-finding observation history; never touches audit rows."""
        retained_runs = max(0, max_runs)
        connection.execute(
            """DELETE FROM telemetry_reports WHERE tenant_id = ? AND run_id NOT IN (
                 SELECT run_id FROM telemetry_runs WHERE tenant_id = ?
                 ORDER BY started_at_utc DESC, run_id DESC LIMIT ?
               )""", (tenant_id, tenant_id, retained_runs),
        )
        connection.execute(
            """DELETE FROM telemetry_runs WHERE tenant_id = ? AND run_id NOT IN (
                 SELECT run_id FROM telemetry_runs WHERE tenant_id = ?
                 ORDER BY started_at_utc DESC, run_id DESC LIMIT ?
               )""", (tenant_id, tenant_id, retained_runs),
        )
        connection.execute(
            """DELETE FROM telemetry_finding_observations AS old
               WHERE old.tenant_id = ? AND (
                 SELECT COUNT(*) FROM telemetry_finding_observations AS newer
                 WHERE newer.tenant_id = old.tenant_id AND newer.finding_id = old.finding_id
                   AND (newer.observed_at_utc > old.observed_at_utc
                     OR (newer.observed_at_utc = old.observed_at_utc
                         AND newer.observation_hash > old.observation_hash))
               ) >= ?""", (tenant_id, MAX_RETAINED_OBSERVATIONS_PER_FINDING),
        )

    def complete_telemetry_cycle(
        self, *, run_id: str, tenant_id: str, source_id: str,
        batch: SyntheticTelemetryBatch, live_source_position_sha256: str | None = None,
        live_source_position_bytes: int | None = None,
    ) -> TelemetryReport:
        """Atomically append events, finding observations, report, and completed run state."""
        if not TENANT_PATTERN.fullmatch(tenant_id):
            raise ValueError("invalid synthetic tenant")
        if source_id != "local_synthetic_fixture_v1" or batch.source_id != source_id:
            raise ValueError("unrecognized synthetic source")
        if (live_source_position_sha256 is None) != (live_source_position_bytes is None):
            raise ValueError("incomplete live source position")
        if live_source_position_sha256 is not None and (
            not re.fullmatch(r"[0-9a-f]{64}", live_source_position_sha256)
            or live_source_position_bytes is None or live_source_position_bytes < 0
        ):
            raise ValueError("invalid live source position")
        events, _duplicate_in_batch = normalize_and_deduplicate(batch)
        input_count = len(batch.events)
        with self._connect() as connection:
            run = connection.execute(
                "SELECT tenant_id, status, source_id FROM telemetry_runs WHERE run_id = ?", (run_id,)
            ).fetchone()
            if run is None or run["tenant_id"] != tenant_id or run["status"] != "started":
                raise ValueError("telemetry run does not match an active tenant run")
            if run["source_id"] != source_id:
                raise ValueError("telemetry run source mismatch")

            rows_added = 0
            for event in events:
                canonical = event.model_dump_json()
                content_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
                prior = connection.execute(
                    "SELECT content_hash FROM telemetry_events WHERE tenant_id = ? AND event_id = ?",
                    (tenant_id, event.event_id),
                ).fetchone()
                if prior is not None:
                    if prior["content_hash"] != content_hash:
                        raise TelemetryConflictError(f"event ID has conflicting stored content: {event.event_id}")
                    continue
                owner = connection.execute(
                    "SELECT event_id FROM telemetry_events WHERE tenant_id = ? AND evidence_ref = ?",
                    (tenant_id, event.evidence_ref),
                ).fetchone()
                if owner is not None and owner["event_id"] != event.event_id:
                    raise TelemetryConflictError(
                        f"evidence reference is assigned to another stored event: {event.evidence_ref}"
                    )
                connection.execute(
                    """INSERT INTO telemetry_events
                       (tenant_id, event_id, evidence_ref, occurred_at_utc, event_type, content_hash,
                        event_json, source_id, ingested_at_utc)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (tenant_id, event.event_id, event.evidence_ref, event.occurred_at.isoformat(),
                     event.event_type.value, content_hash, canonical, source_id, _utc_now()),
                )
                rows_added += 1

            stored_count = connection.execute(
                "SELECT COUNT(*) FROM telemetry_events WHERE tenant_id = ?", (tenant_id,)
            ).fetchone()[0]
            if stored_count > MAX_STORED_EVENTS_PER_TENANT:
                raise ValueError("synthetic telemetry store capacity reached")
            stored_rows = connection.execute(
                """SELECT event_json FROM telemetry_events WHERE tenant_id = ?
                   ORDER BY occurred_at_utc DESC, event_id DESC LIMIT ?""",
                (tenant_id, MAX_DETECTION_EVENTS),
            ).fetchall()
            detection_events = [SyntheticTelemetryEvent.model_validate_json(row["event_json"])
                                for row in reversed(stored_rows)]
            detections = detect_findings(detection_events, tenant_id=tenant_id)
            for detection in detections:
                existing = connection.execute(
                    "SELECT status, finding_json FROM telemetry_findings WHERE tenant_id = ? AND finding_id = ?",
                    (tenant_id, detection.finding_id),
                ).fetchone()
                merged = detection
                if existing is not None:
                    previous = TelemetryFinding.model_validate_json(existing["finding_json"])
                    evidence_refs = list(dict.fromkeys([*previous.evidence_refs, *detection.evidence_refs]))
                    event_ids = list(dict.fromkeys([*previous.event_ids, *detection.event_ids]))
                    merged = detection.model_copy(update={
                        "status": existing["status"],
                        "first_seen_utc": min(previous.first_seen_utc, detection.first_seen_utc),
                        "last_seen_utc": max(previous.last_seen_utc, detection.last_seen_utc),
                        "evidence_refs": evidence_refs[:MAX_DETECTION_EVENTS],
                        "event_ids": event_ids[:MAX_DETECTION_EVENTS],
                    })
                    connection.execute(
                        """UPDATE telemetry_findings SET severity = ?, first_seen_utc = ?, last_seen_utc = ?,
                           finding_json = ?, updated_at_utc = ? WHERE tenant_id = ? AND finding_id = ?""",
                        (merged.severity.value, merged.first_seen_utc.isoformat(), merged.last_seen_utc.isoformat(),
                         merged.model_dump_json(), _utc_now(), tenant_id, merged.finding_id),
                    )
                else:
                    now = _utc_now()
                    connection.execute(
                        """INSERT INTO telemetry_findings
                           (tenant_id, finding_id, status, severity, first_seen_utc, last_seen_utc,
                            finding_json, created_at_utc, updated_at_utc)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (tenant_id, merged.finding_id, merged.status, merged.severity.value, merged.first_seen_utc.isoformat(),
                         merged.last_seen_utc.isoformat(), merged.model_dump_json(), now, now),
                    )
                for evidence_ref in detection.evidence_refs:
                    event = next(item for item in detection_events if item.evidence_ref == evidence_ref)
                    connection.execute(
                        """INSERT OR IGNORE INTO telemetry_finding_evidence
                           (tenant_id, finding_id, evidence_ref, event_id) VALUES (?, ?, ?, ?)""",
                        (tenant_id, detection.finding_id, evidence_ref, event.event_id),
                    )
                observation_hash = hashlib.sha256(detection.model_dump_json().encode()).hexdigest()
                connection.execute(
                    """INSERT OR IGNORE INTO telemetry_finding_observations
                       (tenant_id, finding_id, observation_hash, observed_at_utc, observation_json)
                       VALUES (?, ?, ?, ?, ?)""",
                    (tenant_id, detection.finding_id, observation_hash, _utc_now(), detection.model_dump_json()),
                )

            all_rows = connection.execute(
                "SELECT finding_json FROM telemetry_findings WHERE tenant_id = ? ORDER BY finding_id",
                (tenant_id,),
            ).fetchall()
            all_findings = [TelemetryFinding.model_validate_json(row["finding_json"]) for row in all_rows]
            report = make_telemetry_report(
                tenant_id=tenant_id, run_id=run_id, source_id=source_id,
                input_count=input_count, accepted_count=rows_added,
                duplicate_count=input_count - rows_added, findings=all_findings,
                generated_at=datetime.now(timezone.utc),
            )
            connection.execute(
                """INSERT INTO telemetry_reports
                   (tenant_id, run_id, report_id, generated_at_utc, report_json)
                   VALUES (?, ?, ?, ?, ?)""",
                (tenant_id, run_id, report.report_id, report.generated_at_utc.isoformat(), report.model_dump_json()),
            )
            completion = connection.execute(
                """UPDATE telemetry_runs SET status = 'completed', completed_at_utc = ?,
                   input_event_count = ?, accepted_event_count = ?, duplicate_event_count = ?,
                   finding_count = ?, error_code = NULL WHERE run_id = ? AND tenant_id = ? AND status = 'started'""",
                (_utc_now(), input_count, rows_added, input_count - rows_added,
                 len(detections), run_id, tenant_id),
            )
            if completion.rowcount != 1:
                raise ValueError("telemetry run could not be completed")
            if live_source_position_sha256 is not None:
                source_status = connection.execute(
                    """UPDATE telemetry_source_status SET status = 'healthy', last_success_at_utc = ?,
                       input_event_count = ?, accepted_event_count = ?, duplicate_event_count = ?,
                       rejected_record_count = 0, position_sha256 = ?, position_bytes = ?, error_code = NULL
                       WHERE tenant_id = ? AND source_key = ? AND status = 'running'""",
                    (_utc_now(), input_count, rows_added, input_count - rows_added,
                     live_source_position_sha256, live_source_position_bytes,
                     tenant_id, self.LIVE_SOURCE_KEY),
                )
                if source_status.rowcount != 1:
                    raise ValueError("live source attempt was not started")
            self._prune_telemetry_history(connection, tenant_id)
        return report

    def list_telemetry_findings(self, tenant_id: str) -> list[TelemetryFinding]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT finding_json FROM telemetry_findings WHERE tenant_id = ? ORDER BY finding_id",
                (tenant_id,),
            ).fetchall()
        return [TelemetryFinding.model_validate_json(row["finding_json"]) for row in rows]

    def list_telemetry_evidence(self, tenant_id: str, finding_id: str) -> list[EvidenceReferenceResponse] | None:
        with self._connect() as connection:
            exists = connection.execute(
                "SELECT 1 FROM telemetry_findings WHERE tenant_id = ? AND finding_id = ?",
                (tenant_id, finding_id),
            ).fetchone()
            if exists is None:
                return None
            rows = connection.execute(
                """SELECT e.event_json FROM telemetry_finding_evidence f
                   JOIN telemetry_events e ON e.tenant_id = f.tenant_id AND e.event_id = f.event_id
                   WHERE f.tenant_id = ? AND f.finding_id = ? ORDER BY e.occurred_at_utc, e.event_id""",
                (tenant_id, finding_id),
            ).fetchall()
        result = []
        for row in rows:
            event = SyntheticTelemetryEvent.model_validate_json(row["event_json"])
            result.append(EvidenceReferenceResponse(
                evidence_ref=event.evidence_ref, event_id=event.event_id,
                event_type=event.event_type.value, occurred_at_utc=event.occurred_at,
                asset_ref=event.asset_ref, actor_ref=event.actor_ref, source_ref=event.source_ref,
            ))
        return result

    def latest_telemetry_report(self, tenant_id: str) -> TelemetryReport | None:
        with self._connect() as connection:
            row = connection.execute(
                """SELECT r.report_json FROM telemetry_reports r
                   JOIN telemetry_runs j ON j.run_id = r.run_id AND j.tenant_id = r.tenant_id
                   WHERE r.tenant_id = ? AND j.status = 'completed'
                   ORDER BY r.generated_at_utc DESC, r.run_id DESC LIMIT 1""",
                (tenant_id,),
            ).fetchone()
        return TelemetryReport.model_validate_json(row["report_json"]) if row else None

    def latest_telemetry_run(self, tenant_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                """SELECT run_id, source_id, status, scheduled_at_utc, started_at_utc,
                          completed_at_utc, attempt, input_event_count, accepted_event_count,
                          duplicate_event_count, finding_count, error_code
                   FROM telemetry_runs WHERE tenant_id = ? ORDER BY started_at_utc DESC, run_id DESC LIMIT 1""",
                (tenant_id,),
            ).fetchone()
        return dict(row) if row else None
