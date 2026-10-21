"""Create sanitized, public copies of the local demo assessment reports."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPORTS = {
    "baseline": ROOT / "results" / "demo_site_assessment_baseline.json",
    "hardened": ROOT / "results" / "demo_site_assessment_hardened.json",
}
PUBLIC_DIR = ROOT / "frontend" / "data"


def make_public_copy(source: Path, profile: str) -> dict:
    report = json.loads(source.read_text(encoding="utf-8"))
    if report.get("schema_version") != "1.0" or report.get("profile") != profile:
        raise ValueError(f"Unexpected source assessment schema or profile: {source.name}")
    report.pop("artifact", None)
    report["publication"] = {
        "synthetic": True,
        "precomputed": True,
        "public_execution": False,
        "display": "Sanitized sample from the local AegisAI demo site",
    }
    return report


def main() -> None:
    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
    for profile, source in REPORTS.items():
        destination = PUBLIC_DIR / f"public_demo_assessment_{profile}.json"
        content = json.dumps(make_public_copy(source, profile), ensure_ascii=False, indent=2) + "\n"
        destination.write_text(content, encoding="utf-8")
        print(f"Wrote {destination.relative_to(ROOT)} ({destination.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
