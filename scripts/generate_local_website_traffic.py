"""Send a few harmless fixed requests to the loopback telemetry test website."""

from __future__ import annotations

import argparse
import sys
from urllib.error import HTTPError
from urllib.request import Request, urlopen

BASE_URL = "http://127.0.0.1:8767"
REQUESTS = (
    ("GET", "/"),
    ("GET", "/health"),
    ("POST", "/login-failure"),
    ("POST", "/login-failure"),
    ("POST", "/login-failure"),
    ("GET", "/demo-error"),
    ("GET", "/health"),
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)
    outcomes: list[int] = []
    try:
        for method, route in REQUESTS:
            request = Request(BASE_URL + route, method=method)
            try:
                with urlopen(request, timeout=2) as response:
                    response.read(256)
                    outcomes.append(response.status)
            except HTTPError as response:
                response.read(256)
                outcomes.append(response.code)
    except Exception as exc:
        print(f"loopback traffic generation failed: {exc.__class__.__name__}", file=sys.stderr)
        return 2
    print(f"Generated {len(outcomes)} harmless loopback requests; statuses: {outcomes}")
    print("Requests went only to 127.0.0.1. No credentials or request bodies were sent.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
