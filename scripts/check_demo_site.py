"""Check the fixed local AegisAI demo for its required security headers."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import URLError
from urllib.request import ProxyHandler, build_opener


URL = "http://127.0.0.1:8765/"
ROOT = Path(__file__).resolve().parents[1]
REQUIRED_HEADERS = {
    "Content-Security-Policy": "default-src 'self'",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=()",
}
FINDING_DETAILS = {
    "Content-Security-Policy": (
        "medium",
        "Restricts which sources the browser may load content from.",
        "Set a Content-Security-Policy that matches the site's required resources.",
    ),
    "X-Content-Type-Options": (
        "low",
        "Prevents browsers from guessing a different content type.",
        "Set X-Content-Type-Options to nosniff.",
    ),
    "Referrer-Policy": (
        "low",
        "Controls how much referrer information is sent with navigation requests.",
        "Set Referrer-Policy to strict-origin-when-cross-origin or a stricter policy.",
    ),
    "Permissions-Policy": (
        "low",
        "Restricts access to browser features that this demo does not need.",
        "Set a Permissions-Policy that disables unused browser features.",
    ),
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Check the fixed loopback AegisAI demo site")
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="assessment JSON path (default: profile-specific file under results/)",
    )
    args = parser.parse_args()

    try:
        opener = build_opener(ProxyHandler({}))
        with opener.open(URL, timeout=2) as response:
            headers = response.headers
            status = response.status
        with opener.open(URL + "demo-config.json", timeout=2) as response:
            profile_data = json.loads(response.read().decode("utf-8"))
    except (URLError, TimeoutError, OSError) as exc:
        print(json.dumps({"ok": False, "url": URL, "error": str(exc)}, indent=2))
        return 2
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "url": URL, "error": f"Invalid demo profile response: {exc}"}, indent=2))
        return 2
    if not isinstance(profile_data, dict) or profile_data.get("profile") not in {"baseline", "hardened"}:
        print(json.dumps({"ok": False, "url": URL, "error": "Unknown or malformed demo profile response"}, indent=2))
        return 2

    missing = []
    findings = []
    header_results = []
    for name, expected in REQUIRED_HEADERS.items():
        actual = headers.get(name, "")
        present = expected in actual
        header_results.append({
            "header": name,
            "expected_value": expected,
            "observed_value": actual or None,
            "present": present,
        })
        if not present:
            missing.append(name)
            severity, description, remediation = FINDING_DETAILS[name]
            findings.append({
                "id": "missing_" + name.lower().replace("-", "_"),
                "severity": severity,
                "title": f"Missing or incorrect {name}",
                "description": description,
                "evidence": (
                    f"Observed value: {actual}" if actual
                    else "The response did not include this header."
                ),
                "remediation": remediation,
            })
    profile = profile_data.get("profile", "unknown")
    output_path = args.output or ROOT / "results" / f"demo_site_assessment_{profile}.json"
    passed = status == 200 and not missing and profile == "hardened"
    result = {
        "schema_version": "1.0",
        "assessment_type": "http_security_header_check",
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "passed" if passed else "findings",
        "ok": passed,
        "artifact": str(output_path),
        "url": URL,
        "http_status": status,
        "profile": profile,
        "checked_headers": list(REQUIRED_HEADERS),
        "header_results": header_results,
        "missing_or_incorrect_headers": missing,
        "finding_count": len(findings),
        "findings": findings,
        "limitations": [
            "Checks only the listed HTTP response headers and status code.",
            "Does not assess application vulnerabilities or establish that a website is secure.",
        ],
    }
    rendered = json.dumps(result, indent=2)
    print(rendered)
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered + "\n", encoding="utf-8")
    except OSError as exc:
        print(json.dumps({"artifact_error": str(exc), "output": str(output_path)}, indent=2))
        return 2
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
