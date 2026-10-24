from __future__ import annotations

import sqlite3
from local_assessment.controller import _exchange_http
from scripts import run_local_assessment


def _successful_local_response(path, request_deadline, assessment_deadline):
    return 200, {
        "content-security-policy": "default-src 'self'",
        "x-content-type-options": "nosniff",
        "referrer-policy": "no-referrer",
        "permissions-policy": "camera=()",
    }, b"synthetic demo response"


def _assessment_response(monkeypatch):
    monkeypatch.setattr(
        "local_assessment.controller._exchange_http", _successful_local_response,
    )


def test_database_argument_persists_and_repeated_run_deduplicates(tmp_path, monkeypatch, capsys):
    database = tmp_path / "presentation.sqlite3"
    _assessment_response(monkeypatch)

    assert run_local_assessment.main(["--database", str(database)]) == 0
    assert run_local_assessment.main(["--database", str(database)]) == 0
    assert database.is_file()

    from private_api.store import SQLiteStore

    report = SQLiteStore(database).latest_assessment_report("synthetic-org-demo")
    assert report is not None
    assert len(report.raw_observations) == 3
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM website_assessment_reports").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM website_assessment_observations").fetchone()[0] == 3
        assert connection.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0] == 2
    assert '"report_id"' in capsys.readouterr().out


def test_omitted_database_argument_keeps_default_path_without_opening_real_database(
    tmp_path, monkeypatch,
):
    safe_root = tmp_path / "repo-root"
    safe_root.mkdir()
    expected_default = safe_root / ".aegisai-local" / "private_api.sqlite3"
    assert run_local_assessment.DEFAULT_DATABASE == (
        run_local_assessment.ROOT / ".aegisai-local" / "private_api.sqlite3"
    )
    monkeypatch.setattr(run_local_assessment, "ROOT", safe_root)
    monkeypatch.setattr(run_local_assessment, "DEFAULT_DATABASE", expected_default)
    _assessment_response(monkeypatch)

    assert run_local_assessment.main([]) == 0
    assert expected_default.is_file()

