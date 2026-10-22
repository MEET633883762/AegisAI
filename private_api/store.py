"""Tenant-scoped SQLite store for synthetic reports and append-only audit rows."""

from __future__ import annotations

import hashlib
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from platform_prototype.models import Finding, IncidentReport
from private_api.auth import TENANT_PATTERN
from private_api.models import (
    EvidenceReferenceResponse,
    IncidentReportResponse,
    IncidentSummary,
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
            if version > 3:
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
                """
            )
            connection.execute("PRAGMA user_version = 3")

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
