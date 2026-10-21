"""Serve the local AegisAI security demo on loopback only."""
from __future__ import annotations

import argparse
import json
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parent / "site"
HOST = "127.0.0.1"
PORT = 8765
PROFILE = "baseline"

SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self'; style-src 'self'; "
        "img-src 'self' data:; connect-src 'self'; object-src 'none'; "
        "base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
    ),
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}


class DemoHandler(SimpleHTTPRequestHandler):
    """Static, read-only site with selectable header profiles."""

    profile = PROFILE

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def end_headers(self) -> None:
        if self.profile == "hardened":
            for name, value in SECURITY_HEADERS.items():
                self.send_header(name, value)
        super().end_headers()

    def do_GET(self) -> None:
        if urlsplit(self.path).path == "/demo-config.json":
            body = json.dumps({"profile": self.profile}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()

    def log_message(self, format: str, *args) -> None:
        # Avoid writing request paths or headers to the console.
        return


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the loopback-only AegisAI website demo")
    parser.add_argument(
        "--profile",
        choices=("baseline", "hardened"),
        default="baseline",
        help="baseline omits the four checked security headers; hardened sets them",
    )
    args = parser.parse_args()
    DemoHandler.profile = args.profile

    server = ThreadingHTTPServer((HOST, PORT), DemoHandler)
    print(f"AegisAI local demo ({args.profile} profile): http://{HOST}:{PORT}/")
    print("Listening on loopback only. Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping demo site.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
