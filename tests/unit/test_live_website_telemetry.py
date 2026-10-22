from __future__ import annotations

import http.client
import json
import multiprocessing
import os
import sqlite3
import threading
from pathlib import Path

import pytest

import demo_site.telemetry_server as site
import private_api.live_website_connector as connector
import scripts.ingest_live_website_telemetry as live_cli
import scripts.generate_local_website_traffic as traffic
from platform_prototype.pipeline import build_report, read_batch_file
from private_api.live_website_ingestion import ingest_live_local_website_logs
from private_api.store import SQLiteStore
from private_api.telemetry import TelemetryReport
from private_api.website_connector import WebsiteLogInputError
from private_api.website_ingestion import FIXED_TENANT_ID

ROOT = Path(__file__).parents[2]
PHASE1_FIXTURE = ROOT / "platform_prototype" / "fixtures" / "synthetic_events_v1.json"


def _exit_process_during_live_report_commit(database: str, repository_root: str) -> None:
    import private_api.live_website_connector as child_connector
    import private_api.store as child_store

    root = Path(repository_root)
    local_root = root / ".aegisai-local"
    log_dir = local_root / "website-telemetry"
    child_connector.ROOT = root
    child_connector.LOCAL_ROOT = local_root
    child_connector.LOG_DIR = log_dir
    child_connector.ACTIVE_ACCESS = log_dir / "access.jsonl"
    child_connector.ROTATED_ACCESS = log_dir / "access.jsonl.1"
    child_connector.OLDER_ROTATED_ACCESS = (log_dir / "access.jsonl.2", log_dir / "access.jsonl.3")
    child_connector.ACTIVE_ERRORS = log_dir / "errors.jsonl"
    child_connector.ROTATED_ERRORS = log_dir / "errors.jsonl.1"
    child_connector.OLDER_ROTATED_ERRORS = (log_dir / "errors.jsonl.2", log_dir / "errors.jsonl.3")
    child_connector.APPROVED_LOG_FILES = (
        log_dir / "access.jsonl.3", log_dir / "access.jsonl.2", log_dir / "access.jsonl.1",
        log_dir / "access.jsonl", log_dir / "errors.jsonl.3", log_dir / "errors.jsonl.2",
        log_dir / "errors.jsonl.1", log_dir / "errors.jsonl",
    )
    child_store.make_telemetry_report = lambda **_kwargs: os._exit(23)
    ingest_live_local_website_logs(SQLiteStore(Path(database)))


def _temporary_log_paths(monkeypatch, tmp_path: Path):
    local_root = tmp_path / ".aegisai-local"
    log_dir = local_root / "website-telemetry"
    monkeypatch.setattr(site, "ROOT", tmp_path)
    monkeypatch.setattr(site, "LOCAL_ROOT", local_root)
    monkeypatch.setattr(site, "LOG_DIR", log_dir)
    monkeypatch.setattr(site, "ACCESS_LOG", log_dir / "access.jsonl")
    monkeypatch.setattr(site, "ERROR_LOG", log_dir / "errors.jsonl")
    monkeypatch.setattr(site, "PORT", 0)
    monkeypatch.setattr(connector, "ROOT", tmp_path)
    monkeypatch.setattr(connector, "LOCAL_ROOT", local_root)
    monkeypatch.setattr(connector, "LOG_DIR", log_dir)
    monkeypatch.setattr(connector, "ACTIVE_ACCESS", log_dir / "access.jsonl")
    monkeypatch.setattr(connector, "ROTATED_ACCESS", log_dir / "access.jsonl.1")
    monkeypatch.setattr(connector, "OLDER_ROTATED_ACCESS", (log_dir / "access.jsonl.2", log_dir / "access.jsonl.3"))
    monkeypatch.setattr(connector, "ACTIVE_ERRORS", log_dir / "errors.jsonl")
    monkeypatch.setattr(connector, "ROTATED_ERRORS", log_dir / "errors.jsonl.1")
    monkeypatch.setattr(connector, "OLDER_ROTATED_ERRORS", (log_dir / "errors.jsonl.2", log_dir / "errors.jsonl.3"))
    monkeypatch.setattr(connector, "APPROVED_LOG_FILES", (
        log_dir / "access.jsonl.3", log_dir / "access.jsonl.2", log_dir / "access.jsonl.1", log_dir / "access.jsonl",
        log_dir / "errors.jsonl.3", log_dir / "errors.jsonl.2", log_dir / "errors.jsonl.1", log_dir / "errors.jsonl",
    ))
    return log_dir


def _request(port: int, method: str, path: str) -> int:
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
    try:
        connection.request(method, path)
        response = connection.getresponse()
        response.read(512)
        return response.status
    finally:
        connection.close()


def _start_site(monkeypatch, tmp_path: Path):
    log_dir = _temporary_log_paths(monkeypatch, tmp_path)
    server = site.create_server()
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
    thread.start()
    return server, thread, log_dir


def test_loopback_website_and_fixed_traffic_generator_emit_logs_and_stop_cleanly(tmp_path, monkeypatch, capsys):
    server, thread, log_dir = _start_site(monkeypatch, tmp_path)
    try:
        port = server.server_address[1]
        assert server.server_address[0] == "127.0.0.1"
        monkeypatch.setattr(traffic, "BASE_URL", f"http://127.0.0.1:{port}")
        assert traffic.main([]) == 0
        assert "Generated 7 harmless loopback requests" in capsys.readouterr().out
        with pytest.raises(SystemExit):
            traffic.main(["--url", "http://example.invalid"])
        access = (log_dir / "access.jsonl").read_text(encoding="utf-8").splitlines()
        errors = (log_dir / "errors.jsonl").read_text(encoding="utf-8").splitlines()
        assert len(access) == 7 and len(errors) == 1
        assert {json.loads(line)["record_type"] for line in access} == {"http_access", "auth_failure"}
        assert json.loads(errors[0])["error_code"] == "DEMO_ERROR_RESPONSE"
        assert all("/login-failure" not in line and "127.0.0.1" not in line for line in access + errors)
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()
    assert not thread.is_alive()


def test_live_log_ingestion_reuses_rules_evidence_audit_and_tenant_isolation(tmp_path, monkeypatch, capsys):
    server, thread, _log_dir = _start_site(monkeypatch, tmp_path)
    database = tmp_path / "private.sqlite3"
    monkeypatch.setattr(live_cli, "DEFAULT_DATABASE", database)
    try:
        port = server.server_address[1]
        _request(port, "GET", "/")
        for _ in range(3):
            _request(port, "POST", "/login-failure")
        _request(port, "GET", "/demo-error")
        assert live_cli.main([]) == 0
        first = TelemetryReport.model_validate_json(capsys.readouterr().out)
        assert live_cli.main([]) == 0
        second = TelemetryReport.model_validate_json(capsys.readouterr().out)
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()
    assert first.tenant_id == second.tenant_id == FIXED_TENANT_ID
    assert (first.input_event_count, first.accepted_event_count, first.duplicate_event_count) == (6, 6, 0)
    assert (second.accepted_event_count, second.duplicate_event_count) == (0, 6)
    store = SQLiteStore(database)
    findings = store.list_telemetry_findings(FIXED_TENANT_ID)
    assert [finding.rule_id for finding in findings] == ["AUTH-001"]
    auth_evidence = store.list_telemetry_evidence(FIXED_TENANT_ID, findings[0].finding_id)
    assert auth_evidence and len(auth_evidence) == 3
    assert all(item.source_ref == "synthetic-demo-site-live-access-error-logs-v1" for item in auth_evidence)
    ingestion_audits = [item for item in store.audit_snapshot()
                        if item["route"] == "live_website_telemetry.ingest"]
    assert len(ingestion_audits) == 2  # one intentional audit event per CLI attempt

    other = "synthetic-org-live-website-other"
    store.seed_tenant(other, build_report(read_batch_file(PHASE1_FIXTURE)))
    assert store.list_telemetry_findings(other) == []
    with pytest.raises(TypeError):
        ingest_live_local_website_logs(store, tenant_id=other)


def _access_line(suffix: str) -> bytes:
    return (json.dumps({
        "record_id": f"wlog-access-{suffix}",
        "occurred_at": "2026-10-22T12:00:00Z",
        "record_type": "http_access",
        "actor_ref": "synthetic-user-a",
        "evidence_id": f"website-evidence-access-{suffix}",
        "method": "GET", "route_code": "home", "status_code": 200,
    }, separators=(",", ":")) + "\n").encode()


def test_partial_trailing_line_is_ignored_then_ingested_when_completed(tmp_path, monkeypatch):
    log_dir = _temporary_log_paths(monkeypatch, tmp_path)
    log_dir.mkdir(parents=True)
    line = _access_line("partial-1")
    active = log_dir / "access.jsonl"
    active.write_bytes(line + line[:-5])
    first = connector.read_live_website_log_batch()
    assert len(first.events) == 1
    with active.open("ab") as output:
        output.write(line[-5:])
    second = connector.read_live_website_log_batch()
    assert len(second.events) == 2


def test_fixed_rotation_and_truncation_keep_old_events_and_ingest_new_lines(tmp_path, monkeypatch):
    log_dir = _temporary_log_paths(monkeypatch, tmp_path)
    log_dir.mkdir(parents=True)
    active = log_dir / "access.jsonl"
    rotated = log_dir / "access.jsonl.1"
    active.write_bytes(_access_line("rotate-1"))
    active.replace(rotated)
    active.write_bytes(_access_line("rotate-2"))
    batch = connector.read_live_website_log_batch()
    assert {event.event_id for event in batch.events} == {"syn-website-access-rotate-1", "syn-website-access-rotate-2"}
    store = SQLiteStore(tmp_path / "private.sqlite3")
    first = ingest_live_local_website_logs(store)
    assert first.accepted_event_count == 2
    active.write_bytes(b"")  # truncation never causes deletion from tenant storage
    truncated = connector.read_live_website_log_batch()
    assert {event.event_id for event in truncated.events} == {"syn-website-access-rotate-1"}
    second = ingest_live_local_website_logs(store)
    assert (second.accepted_event_count, second.duplicate_event_count) == (0, 1)
    with sqlite3.connect(store.path) as connection:
        retained = {row[0] for row in connection.execute(
            "SELECT event_id FROM telemetry_events WHERE tenant_id = ?", (FIXED_TENANT_ID,),
        )}
    assert retained == {"syn-website-access-rotate-1", "syn-website-access-rotate-2"}


def test_multiple_fixed_rotations_are_read_oldest_first_and_bounded(tmp_path, monkeypatch):
    log_dir = _temporary_log_paths(monkeypatch, tmp_path)
    log_dir.mkdir(parents=True)
    for index in range(1, 5):
        name = "access.jsonl" if index == 4 else f"access.jsonl.{4 - index}"
        (log_dir / name).write_bytes(_access_line(f"multi-{index}"))
    snapshot = connector.read_live_website_log_snapshot()
    assert len(snapshot.batch.events) == 4
    assert snapshot.position_bytes == sum((log_dir / name).stat().st_size for name in (
        "access.jsonl", "access.jsonl.1", "access.jsonl.2", "access.jsonl.3",
    ))
    assert len(snapshot.position_sha256) == 64


@pytest.mark.parametrize("bad_line", [b"{\n", b"[]\n", b'{"record_type":"unknown"}\n'])
def test_malformed_complete_records_fail_safely(tmp_path, monkeypatch, bad_line):
    log_dir = _temporary_log_paths(monkeypatch, tmp_path)
    log_dir.mkdir(parents=True)
    (log_dir / "access.jsonl").write_bytes(bad_line)
    with pytest.raises(WebsiteLogInputError, match="validation failed"):
        connector.read_live_website_log_batch()


def test_source_authorization_rejects_symlinks_and_paths_outside_fixed_log_directory(tmp_path, monkeypatch):
    log_dir = _temporary_log_paths(monkeypatch, tmp_path)
    log_dir.mkdir(parents=True)
    outside = tmp_path / "outside.jsonl"
    outside.write_bytes(_access_line("outside"))
    link = log_dir / "access.jsonl"
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation is unavailable")
    with pytest.raises(WebsiteLogInputError, match="outside its approved local directory"):
        connector.read_live_website_log_batch()
    monkeypatch.setattr(connector, "APPROVED_LOG_FILES", (outside,))
    with pytest.raises(WebsiteLogInputError, match="outside its approved local directory"):
        connector.read_live_website_log_batch()


def test_reader_rejects_unlisted_file_inside_approved_directory(tmp_path, monkeypatch):
    log_dir = _temporary_log_paths(monkeypatch, tmp_path)
    log_dir.mkdir(parents=True)
    unlisted = log_dir / "operator-added.jsonl"
    unlisted.write_bytes(_access_line("unlisted"))
    with pytest.raises(WebsiteLogInputError, match="approved fixed file list"):
        connector._read_fixed_log(unlisted)


def test_live_log_file_and_record_size_limits(tmp_path, monkeypatch):
    log_dir = _temporary_log_paths(monkeypatch, tmp_path)
    log_dir.mkdir(parents=True)
    (log_dir / "access.jsonl").write_bytes(b"x" * (connector.MAX_LOG_FILE_BYTES + 1))
    with pytest.raises(WebsiteLogInputError, match="1 MiB"):
        connector.read_live_website_log_batch()
    (log_dir / "access.jsonl").write_bytes(b"x" * (connector.MAX_LOG_LINE_BYTES + 1) + b"\n")
    with pytest.raises(WebsiteLogInputError, match="16 KiB"):
        connector.read_live_website_log_batch()


def test_restart_replays_partial_completion_without_duplicate_events(tmp_path, monkeypatch):
    log_dir = _temporary_log_paths(monkeypatch, tmp_path)
    log_dir.mkdir(parents=True)
    active = log_dir / "access.jsonl"
    line = _access_line("restart-partial")
    first_line = _access_line("restart-existing")
    active.write_bytes(first_line + line[:-4])
    database = tmp_path / "private.sqlite3"
    first_store = SQLiteStore(database)
    first_attempt = ingest_live_local_website_logs(first_store)
    active.write_bytes(first_line + line)
    restarted_store = SQLiteStore(database)
    recovered = ingest_live_local_website_logs(restarted_store)
    second = ingest_live_local_website_logs(SQLiteStore(database))
    assert (first_attempt.accepted_event_count, first_attempt.duplicate_event_count) == (1, 0)
    assert (recovered.accepted_event_count, recovered.duplicate_event_count) == (1, 1)
    assert (second.accepted_event_count, second.duplicate_event_count) == (0, 2)
    status = restarted_store.live_source_status(FIXED_TENANT_ID)
    assert status["status"] == "healthy"
    assert status["last_success_at_utc"] is not None
    assert status["position_sha256"] and status["position_bytes"] == len(first_line + line)
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM telemetry_events").fetchone()[0] == 2


def test_interrupted_cycle_rolls_back_and_retry_recovers(tmp_path, monkeypatch):
    import private_api.store as store_module

    log_dir = _temporary_log_paths(monkeypatch, tmp_path)
    log_dir.mkdir(parents=True)
    (log_dir / "access.jsonl").write_bytes(_access_line("rollback-a") + _access_line("rollback-b"))
    store = SQLiteStore(tmp_path / "private.sqlite3")
    original = store_module.make_telemetry_report
    calls = [0]

    def interrupt_once(**kwargs):
        calls[0] += 1
        if calls[0] == 1:
            raise OSError("simulated interrupted report write")
        return original(**kwargs)

    monkeypatch.setattr(store_module, "make_telemetry_report", interrupt_once)
    with pytest.raises(RuntimeError, match="ingestion failed"):
        ingest_live_local_website_logs(store)
    with sqlite3.connect(store.path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM telemetry_events").fetchone()[0] == 0
    recovered = ingest_live_local_website_logs(SQLiteStore(store.path))
    assert (recovered.accepted_event_count, recovered.duplicate_event_count) == (2, 0)
    with sqlite3.connect(store.path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM telemetry_events").fetchone()[0] == 2


def test_abrupt_process_exit_during_transaction_recovers_after_restart(tmp_path, monkeypatch):
    log_dir = _temporary_log_paths(monkeypatch, tmp_path)
    log_dir.mkdir(parents=True)
    (log_dir / "access.jsonl").write_bytes(_access_line("process-crash"))
    database = tmp_path / "private.sqlite3"
    SQLiteStore(database)
    process = multiprocessing.get_context("spawn").Process(
        target=_exit_process_during_live_report_commit,
        args=(str(database), str(tmp_path)),
    )
    process.start()
    process.join(timeout=15)
    if process.is_alive():
        process.kill()
        process.join(timeout=5)
        pytest.fail("crash-injection child process did not exit within the bound")
    assert process.exitcode == 23
    recovered_store = SQLiteStore(database)
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM telemetry_events").fetchone()[0] == 0
    assert recovered_store.live_source_status(FIXED_TENANT_ID)["status"] == "running"
    recovered = ingest_live_local_website_logs(recovered_store)
    replay = ingest_live_local_website_logs(SQLiteStore(database))
    assert (recovered.accepted_event_count, recovered.duplicate_event_count) == (1, 0)
    assert (replay.accepted_event_count, replay.duplicate_event_count) == (0, 1)
    assert recovered_store.live_source_status(FIXED_TENANT_ID)["status"] == "healthy"


def test_source_status_contains_only_bounded_categories_on_invalid_source(tmp_path, monkeypatch):
    log_dir = _temporary_log_paths(monkeypatch, tmp_path)
    log_dir.mkdir(parents=True)
    (log_dir / "access.jsonl").write_text('{"secret":"private raw line"}\n', encoding="utf-8")
    store = SQLiteStore(tmp_path / "private.sqlite3")
    with pytest.raises(RuntimeError):
        ingest_live_local_website_logs(store)
    status = store.live_source_status(FIXED_TENANT_ID)
    assert status["status"] == "failed"
    assert status["error_code"] == "source_invalid"
    assert status["rejected_record_count"] == 1
    assert "private raw line" not in json.dumps(status)


def test_missing_source_is_reported_without_claiming_recovery(tmp_path, monkeypatch):
    _temporary_log_paths(monkeypatch, tmp_path)
    store = SQLiteStore(tmp_path / "private.sqlite3")
    with pytest.raises(RuntimeError, match="ingestion failed"):
        ingest_live_local_website_logs(store)
    status = store.live_source_status(FIXED_TENANT_ID)
    assert status["status"] == "failed"
    assert status["error_code"] == "source_invalid"
    assert status["position_sha256"] is None


def test_conflicting_record_ids_are_rejected_without_partial_storage(tmp_path, monkeypatch):
    log_dir = _temporary_log_paths(monkeypatch, tmp_path)
    log_dir.mkdir(parents=True)
    line = json.loads(_access_line("conflict").decode())
    conflicting = dict(line, actor_ref="synthetic-account-test")
    (log_dir / "access.jsonl").write_bytes(
        (json.dumps(line) + "\n" + json.dumps(conflicting) + "\n").encode()
    )
    store = SQLiteStore(tmp_path / "private.sqlite3")
    with pytest.raises(RuntimeError):
        ingest_live_local_website_logs(store)
    with sqlite3.connect(store.path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM telemetry_events").fetchone()[0] == 0
    status = store.live_source_status(FIXED_TENANT_ID)
    assert status["status"] == "failed"
    assert status["error_code"] == "processing_error"


def test_sqlite_store_failure_is_categorized_without_exposing_details(tmp_path, monkeypatch):
    import sqlite3 as sqlite

    log_dir = _temporary_log_paths(monkeypatch, tmp_path)
    log_dir.mkdir(parents=True)
    (log_dir / "access.jsonl").write_bytes(_access_line("store-fail"))
    store = SQLiteStore(tmp_path / "private.sqlite3")
    monkeypatch.setattr(store, "complete_telemetry_cycle", lambda **_kwargs: (_ for _ in ()).throw(
        sqlite.OperationalError("database path and private details")))
    with pytest.raises(RuntimeError):
        ingest_live_local_website_logs(store)
    status = store.live_source_status(FIXED_TENANT_ID)
    assert status["error_code"] == "store_error"
    assert "private details" not in json.dumps(status)

