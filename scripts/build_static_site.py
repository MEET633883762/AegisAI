"""Publish only the strict allowlist from the production frontend build."""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "frontend"
BUILD = SOURCE / ".vite-build"
DEFAULT_OUTPUT = ROOT / "dist" / "aegisai-static"
STATIC_ALLOWLIST = (
    "_headers",
    "index.html",
    "dashboard.html",
    "privacy.html",
    "assets/app.css",
    "assets/main.js",
    "assets/public_demo_episode.json",
    "assets/public_demo_assessment_baseline.json",
    "assets/public_demo_assessment_hardened.json",
)


def build(output: Path) -> tuple[Path, ...]:
    output = output.resolve()
    if output == SOURCE.resolve() or SOURCE.resolve() in output.parents:
        raise ValueError("Static output must be outside frontend/.")
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"Refusing to publish into non-empty output directory: {output}")
    if not BUILD.is_dir():
        raise FileNotFoundError("Production frontend build is missing; run npm ci and npm run build in frontend/.")
    output.mkdir(parents=True, exist_ok=True)

    copied = []
    for relative in STATIC_ALLOWLIST:
        source = SOURCE / "_headers" if relative == "_headers" else BUILD / relative
        if not source.is_file():
            raise FileNotFoundError(f"Allowlisted production asset is missing: {relative}")
        destination = output / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        copied.append(destination)

    actual = {item.relative_to(output).as_posix() for item in output.rglob("*") if item.is_file()}
    expected = set(STATIC_ALLOWLIST)
    if actual != expected:
        raise RuntimeError(f"Static output does not match allowlist: extra={actual - expected}, missing={expected - actual}")
    return tuple(copied)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Output directory (must be absent or empty).")
    args = parser.parse_args()
    try:
        files = build(args.output)
    except (FileNotFoundError, FileExistsError, ValueError, RuntimeError) as error:
        print(error, file=sys.stderr)
        return 1
    print(f"Prepared {len(files)} allowlisted static files in {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
