"""Read fixed JSONL logs produced by the loopback synthetic website only."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from private_api.telemetry import MAX_INPUT_BYTES, MAX_TELEMETRY_EVENTS, SyntheticTelemetryBatch
from private_api.website_connector import (
    LIVE_WEBSITE_SOURCE_REF,
    WebsiteLogFile,
    WebsiteLogInputError,
    WebsiteLogRecord,
    to_telemetry_batch,
)

ROOT = Path(__file__).resolve().parents[1]
LOCAL_ROOT = ROOT / ".aegisai-local"
LOG_DIR = LOCAL_ROOT / "website-telemetry"
ACTIVE_ACCESS = LOG_DIR / "access.jsonl"
ROTATED_ACCESS = LOG_DIR / "access.jsonl.1"
OLDER_ROTATED_ACCESS = (LOG_DIR / "access.jsonl.2", LOG_DIR / "access.jsonl.3")
ACTIVE_ERRORS = LOG_DIR / "errors.jsonl"
ROTATED_ERRORS = LOG_DIR / "errors.jsonl.1"
OLDER_ROTATED_ERRORS = (LOG_DIR / "errors.jsonl.2", LOG_DIR / "errors.jsonl.3")
APPROVED_LOG_FILES = (
    *reversed(OLDER_ROTATED_ACCESS), ROTATED_ACCESS, ACTIVE_ACCESS,
    *reversed(OLDER_ROTATED_ERRORS), ROTATED_ERRORS, ACTIVE_ERRORS,
)
MAX_LOG_FILE_BYTES = MAX_INPUT_BYTES
MAX_LOG_LINE_BYTES = 16_384


def _read_fixed_log(path: Path) -> bytes | None:
    try:
        if path not in APPROVED_LOG_FILES:
            raise WebsiteLogInputError("live website log source is not in the approved fixed file list")
        repository_root = ROOT.resolve(strict=True)
        local_root = LOCAL_ROOT.resolve(strict=True)
        log_root = LOG_DIR.resolve(strict=True)
        local_root.relative_to(repository_root)
        log_root.relative_to(local_root)
        if LOCAL_ROOT.is_symlink() or LOG_DIR.is_symlink() or path.is_symlink():
            raise WebsiteLogInputError("live website log source is outside its approved local directory")
        if path.parent.resolve(strict=True) != log_root:
            raise WebsiteLogInputError("live website log source is outside its approved local directory")
        if not path.exists():
            return None
        if path.resolve(strict=True) != log_root / path.name or not path.is_file():
            raise WebsiteLogInputError("live website log source is not an approved regular file")
        with path.open("rb") as source:
            raw = source.read(MAX_LOG_FILE_BYTES + 1)
    except WebsiteLogInputError:
        raise
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise WebsiteLogInputError(f"live website log source unavailable: {exc.__class__.__name__}") from None
    if len(raw) > MAX_LOG_FILE_BYTES:
        raise WebsiteLogInputError("live website log file exceeds the 1 MiB size limit")
    return raw


def _parse_complete_records(raw: bytes) -> list[WebsiteLogRecord]:
    records: list[WebsiteLogRecord] = []
    for line in raw.splitlines(keepends=True):
        if len(line) > MAX_LOG_LINE_BYTES:
            raise WebsiteLogInputError("live website log line exceeds the 16 KiB size limit")
        if not line.endswith(b"\n"):
            # A write still in progress is reread on the next ingestion cycle.
            continue
        if not line.strip():
            continue
        try:
            records.append(WebsiteLogRecord.model_validate_json(line))
        except ValidationError as exc:
            raise WebsiteLogInputError(
                f"live website log record validation failed: {len(exc.errors())} issue(s)"
            ) from None
        if len(records) > MAX_TELEMETRY_EVENTS:
            raise WebsiteLogInputError("live website log sample exceeds the 500 record limit")
    return records


@dataclass(frozen=True)
class LiveWebsiteLogSnapshot:
    batch: SyntheticTelemetryBatch
    position_sha256: str
    position_bytes: int


def read_live_website_log_snapshot() -> LiveWebsiteLogSnapshot:
    """Read the active logs and three fixed rotations; accepts no path argument."""
    records: list[WebsiteLogRecord] = []
    observed_file = False
    digest = hashlib.sha256()
    total_bytes = 0
    for path in APPROVED_LOG_FILES:
        raw = _read_fixed_log(path)
        if raw is None:
            continue
        observed_file = True
        digest.update(path.name.encode("ascii"))
        digest.update(b"\0")
        digest.update(raw)
        total_bytes += len(raw)
        records.extend(_parse_complete_records(raw))
        if len(records) > MAX_TELEMETRY_EVENTS:
            raise WebsiteLogInputError("live website log sample exceeds the 500 record limit")
    if not observed_file or not records:
        raise WebsiteLogInputError("no complete live website log records are available")
    log_file = WebsiteLogFile(
        schema_version="1.0", source_id="synthetic_demo_site_live_access_error_logs_v1",
        data_classification="synthetic", label="SYNTHETIC WEBSITE LOGS - NOT REAL REQUESTS",
        generated_at=datetime.now(timezone.utc), records=records,
    )
    return LiveWebsiteLogSnapshot(
        batch=to_telemetry_batch(log_file, source_ref=LIVE_WEBSITE_SOURCE_REF),
        position_sha256=digest.hexdigest(),
        position_bytes=total_bytes,
    )


def read_live_website_log_batch() -> SyntheticTelemetryBatch:
    """Compatibility wrapper returning only the validated event batch."""
    return read_live_website_log_snapshot().batch
