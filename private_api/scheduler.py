"""Single-owner local scheduler with cross-process lease, bounded workers and retries."""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Sequence

SCHEDULER_INTERVAL_SECONDS = 600
WORKER_TIMEOUT_SECONDS = 20
MAX_RETRIES = 1
RETRY_BACKOFF_SECONDS = 0.2
SHUTDOWN_JOIN_SECONDS = 5

_local_guard = threading.Lock()
_local_lock_paths: set[str] = set()


class ProcessLock:
    """A non-blocking OS file lock so a second local API process cannot schedule too."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._fd: int | None = None
        self._key = os.path.normcase(str(path.resolve()))

    def acquire(self) -> bool:
        with _local_guard:
            if self._key in _local_lock_paths:
                return False
            _local_lock_paths.add(self._key)
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._fd = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600)
            if os.fstat(self._fd).st_size == 0:
                os.write(self._fd, b"\0")
            os.lseek(self._fd, 0, os.SEEK_SET)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self._fd, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self._fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except (OSError, ImportError):
            if self._fd is not None:
                os.close(self._fd)
                self._fd = None
            with _local_guard:
                _local_lock_paths.discard(self._key)
            return False

    def release(self) -> None:
        if self._fd is None:
            return
        try:
            os.lseek(self._fd, 0, os.SEEK_SET)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self._fd, msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self._fd, fcntl.LOCK_UN)
        finally:
            os.close(self._fd)
            self._fd = None
            with _local_guard:
                _local_lock_paths.discard(self._key)


class WorkerTimeout(TimeoutError):
    pass


class WorkerFailure(RuntimeError):
    _SAFE_ERROR_CODES = {
        2: "source_invalid",
        3: "store_error",
        4: "processing_error",
        5: "event_conflict",
        6: "model_validation_error",
        7: "state_error",
    }
    _ALLOWED_ERROR_CODES = frozenset((*_SAFE_ERROR_CODES.values(), "worker_error"))

    def __init__(self, error_code: str = "worker_error") -> None:
        self.error_code = error_code if error_code in self._ALLOWED_ERROR_CODES else "worker_error"
        super().__init__(self.error_code)


class WorkerStopped(RuntimeError):
    pass


class SubprocessWorkerRunner:
    """Runs one telemetry cycle out of process so a hard timeout can terminate it."""

    def __init__(self, *, command_factory: Callable[..., Sequence[str]] | None = None) -> None:
        self.command_factory = command_factory or self._default_command
        self._active_lock = threading.Lock()
        self._active: subprocess.Popen | None = None

    @staticmethod
    def _default_command(database: Path, fixture: Path, tenant_id: str, run_id: str) -> Sequence[str]:
        return [sys.executable, "-m", "private_api.worker", "--database", str(database),
                "--fixture", str(fixture), "--tenant", tenant_id, "--run-id", run_id]

    def run(self, database: Path, fixture: Path, tenant_id: str, run_id: str, timeout: float) -> None:
        process = subprocess.Popen(
            list(self.command_factory(database, fixture, tenant_id, run_id)),
            cwd=Path(__file__).resolve().parents[1],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        with self._active_lock:
            self._active = process
        try:
            try:
                exit_code = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                self._terminate(process)
                raise WorkerTimeout("telemetry worker exceeded its time budget") from None
            if exit_code != 0:
                error_code = WorkerFailure._SAFE_ERROR_CODES.get(exit_code, "worker_error")
                raise WorkerFailure(error_code)
        finally:
            with self._active_lock:
                if self._active is process:
                    self._active = None

    @staticmethod
    def _terminate(process: subprocess.Popen) -> None:
        if process.poll() is not None:
            return
        try:
            process.terminate()
        except OSError:
            if process.poll() is not None:
                return
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            try:
                process.kill()
            except OSError:
                if process.poll() is not None:
                    return
            process.wait(timeout=1)

    def terminate_active(self) -> None:
        with self._active_lock:
            process = self._active
        if process is not None:
            self._terminate(process)


class LocalTelemetryScheduler:
    """One periodic worker thread and one OS-locked scheduler owner per local DB."""

    def __init__(
        self,
        *,
        database: Path,
        fixture: Path,
        tenant_ids: Sequence[str],
        store,
        interval_seconds: int = SCHEDULER_INTERVAL_SECONDS,
        worker_timeout_seconds: int = WORKER_TIMEOUT_SECONDS,
        max_retries: int = MAX_RETRIES,
        retry_backoff_seconds: float = RETRY_BACKOFF_SECONDS,
        runner: SubprocessWorkerRunner | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if interval_seconds != SCHEDULER_INTERVAL_SECONDS:
            raise ValueError("Phase 3 scheduler interval is fixed at 600 seconds")
        if worker_timeout_seconds < 1 or max_retries not in (0, 1):
            raise ValueError("scheduler timeout and retry bounds are invalid")
        if not 1 <= len(tenant_ids) <= 5 or len(set(tenant_ids)) != len(tenant_ids):
            raise ValueError("scheduler supports one to five unique local synthetic tenants")
        self.database = database
        self.fixture = fixture
        self.tenant_ids = tuple(tenant_ids)
        self.store = store
        self.interval_seconds = interval_seconds
        self.worker_timeout_seconds = worker_timeout_seconds
        self.max_retries = max_retries
        self.retry_backoff_seconds = retry_backoff_seconds
        self.runner = runner or SubprocessWorkerRunner()
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self._lease = ProcessLock(database.with_name("telemetry-scheduler.lock"))
        self._cycle_lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._state = "stopped"

    @property
    def state(self) -> str:
        return self._state

    def start(self) -> bool:
        if self._thread is not None and self._thread.is_alive():
            return True
        if not self._lease.acquire():
            self._state = "unavailable"
            return False
        self._stop.clear()
        self._state = "running"
        self._thread = threading.Thread(target=self._run_loop, name="aegisai-synthetic-telemetry", daemon=True)
        self._thread.start()
        return True

    def _new_run_id(self) -> str:
        return f"trun-{uuid.uuid4().hex[:16]}"

    def _record_skipped(self, scheduled_at: str) -> None:
        for tenant_id in self.tenant_ids:
            self.store.skip_telemetry_run(
                run_id=self._new_run_id(), tenant_id=tenant_id,
                source_id="local_synthetic_fixture_v1", scheduled_at_utc=scheduled_at,
            )

    def run_cycle(self) -> bool:
        if not self._cycle_lock.acquire(blocking=False):
            self._record_skipped(self.clock().astimezone(timezone.utc).isoformat())
            return False
        try:
            scheduled_at = self.clock().astimezone(timezone.utc).isoformat()
            cycle_succeeded = True
            for tenant_id in self.tenant_ids:
                for attempt in range(1, self.max_retries + 2):
                    run_id = self._new_run_id()
                    self.store.start_telemetry_run(
                        run_id=run_id, tenant_id=tenant_id,
                        source_id="local_synthetic_fixture_v1", scheduled_at_utc=scheduled_at,
                        attempt=attempt,
                    )
                    try:
                        self.runner.run(
                            self.database, self.fixture, tenant_id, run_id,
                            self.worker_timeout_seconds,
                        )
                        break
                    except WorkerStopped:
                        self.store.fail_telemetry_run(run_id, "shutdown")
                        return False
                    except WorkerTimeout:
                        self.store.fail_telemetry_run(run_id, "timeout")
                    except WorkerFailure as exc:
                        self.store.fail_telemetry_run(run_id, "shutdown" if self._stop.is_set() else exc.error_code)
                    except Exception:
                        self.store.fail_telemetry_run(run_id, "shutdown" if self._stop.is_set() else "worker_error")
                    if attempt <= self.max_retries and not self._stop.wait(self.retry_backoff_seconds):
                        continue
                    cycle_succeeded = False
                    break
            return cycle_succeeded
        finally:
            self._cycle_lock.release()

    def _run_loop(self) -> None:
        try:
            while not self._stop.is_set():
                try:
                    self.run_cycle()
                except Exception:
                    # Keep background failures categorical; do not print fixture/DB contents.
                    self._stop.set()
                    break
                if self._stop.wait(self.interval_seconds):
                    break
        finally:
            self._state = "stopped"
            self._lease.release()

    def stop(self, timeout: float = SHUTDOWN_JOIN_SECONDS) -> bool:
        self._stop.set()
        self.runner.terminate_active()
        thread = self._thread
        if thread is not None and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=timeout)
        if thread is not None and thread.is_alive():
            return False
        if self._thread is None:
            self._lease.release()
        self._state = "stopped"
        return True
