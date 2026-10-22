from __future__ import annotations

import sqlite3
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from platform_prototype.pipeline import build_report, read_batch_file
from private_api.scheduler import (
    LocalTelemetryScheduler,
    SubprocessWorkerRunner,
    WorkerTimeout,
)
from private_api.store import SQLiteStore
from private_api.telemetry import read_telemetry_file

ROOT = Path(__file__).parents[2]
PHASE1_FIXTURE = ROOT / "platform_prototype" / "fixtures" / "synthetic_events_v1.json"
TELEMETRY_FIXTURE = ROOT / "platform_prototype" / "fixtures" / "synthetic_telemetry_v1.json"
TENANT = "synthetic-org-scheduler-test"


def _store(tmp_path: Path) -> SQLiteStore:
    store = SQLiteStore(tmp_path / "private.sqlite3")
    store.seed_tenant(TENANT, build_report(read_batch_file(PHASE1_FIXTURE)))
    return store


def _counts(store: SQLiteStore) -> dict[str, int]:
    with sqlite3.connect(store.path) as connection:
        return {status: count for status, count in connection.execute(
            "SELECT status, COUNT(*) FROM telemetry_runs GROUP BY status"
        )}


def test_scheduler_cycle_records_completion_and_reprocessing_is_idempotent(tmp_path):
    store = _store(tmp_path)
    scheduler = LocalTelemetryScheduler(
        database=store.path, fixture=TELEMETRY_FIXTURE, tenant_ids=[TENANT], store=store,
    )
    assert scheduler.run_cycle() is True
    assert store.latest_telemetry_run(TENANT)["status"] == "completed"
    assert scheduler.run_cycle() is True
    latest = store.latest_telemetry_run(TENANT)
    assert latest["status"] == "completed"
    assert latest["accepted_event_count"] == 0
    assert latest["duplicate_event_count"] == 10
    assert _counts(store)["completed"] == 2


def test_scheduler_overlap_records_skipped_without_starting_second_worker(tmp_path):
    store = _store(tmp_path)
    entered = threading.Event()
    release = threading.Event()

    class BlockingRunner:
        def run(self, database, fixture, tenant_id, run_id, timeout):
            entered.set()
            assert release.wait(timeout=3)
            batch = read_telemetry_file(fixture)
            SQLiteStore(database).complete_telemetry_cycle(
                run_id=run_id, tenant_id=tenant_id, source_id=batch.source_id, batch=batch,
            )

        def terminate_active(self):
            release.set()

    scheduler = LocalTelemetryScheduler(
        database=store.path, fixture=TELEMETRY_FIXTURE, tenant_ids=[TENANT], store=store,
        runner=BlockingRunner(),
    )
    first = threading.Thread(target=scheduler.run_cycle)
    first.start()
    assert entered.wait(timeout=2)
    assert scheduler.run_cycle() is False
    release.set()
    first.join(timeout=3)
    assert not first.is_alive()
    counts = _counts(store)
    assert counts["completed"] == 1
    assert counts["skipped"] == 1


def test_worker_retries_once_after_timeout_then_completes(tmp_path):
    store = _store(tmp_path)

    class RetryRunner:
        calls = 0

        def run(self, database, fixture, tenant_id, run_id, timeout):
            self.calls += 1
            if self.calls == 1:
                raise WorkerTimeout("test timeout")
            batch = read_telemetry_file(fixture)
            SQLiteStore(database).complete_telemetry_cycle(
                run_id=run_id, tenant_id=tenant_id, source_id=batch.source_id, batch=batch,
            )

        def terminate_active(self):
            return None

    runner = RetryRunner()
    scheduler = LocalTelemetryScheduler(
        database=store.path, fixture=TELEMETRY_FIXTURE, tenant_ids=[TENANT], store=store,
        runner=runner, retry_backoff_seconds=0,
    )
    assert scheduler.run_cycle() is True
    with sqlite3.connect(store.path) as connection:
        attempts = connection.execute(
            "SELECT attempt, status, error_code FROM telemetry_runs ORDER BY attempt"
        ).fetchall()
    assert attempts == [(1, "failed", "timeout"), (2, "completed", None)]
    assert runner.calls == 2


def test_worker_process_enforces_timeout_and_terminates_child(tmp_path):
    store = _store(tmp_path)
    runner = SubprocessWorkerRunner(command_factory=lambda *_: [sys.executable, "-c", "import time; time.sleep(30)"])
    scheduler = LocalTelemetryScheduler(
        database=store.path, fixture=TELEMETRY_FIXTURE, tenant_ids=[TENANT], store=store,
        runner=runner, worker_timeout_seconds=1, max_retries=0,
    )
    started = time.monotonic()
    assert scheduler.run_cycle() is False
    assert time.monotonic() - started < 5
    assert store.latest_telemetry_run(TENANT)["status"] == "failed"
    assert store.latest_telemetry_run(TENANT)["error_code"] == "timeout"
    assert runner._active is None


def test_start_prevents_duplicate_local_schedulers_and_shutdown_releases_lock(tmp_path):
    store = _store(tmp_path)
    scheduler1 = LocalTelemetryScheduler(
        database=store.path, fixture=TELEMETRY_FIXTURE, tenant_ids=[TENANT], store=store,
    )
    scheduler2 = LocalTelemetryScheduler(
        database=store.path, fixture=TELEMETRY_FIXTURE, tenant_ids=[TENANT], store=store,
    )
    assert scheduler1.start() is True
    assert scheduler1.start() is True
    assert scheduler2.start() is False
    assert scheduler2.state == "unavailable"
    assert scheduler1.stop(timeout=5) is True
    assert scheduler1.state == "stopped"
    assert scheduler2.start() is True
    assert scheduler2.stop(timeout=5) is True


def test_shutdown_terminates_active_worker_and_joins_scheduler_thread(tmp_path):
    store = _store(tmp_path)
    runner = SubprocessWorkerRunner(command_factory=lambda *_: [sys.executable, "-c", "import time; time.sleep(30)"])
    scheduler = LocalTelemetryScheduler(
        database=store.path, fixture=TELEMETRY_FIXTURE, tenant_ids=[TENANT], store=store,
        runner=runner, worker_timeout_seconds=20,
    )
    assert scheduler.start() is True
    deadline = time.monotonic() + 3
    while runner._active is None and time.monotonic() < deadline:
        time.sleep(0.01)
    assert runner._active is not None
    assert scheduler.stop(timeout=5) is True
    assert scheduler.state == "stopped"
    assert scheduler._thread is None or not scheduler._thread.is_alive()
    assert runner._active is None


def test_scheduler_enforces_fixed_interval_and_tenant_count_bounds(tmp_path):
    store = _store(tmp_path)
    try:
        LocalTelemetryScheduler(
            database=store.path, fixture=TELEMETRY_FIXTURE, tenant_ids=[TENANT], store=store,
            interval_seconds=30,
        )
    except ValueError as exc:
        assert "600 seconds" in str(exc)
    else:
        raise AssertionError("short scheduler interval should be rejected")
    try:
        LocalTelemetryScheduler(
            database=store.path, fixture=TELEMETRY_FIXTURE, tenant_ids=[TENANT] * 6, store=store,
        )
    except ValueError as exc:
        assert "one to five" in str(exc)
    else:
        raise AssertionError("too many tenants should be rejected")
    try:
        LocalTelemetryScheduler(
            database=store.path, fixture=TELEMETRY_FIXTURE, tenant_ids=[TENANT], store=store,
            max_retries=2,
        )
    except ValueError as exc:
        assert "timeout and retry bounds" in str(exc)
    else:
        raise AssertionError("more than one retry should be rejected")
