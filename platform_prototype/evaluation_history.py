"""Bounded, opt-in history for deterministic synthetic evaluation reports."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from platform_prototype.evaluation import (
    ConfusionCounts,
    EvaluationReport,
    Metrics,
    MAX_REPORT_BYTES,
    report_json,
)

MAX_HISTORY_RUNS = 20
MAX_HISTORY_DB_BYTES = (MAX_REPORT_BYTES * MAX_HISTORY_RUNS) + (256 * 1024)


class HistoryModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class EvaluationComparison(HistoryModel):
    previous_run_id: str
    newly_failing_scenario_ids: list[str] = Field(max_length=50)
    resolved_scenario_ids: list[str] = Field(max_length=50)


class EvaluationRunSummary(HistoryModel):
    run_id: str = Field(pattern=r"^[a-f0-9-]{36}$")
    generated_at_utc: datetime
    report_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    dataset_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    detector_config_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    counts: ConfusionCounts
    metrics: Metrics
    total_evaluated_pairs: int = Field(ge=0)
    comparison: EvaluationComparison | None


def _failing_scenarios(report: EvaluationReport) -> set[str]:
    return {item.scenario_id for item in report.scenarios if item.status == "fail"}


def _run_summary(
    run_id: str,
    generated_at_utc: str,
    report_sha256: str,
    report: EvaluationReport,
    previous: tuple[str, EvaluationReport] | None,
) -> EvaluationRunSummary:
    comparison = None
    if previous is not None:
        previous_id, previous_report = previous
        current_failures = _failing_scenarios(report)
        previous_failures = _failing_scenarios(previous_report)
        comparison = EvaluationComparison(
            previous_run_id=previous_id,
            newly_failing_scenario_ids=sorted(current_failures - previous_failures),
            resolved_scenario_ids=sorted(previous_failures - current_failures),
        )
    counts = report.counts
    timestamp = datetime.fromisoformat(generated_at_utc.replace("Z", "+00:00"))
    if timestamp.tzinfo is None or timestamp.utcoffset() != timezone.utc.utcoffset(timestamp):
        raise ValueError("evaluation history timestamp must be UTC")
    return EvaluationRunSummary(
        run_id=run_id,
        generated_at_utc=timestamp,
        report_sha256=report_sha256,
        dataset_sha256=report.dataset_sha256,
        detector_config_sha256=report.detector_config_sha256,
        counts=counts,
        metrics=report.metrics,
        total_evaluated_pairs=(counts.true_positives + counts.true_negatives
                               + counts.false_positives + counts.false_negatives),
        comparison=comparison,
    )


def _connect(database_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(database_path, timeout=2.0)
    connection.execute("PRAGMA busy_timeout = 2000")
    return connection


def record_evaluation_run(
    database_path: Path,
    report: EvaluationReport,
    *,
    generated_at_utc: str | None = None,
    run_id: str | None = None,
) -> EvaluationRunSummary:
    """Atomically append one run and retain no more than the newest twenty reports."""
    path = Path(database_path)
    payload = report_json(report)
    payload_bytes = payload.encode("utf-8")
    if len(payload_bytes) > MAX_REPORT_BYTES:
        raise ValueError("evaluation report exceeds the history record limit")
    timestamp = generated_at_utc or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    # Reject non-UTC/invalid timestamps at the persistence boundary.
    parsed_timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    if parsed_timestamp.tzinfo is None or parsed_timestamp.utcoffset() != timezone.utc.utcoffset(parsed_timestamp):
        raise ValueError("evaluation timestamp must be UTC")
    identifier = run_id or str(uuid.uuid4())
    try:
        if str(uuid.UUID(identifier)) != identifier:
            raise ValueError
    except (ValueError, AttributeError, TypeError):
        raise ValueError("invalid evaluation run identifier")
    digest = hashlib.sha256(payload_bytes).hexdigest()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.stat().st_size > MAX_HISTORY_DB_BYTES:
        raise ValueError("evaluation history store exceeds its size limit")
    connection = _connect(path)
    try:
        existing_tables = {row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )}
        user_version = connection.execute("PRAGMA user_version").fetchone()[0]
        if existing_tables and (existing_tables != {"evaluation_runs"} or user_version != 1):
            raise ValueError("evaluation history store schema is not recognized")
        connection.execute("BEGIN IMMEDIATE")
        if not existing_tables:
            if user_version != 0:
                raise ValueError("evaluation history store schema is not recognized")
            connection.execute("""
                CREATE TABLE evaluation_runs (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL UNIQUE,
                    generated_at_utc TEXT NOT NULL,
                    report_sha256 TEXT NOT NULL,
                    report_json TEXT NOT NULL
                )
            """)
            connection.execute("PRAGMA user_version = 1")
        latest = connection.execute(
            "SELECT run_id, report_json FROM evaluation_runs ORDER BY sequence DESC LIMIT 1"
        ).fetchone()
        previous = None
        if latest is not None:
            try:
                previous = (latest[0], EvaluationReport.model_validate_json(latest[1]))
            except (ValidationError, ValueError, TypeError):
                raise ValueError("evaluation history store contains an invalid report") from None
        connection.execute(
            "INSERT INTO evaluation_runs(run_id, generated_at_utc, report_sha256, report_json) VALUES (?, ?, ?, ?)",
            (identifier, timestamp, digest, payload),
        )
        connection.execute("""
            DELETE FROM evaluation_runs WHERE sequence NOT IN (
                SELECT sequence FROM evaluation_runs ORDER BY sequence DESC LIMIT ?
            )
        """, (MAX_HISTORY_RUNS,))
        connection.commit()
        return _run_summary(identifier, timestamp, digest, report, previous)
    except Exception:
        if connection.in_transaction:
            connection.rollback()
        raise
    finally:
        connection.close()


def read_evaluation_history(database_path: Path) -> tuple[EvaluationReport | None, list[EvaluationRunSummary]]:
    """Read an existing history store without creating it; tolerate only bounded, valid content."""
    path = Path(database_path)
    if not path.is_file() or path.stat().st_size > MAX_HISTORY_DB_BYTES:
        return None, []
    uri = f"{path.resolve().as_uri()}?mode=ro"
    try:
        connection = sqlite3.connect(uri, uri=True, timeout=0.5)
        try:
            connection.execute("PRAGMA query_only = ON")
            if connection.execute("PRAGMA user_version").fetchone()[0] != 1:
                return None, []
            rows = connection.execute(
                "SELECT run_id, generated_at_utc, report_sha256, report_json "
                "FROM evaluation_runs ORDER BY sequence DESC LIMIT ?", (MAX_HISTORY_RUNS,),
            ).fetchall()
        finally:
            connection.close()
        if len(rows) > MAX_HISTORY_RUNS:
            return None, []
        reports: list[tuple[EvaluationRunSummary, EvaluationReport]] = []
        for identifier, timestamp, digest, payload in rows:
            if len(payload.encode("utf-8")) > MAX_REPORT_BYTES:
                return None, []
            report = EvaluationReport.model_validate_json(payload)
            expected_digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
            if digest != expected_digest:
                return None, []
            reports.append((_run_summary(identifier, timestamp, digest, report, None), report))
        if not reports:
            return None, []
        summaries: list[EvaluationRunSummary] = []
        # Comparisons are reconstructed from adjacent retained reports, oldest to newest.
        prior: tuple[str, EvaluationReport] | None = None
        chronological = list(reversed(reports))
        for summary, report in chronological:
            summaries.append(_run_summary(
                summary.run_id, summary.generated_at_utc.isoformat(), summary.report_sha256, report, prior,
            ))
            prior = (summary.run_id, report)
        summaries.reverse()
        return reports[0][1], summaries
    except (OSError, sqlite3.Error, ValidationError, ValueError, TypeError):
        return None, []
