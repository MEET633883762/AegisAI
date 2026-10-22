"""Harmless loopback test site that writes its own bounded synthetic logs."""

from __future__ import annotations

import argparse
import sys
import threading
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from private_api.website_connector import WebsiteLogRecord

HOST = "127.0.0.1"
PORT = 8767
LOCAL_ROOT = ROOT / ".aegisai-local"
LOG_DIR = LOCAL_ROOT / "website-telemetry"
ACCESS_LOG = LOG_DIR / "access.jsonl"
ERROR_LOG = LOG_DIR / "errors.jsonl"
_LOG_LOCK = threading.Lock()


def _prepare_log_directory() -> None:
    local_root = LOCAL_ROOT
    local_root.mkdir(parents=True, exist_ok=True)
    if local_root.is_symlink() or LOG_DIR.is_symlink():
        raise OSError("local telemetry log directory must not be a symlink")
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    try:
        LOG_DIR.resolve(strict=True).relative_to(local_root.resolve(strict=True))
    except ValueError:
        raise OSError("local telemetry log directory is outside its approved parent") from None
    for path in (ACCESS_LOG, ERROR_LOG):
        if path.is_symlink():
            raise OSError("local telemetry log files must not be symlinks")


def _append_record(path: Path, record: WebsiteLogRecord) -> None:
    _prepare_log_directory()
    line = record.model_dump_json(exclude_none=True).encode("utf-8") + b"\n"
    with _LOG_LOCK:
        with path.open("ab") as output:
            output.write(line)
            output.flush()


class TelemetryHandler(BaseHTTPRequestHandler):
    server_version = "AegisAI-Synthetic-Demo"
    sys_version = ""

    def _respond(self, *, status: int, route_code: str, body: bytes, method: str) -> None:
        request_token = uuid.uuid4().hex
        auth_failure = method == "POST" and route_code == "login" and status in {401, 403}
        record_type = "auth_failure" if auth_failure else "http_access"
        try:
            access = WebsiteLogRecord(
                record_id=f"wlog-access-{request_token}",
                occurred_at=datetime.now(timezone.utc), record_type=record_type,
                actor_ref="synthetic-account-test" if auth_failure else "synthetic-user-a",
                evidence_id=f"website-evidence-access-{request_token}", method=method,
                route_code=route_code, status_code=status,
            )
            _append_record(ACCESS_LOG, access)
            if status >= 500:
                error = WebsiteLogRecord(
                    record_id=f"wlog-error-{request_token}", occurred_at=access.occurred_at,
                    record_type="application_error", actor_ref="synthetic-monitor",
                    evidence_id=f"website-evidence-error-{request_token}", error_code="DEMO_ERROR_RESPONSE",
                )
                _append_record(ERROR_LOG, error)
        except (OSError, ValueError):
            body = b"Synthetic local demo log unavailable.\n"
            status = 503

        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        if method != "HEAD":
            self.wfile.write(body)

    def do_GET(self) -> None:
        route = urlsplit(self.path).path
        routes = {
            "/": (200, "home", b"AegisAI synthetic telemetry test site.\n"),
            "/health": (200, "health", b"Synthetic site is running.\n"),
            "/demo-error": (500, "health", b"Harmless synthetic error response.\n"),
        }
        status, route_code, body = routes.get(route, (404, "not_found", b"Synthetic route not found.\n"))
        self._respond(status=status, route_code=route_code, body=body, method="GET")

    def do_POST(self) -> None:
        route = urlsplit(self.path).path
        if route != "/login-failure":
            self._respond(status=404, route_code="not_found", body=b"Synthetic route not found.\n", method="POST")
            return
        # This fixed route consumes no credentials or request body.
        content_length = self.headers.get("Content-Length", "0")
        if content_length != "0":
            self.close_connection = True
            self._respond(status=400, route_code="login", body=b"Request body is not accepted.\n", method="POST")
            return
        self._respond(status=401, route_code="login", body=b"Synthetic login attempt rejected.\n", method="POST")

    def log_message(self, _format: str, *_args) -> None:
        # Never send raw paths, headers, or client data to console logs.
        return


class LoopbackTelemetryServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def create_server() -> LoopbackTelemetryServer:
    _prepare_log_directory()
    return LoopbackTelemetryServer((HOST, PORT), TelemetryHandler)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)
    try:
        server = create_server()
    except OSError as exc:
        print(f"local website could not start: {exc.__class__.__name__}", file=sys.stderr)
        return 2
    print(f"Synthetic test website listening at http://{HOST}:{PORT}/ (loopback only)")
    print("No credentials are collected. Press Ctrl+C to stop.")
    try:
        server.serve_forever(poll_interval=0.1)
    except KeyboardInterrupt:
        print("Stopping synthetic test website.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
