from __future__ import annotations

import sqlite3
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

from platform_prototype.pipeline import build_report, read_batch_file
from private_api.scheduler import (
    LocalTelemetryScheduler,
    SubprocessWorkerRunner,
    WorkerFailure,
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


def test_worker_failure_exit_codes_are_mapped_to_safe_categories():
    expected = {
        2: "source_invalid", 3: "store_error", 4: "processing_error",
        5: "event_conflict", 6: "model_validation_error", 7: "state_error",
        9: "worker_error",
    }
    for exit_code, category in expected.items():
        runner = SubprocessWorkerRunner(command_factory=lambda *_, code=exit_code: [
            sys.executable, "-c", f"raise SystemExit({code})",
        ])
        try:
            runner.run(Path("unused.sqlite3"), Path("unused.json"), TENANT, "run-id", timeout=2)
        except WorkerFailure as error:
            assert error.error_code == category
        else:
            raise AssertionError(f"worker exit {exit_code} should fail")


def test_invalid_fixture_failure_is_reported_without_exposing_details(tmp_path):
    store = _store(tmp_path)
    fixture = tmp_path / "invalid-telemetry.json"
    fixture.write_text('{"not":"a telemetry batch"}', encoding="utf-8")
    scheduler = LocalTelemetryScheduler(
        database=store.path, fixture=fixture, tenant_ids=[TENANT], store=store,
        max_retries=0,
    )
    assert scheduler.run_cycle() is False
    run = store.latest_telemetry_run(TENANT)
    assert run["status"] == "failed"
    assert run["error_code"] == "source_invalid"
    assert "not a telemetry batch" not in str(run)


def test_conflicting_stored_event_is_reported_as_event_conflict(tmp_path):
    store = _store(tmp_path)
    batch = read_telemetry_file(TELEMETRY_FIXTURE)
    changed_event = batch.events[0].model_copy(update={"actor_ref": "synthetic-conflict-test"})
    store.start_telemetry_run(
        run_id="trun-0000000000000001", tenant_id=TENANT, source_id=batch.source_id,
        scheduled_at_utc=datetime.now(timezone.utc).isoformat(), attempt=1,
    )
    store.complete_telemetry_cycle(
        run_id="trun-0000000000000001", tenant_id=TENANT, source_id=batch.source_id,
        batch=batch.model_copy(update={"events": [changed_event]}),
    )

    scheduler = LocalTelemetryScheduler(
        database=store.path, fixture=TELEMETRY_FIXTURE, tenant_ids=[TENANT], store=store,
        max_retries=0,
    )
    assert scheduler.run_cycle() is False
    run = store.latest_telemetry_run(TENANT)
    assert run["status"] == "failed"
    assert run["error_code"] == "event_conflict"


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


@pytest.mark.parametrize("worker_succeeds", [True, False])
def test_shutdown_does_not_start_next_tenant_or_retry(tmp_path, worker_succeeds):
    store = _store(tmp_path)
    second_tenant = "synthetic-org-scheduler-second"
    store.seed_tenant(second_tenant, build_report(read_batch_file(PHASE1_FIXTURE)))
    entered = threading.Event()
    release = threading.Event()

    class FinishingRunner:
        calls: list[str] = []

        def run(self, database, fixture, tenant_id, run_id, timeout):
            self.calls.append(tenant_id)
            entered.set()
            assert release.wait(timeout=3)
            if not worker_succeeds:
                raise WorkerFailure("processing_error")
            batch = read_telemetry_file(fixture)
            SQLiteStore(database).complete_telemetry_cycle(
                run_id=run_id, tenant_id=tenant_id, source_id=batch.source_id, batch=batch,
            )

        def terminate_active(self):
            release.set()

    runner = FinishingRunner()
    scheduler = LocalTelemetryScheduler(
        database=store.path, fixture=TELEMETRY_FIXTURE,
        tenant_ids=[TENANT, second_tenant], store=store,
        runner=runner, max_retries=1, retry_backoff_seconds=0,
    )
    try:
        assert scheduler.start() is True
        assert entered.wait(timeout=2)
        assert scheduler.stop(timeout=5) is True
        assert runner.calls == [TENANT]
        assert store.latest_telemetry_run(second_tenant) is None
        first = store.latest_telemetry_run(TENANT)
        assert first["status"] == ("completed" if worker_succeeds else "failed")
        if not worker_succeeds:
            assert first["error_code"] == "shutdown"
        # Manual or overlapping callers cannot enqueue new work after stop.
        assert scheduler.run_cycle() is False
        assert runner.calls == [TENANT]
    finally:
        release.set()
        scheduler.stop(timeout=5)


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
