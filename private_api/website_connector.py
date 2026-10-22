"""Bounded adapter for one checked-in synthetic website log sample."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import Field, ValidationError, model_validator

from private_api.telemetry import (
    MAX_INPUT_BYTES,
    MAX_TELEMETRY_EVENTS,
    SyntheticTelemetryBatch,
    SyntheticTelemetryEvent,
    TelemetryEventType,
)
from private_api.telemetry import TelemetryModel

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "demo_site" / "fixtures"
WEBSITE_LOG_FIXTURE = FIXTURE_DIR / "synthetic_website_logs_v1.json"
WEBSITE_SOURCE_REF = "synthetic-demo-site-access-error-logs-v1"
LIVE_WEBSITE_SOURCE_REF = "synthetic-demo-site-live-access-error-logs-v1"
WEBSITE_ASSET_REF = "synthetic-demo-website"
SOURCE_ID = "local_synthetic_fixture_v1"
SYNTHETIC_LABEL = "SYNTHETIC - NOT REAL CLIENT DATA"


class WebsiteLogRecord(TelemetryModel):
    record_id: str = Field(min_length=1, max_length=64, pattern=r"^wlog-[a-zA-Z0-9_-]+$")
    occurred_at: datetime
    record_type: Literal["http_access", "auth_failure", "request_rate", "application_error"]
    actor_ref: Literal["synthetic-user-a", "synthetic-account-test", "synthetic-monitor"]
    evidence_id: str = Field(min_length=1, max_length=80, pattern=r"^website-evidence-[a-zA-Z0-9_-]+$")
    method: Literal["GET", "POST", "HEAD"] | None = None
    route_code: Literal["home", "login", "health", "api_read", "not_found"] | None = None
    status_code: int | None = Field(default=None, ge=100, le=599)
    request_count: int | None = Field(default=None, ge=1, le=100_000)
    window_seconds: int | None = Field(default=None, ge=1, le=600)
    error_code: Literal[
        "HANDLER_TIMEOUT", "SAFE_VALIDATION_REJECTED", "RESOURCE_NOT_FOUND", "DEMO_ERROR_RESPONSE",
    ] | None = None

    @model_validator(mode="after")
    def fields_match_record_type(self) -> WebsiteLogRecord:
        if self.occurred_at.tzinfo is None or self.occurred_at.utcoffset() is None:
            raise ValueError("occurred_at must include a timezone offset")
        groups = {
            "http_access": (self.method, self.route_code, self.status_code),
            "auth_failure": (self.method, self.route_code, self.status_code),
            "request_rate": (self.request_count, self.window_seconds),
            "application_error": (self.error_code,),
        }
        expected = groups[self.record_type]
        if any(value is None for value in expected):
            raise ValueError("record is missing fields required by its record_type")
        all_values = (self.method, self.route_code, self.status_code, self.request_count,
                      self.window_seconds, self.error_code)
        if sum(value is not None for value in all_values) != len(expected):
            raise ValueError("record contains fields not allowed for its record_type")
        if self.record_type == "auth_failure" and (self.method != "POST" or self.route_code != "login" or self.status_code not in {401, 403}):
            raise ValueError("auth_failure must be a failed synthetic login request")
        return self


class WebsiteLogFile(TelemetryModel):
    schema_version: Literal["1.0"]
    source_id: Literal["synthetic_demo_site_access_error_logs_v1", "synthetic_demo_site_live_access_error_logs_v1"]
    data_classification: Literal["synthetic"]
    label: Literal["SYNTHETIC WEBSITE LOGS - NOT REAL REQUESTS"]
    generated_at: datetime
    records: list[WebsiteLogRecord] = Field(min_length=1, max_length=MAX_TELEMETRY_EVENTS)

    @model_validator(mode="after")
    def generated_time_is_aware(self) -> WebsiteLogFile:
        if self.generated_at.tzinfo is None or self.generated_at.utcoffset() is None:
            raise ValueError("generated_at must include a timezone offset")
        return self


class WebsiteLogInputError(ValueError):
    """Safe, content-independent website sample rejection."""


def _validate_bytes(raw: bytes) -> WebsiteLogFile:
    if len(raw) > MAX_INPUT_BYTES:
        raise WebsiteLogInputError("website log sample exceeds the 1 MiB size limit")
    try:
        return WebsiteLogFile.model_validate_json(raw)
    except Exception as exc:
        issues = exc.errors() if isinstance(exc, ValidationError) else []
        raise WebsiteLogInputError(f"website log sample validation failed: {len(issues)} issue(s)") from None


def _read_approved_file(path: Path, approved_directory: Path) -> bytes:
    try:
        approved = approved_directory.resolve(strict=True)
        if path.is_symlink() or path.parent.resolve(strict=True) != approved:
            raise WebsiteLogInputError("website log source is outside the approved fixture")
        if path.resolve(strict=True) != approved / path.name or not path.is_file():
            raise WebsiteLogInputError("website log source is not an approved regular file")
        with path.open("rb") as source:
            raw = source.read(MAX_INPUT_BYTES + 1)
    except WebsiteLogInputError:
        raise
    except OSError as exc:
        raise WebsiteLogInputError(f"website log source unavailable: {exc.__class__.__name__}") from None
    if len(raw) > MAX_INPUT_BYTES:
        raise WebsiteLogInputError("website log sample exceeds the 1 MiB size limit")
    return raw


def read_website_log_fixture() -> WebsiteLogFile:
    """Read only the fixed source; no caller-provided path or remote source is accepted."""
    try:
        repository_root = ROOT.resolve(strict=True)
        approved_directory = FIXTURE_DIR.resolve(strict=True)
        approved_directory.relative_to(repository_root)
        if (ROOT / "demo_site").is_symlink() or FIXTURE_DIR.is_symlink():
            raise WebsiteLogInputError("website log source is outside the approved fixture")
    except WebsiteLogInputError:
        raise
    except (OSError, ValueError):
        raise WebsiteLogInputError("website log source is outside the approved fixture") from None
    return _validate_bytes(_read_approved_file(WEBSITE_LOG_FIXTURE, FIXTURE_DIR))


def to_telemetry_batch(
    logs: WebsiteLogFile, *,
    source_ref: Literal[
        "synthetic-demo-site-access-error-logs-v1", "synthetic-demo-site-live-access-error-logs-v1",
    ] = WEBSITE_SOURCE_REF,
) -> SyntheticTelemetryBatch:
    events: list[SyntheticTelemetryEvent] = []
    for record in logs.records:
        suffix = record.record_id.removeprefix("wlog-")
        event_type = {
            "http_access": TelemetryEventType.HTTP_ACCESS,
            "auth_failure": TelemetryEventType.AUTH_FAILURE,
            "request_rate": TelemetryEventType.REQUEST_RATE,
            "application_error": TelemetryEventType.APPLICATION_ERROR,
        }[record.record_type]
        fields: dict[str, object] = {}
        if record.record_type in {"http_access", "auth_failure"}:
            fields.update(http_method=record.method, route_code=record.route_code, status_code=record.status_code)
        elif record.record_type == "request_rate":
            fields.update(request_count=record.request_count, window_seconds=record.window_seconds)
        else:
            fields.update(error_code=record.error_code)
        events.append(SyntheticTelemetryEvent(
            event_id=f"syn-website-{suffix}", occurred_at=record.occurred_at,
            event_type=event_type, asset_ref=WEBSITE_ASSET_REF,
            actor_ref=record.actor_ref, source_ref=source_ref,
            evidence_ref=f"synthetic-{record.evidence_id}", **fields,
        ))
    try:
        return SyntheticTelemetryBatch(
            schema_version="1.0", source_id=SOURCE_ID,
            data_classification="synthetic", label=SYNTHETIC_LABEL,
            generated_at=logs.generated_at.astimezone(timezone.utc), events=events,
        )
    except ValidationError:
        raise WebsiteLogInputError("website log sample could not be mapped to telemetry") from None
