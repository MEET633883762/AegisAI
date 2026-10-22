"""Validated replay of the fixed synthetic scenario library against existing rules."""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from private_api.telemetry import (
    SyntheticTelemetryEvent,
    TelemetryFinding,
    detect_findings,
    normalize_and_deduplicate,
)

MAX_SCENARIO_LIBRARY_BYTES = 1_048_576
MAX_SCENARIOS = 100
MAX_EVENTS_PER_SCENARIO = 100
MAX_EVENTS_PER_LIBRARY = 1_000
SUPPORTED_RULE_IDS = frozenset({"AUTH-001", "WEB-001", "APP-001", "VULN-001", "CONFIG-001"})
RULE_EVENT_TYPES = {
    "AUTH-001": frozenset({"auth_failure", "auth_success"}),
    "WEB-001": frozenset({"request_rate_indicator"}),
    "APP-001": frozenset({"simulated_suspicious_activity"}),
    "VULN-001": frozenset({"synthetic_vulnerability_finding"}),
    "CONFIG-001": frozenset({"synthetic_configuration_finding"}),
}


class ReplayModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class ReplayScenario(ReplayModel):
    scenario_id: str = Field(min_length=1, max_length=40, pattern=r"^scenario-[a-z0-9-]+$")
    scenario_version: Literal["1.0"]
    data_classification: Literal["synthetic"]
    scenario_class: Literal["positive", "benign"]
    category: Literal["authentication", "request_rate", "application", "vulnerability", "configuration", "control"]
    description: str = Field(min_length=1, max_length=300)
    events: list[SyntheticTelemetryEvent] = Field(min_length=1, max_length=MAX_EVENTS_PER_SCENARIO)
    expected_rule_ids: list[str] = Field(max_length=len(SUPPORTED_RULE_IDS))
    expected_evidence_refs: list[str] = Field(max_length=MAX_EVENTS_PER_SCENARIO)
    rationale: str = Field(min_length=1, max_length=500)

    @field_validator("expected_rule_ids")
    @classmethod
    def known_unique_rules(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)) or not set(value).issubset(SUPPORTED_RULE_IDS):
            raise ValueError("expected rule IDs must be known and unique")
        return value

    @field_validator("expected_evidence_refs")
    @classmethod
    def unique_expected_evidence(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("expected evidence references must be unique")
        return value

    @model_validator(mode="after")
    def expected_results_match_input(self) -> ReplayScenario:
        if self.scenario_class == "benign" and self.expected_rule_ids:
            raise ValueError("benign scenarios must expect no findings")
        if self.scenario_class == "positive" and not self.expected_rule_ids:
            raise ValueError("positive scenarios must declare an expected rule")
        refs = {event.evidence_ref for event in self.events}
        if not set(self.expected_evidence_refs).issubset(refs):
            raise ValueError("expected evidence must reference an event in this scenario")
        types = {event.event_type.value for event in self.events}
        for rule_id in self.expected_rule_ids:
            if not types.intersection(RULE_EVENT_TYPES[rule_id]):
                raise ValueError(f"expected rule {rule_id} has no compatible input event")
        if self.expected_rule_ids and not self.expected_evidence_refs:
            raise ValueError("positive scenarios must declare expected evidence")
        return self


class ReplayScenarioLibrary(ReplayModel):
    schema_version: Literal["1.0"]
    library_id: Literal["aegisai_synthetic_replay_library"]
    library_version: Literal["1.0"]
    data_classification: Literal["synthetic"]
    label: Literal["SYNTHETIC SIMULATION - NOT REAL ATTACK TRAFFIC"]
    scenarios: list[ReplayScenario] = Field(min_length=1, max_length=MAX_SCENARIOS)

    @model_validator(mode="after")
    def ids_are_unambiguous_and_bounded(self) -> ReplayScenarioLibrary:
        if len({scenario.scenario_id for scenario in self.scenarios}) != len(self.scenarios):
            raise ValueError("scenario IDs must be unique")
        event_ids: set[str] = set()
        evidence_refs: set[str] = set()
        event_count = 0
        for scenario in self.scenarios:
            event_count += len(scenario.events)
            for event in scenario.events:
                if event.event_id in event_ids:
                    raise ValueError("event IDs must be unique across the scenario library")
                if event.evidence_ref in evidence_refs:
                    raise ValueError("evidence references must be unique across the scenario library")
                event_ids.add(event.event_id)
                evidence_refs.add(event.evidence_ref)
        if event_count > MAX_EVENTS_PER_LIBRARY:
            raise ValueError("scenario library exceeds the total event limit")
        return self


class RuleCounts(ReplayModel):
    true_positives: int = Field(ge=0)
    false_positives: int = Field(ge=0)
    true_negatives: int = Field(ge=0)
    false_negatives: int = Field(ge=0)
    precision: float | None = Field(ge=0, le=1)
    recall: float | None = Field(ge=0, le=1)
    f1: float | None = Field(ge=0, le=1)


class PerRuleResult(RuleCounts):
    rule_id: str


class ReplayScenarioResult(ReplayModel):
    scenario_id: str
    category: str
    scenario_class: Literal["positive", "benign"]
    description: str
    rationale: str
    expected_rule_ids: list[str]
    observed_rule_ids: list[str]
    expected_evidence_refs: list[str]
    observed_evidence_refs: list[str]
    missing_rule_ids: list[str]
    unexpected_rule_ids: list[str]
    evidence_complete: bool | None
    findings: list[TelemetryFinding]


class GapRecommendation(ReplayModel):
    scenario_id: str
    rule_id: str
    gap_type: Literal["missed_detection", "unexpected_alert", "missing_evidence"]
    recommendation: str = Field(min_length=1, max_length=500)


class ReplayEvaluationReport(ReplayModel):
    schema_version: Literal["1.0"]
    report_type: Literal["aegisai_synthetic_detection_gap_report"]
    replay_id: str = Field(pattern=r"^replay-[a-f0-9]{16}$")
    library_id: str
    library_version: str
    library_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    data_classification: Literal["synthetic"]
    label: Literal["SYNTHETIC SIMULATION - NOT REAL ATTACK TRAFFIC"]
    started_at_utc: datetime
    finished_at_utc: datetime
    scenario_count: int = Field(ge=1)
    positive_scenario_count: int = Field(ge=0)
    benign_scenario_count: int = Field(ge=0)
    rule_ids: list[str]
    counts: RuleCounts
    per_rule: list[PerRuleResult]
    scenario_detection_coverage: float | None = Field(ge=0, le=1)
    covered_positive_scenarios: int = Field(ge=0)
    expected_positive_scenarios: int = Field(ge=0)
    evidence_completeness: float | None = Field(ge=0, le=1)
    complete_expected_pairs: int = Field(ge=0)
    expected_pairs: int = Field(ge=0)
    scenarios: list[ReplayScenarioResult]
    missed_detections: list[dict[str, str]]
    unexpected_alerts: list[dict[str, str]]
    recommendations: list[GapRecommendation]
    limitations: list[str] = Field(min_length=1)

    @field_validator("finished_at_utc")
    @classmethod
    def finish_not_before_start(cls, value: datetime, info):
        start = info.data.get("started_at_utc")
        if start is not None and value < start:
            raise ValueError("finished_at_utc must not precede started_at_utc")
        return value


class ReplayInputError(ValueError):
    """Safe, input-independent scenario validation error."""


def load_scenario_library_bytes(raw: bytes) -> ReplayScenarioLibrary:
    if len(raw) > MAX_SCENARIO_LIBRARY_BYTES:
        raise ReplayInputError("scenario library exceeds the 1 MiB size limit")
    try:
        return ReplayScenarioLibrary.model_validate_json(raw)
    except ValidationError as exc:
        raise ReplayInputError(f"scenario library validation failed: {len(exc.errors())} issue(s)") from None


def read_scenario_library(path: Path) -> ReplayScenarioLibrary:
    try:
        with path.open("rb") as source:
            raw = source.read(MAX_SCENARIO_LIBRARY_BYTES + 1)
    except OSError as exc:
        raise ReplayInputError(f"could not read scenario library: {exc.__class__.__name__}") from None
    return load_scenario_library_bytes(raw)


def _ratios(tp: int, fp: int, tn: int, fn: int) -> RuleCounts:
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    f1_denominator = 2 * tp + fp + fn
    f1 = (2 * tp) / f1_denominator if f1_denominator else None
    return RuleCounts(true_positives=tp, false_positives=fp, true_negatives=tn,
                      false_negatives=fn, precision=precision, recall=recall, f1=f1)


def _scenario_tenant(scenario_id: str) -> str:
    suffix = re.sub(r"[^a-z0-9-]", "-", scenario_id.removeprefix("scenario-"))[:36]
    return f"synthetic-org-replay-{suffix}"


def evaluate_scenario_library(
    library: ReplayScenarioLibrary,
    *,
    replay_id: str | None = None,
    started_at: datetime | None = None,
    finished_at: datetime | None = None,
) -> ReplayEvaluationReport:
    """Run each scenario independently and compare labels against actual rule IDs."""
    start = (started_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    run_id = replay_id or f"replay-{uuid.uuid4().hex[:16]}"
    if not re.fullmatch(r"replay-[a-f0-9]{16}", run_id):
        raise ValueError("replay ID must use replay- plus 16 lowercase hex characters")
    scenario_results: list[ReplayScenarioResult] = []
    missed: list[dict[str, str]] = []
    unexpected: list[dict[str, str]] = []
    recommendations: list[GapRecommendation] = []
    matrix: dict[str, list[int]] = {rule: [0, 0, 0, 0] for rule in sorted(SUPPORTED_RULE_IDS)}
    expected_pairs = complete_pairs = 0
    positive_scenarios = covered_scenarios = 0

    for scenario in library.scenarios:
        normalized, _duplicates = normalize_and_deduplicate(
            # Scenario validation has already established one unambiguous local input set.
            _scenario_batch(scenario)
        )
        findings = detect_findings(normalized, tenant_id=_scenario_tenant(scenario.scenario_id))
        observed = {item.rule_id for item in findings}
        expected = set(scenario.expected_rule_ids)
        actual_evidence_by_rule = {
            rule: {ref for finding in findings if finding.rule_id == rule for ref in finding.evidence_refs}
            for rule in SUPPORTED_RULE_IDS
        }
        missing = sorted(expected - observed)
        extra = sorted(observed - expected)
        for rule in SUPPORTED_RULE_IDS:
            expected_match, observed_match = rule in expected, rule in observed
            bucket = (0 if expected_match and observed_match else
                      1 if not expected_match and observed_match else
                      2 if not expected_match and not observed_match else 3)
            matrix[rule][bucket] += 1
            if expected_match:
                expected_pairs += 1
                evidence_ok = set(scenario.expected_evidence_refs).issubset(actual_evidence_by_rule[rule])
                if observed_match and evidence_ok:
                    complete_pairs += 1
                if not observed_match:
                    missed.append({"scenario_id": scenario.scenario_id, "rule_id": rule})
                    recommendations.append(GapRecommendation(
                        scenario_id=scenario.scenario_id, rule_id=rule, gap_type="missed_detection",
                        recommendation=f"Review rule {rule} against the labeled evidence in {scenario.scenario_id}; the expected rule did not match.",
                    ))
                elif not evidence_ok:
                    recommendations.append(GapRecommendation(
                        scenario_id=scenario.scenario_id, rule_id=rule, gap_type="missing_evidence",
                        recommendation=f"Preserve all labeled evidence references for rule {rule} in {scenario.scenario_id}; the rule matched but expected evidence was incomplete.",
                    ))
        if scenario.scenario_class == "positive":
            positive_scenarios += 1
            if not missing:
                covered_scenarios += 1
        for rule in extra:
            unexpected.append({"scenario_id": scenario.scenario_id, "rule_id": rule})
            recommendations.append(GapRecommendation(
                scenario_id=scenario.scenario_id, rule_id=rule, gap_type="unexpected_alert",
                recommendation=f"Review rule {rule}'s applicability to {scenario.scenario_id}; this scenario is labeled without that detection.",
            ))
        observed_evidence = sorted({ref for finding in findings for ref in finding.evidence_refs})
        evidence_complete = None if not expected else all(
            set(scenario.expected_evidence_refs).issubset(actual_evidence_by_rule[rule])
            for rule in expected
        )
        scenario_results.append(ReplayScenarioResult(
            scenario_id=scenario.scenario_id, category=scenario.category,
            scenario_class=scenario.scenario_class, description=scenario.description,
            rationale=scenario.rationale,
            expected_rule_ids=sorted(expected), observed_rule_ids=sorted(observed),
            expected_evidence_refs=sorted(scenario.expected_evidence_refs),
            observed_evidence_refs=observed_evidence, missing_rule_ids=missing,
            unexpected_rule_ids=extra, evidence_complete=evidence_complete, findings=findings,
        ))

    per_rule = [PerRuleResult(rule_id=rule, **_ratios(*matrix[rule]).model_dump())
                for rule in sorted(matrix)]
    total = [sum(matrix[rule][index] for rule in matrix) for index in range(4)]
    counts = _ratios(*total)
    finish = (finished_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    return ReplayEvaluationReport(
        schema_version="1.0", report_type="aegisai_synthetic_detection_gap_report",
        replay_id=run_id, library_id=library.library_id, library_version=library.library_version,
        library_sha256=library_fingerprint(library),
        data_classification="synthetic", label="SYNTHETIC SIMULATION - NOT REAL ATTACK TRAFFIC",
        started_at_utc=start, finished_at_utc=finish,
        scenario_count=len(library.scenarios),
        positive_scenario_count=sum(item.scenario_class == "positive" for item in library.scenarios),
        benign_scenario_count=sum(item.scenario_class == "benign" for item in library.scenarios),
        rule_ids=sorted(SUPPORTED_RULE_IDS), counts=counts, per_rule=per_rule,
        scenario_detection_coverage=covered_scenarios / positive_scenarios if positive_scenarios else None,
        covered_positive_scenarios=covered_scenarios, expected_positive_scenarios=positive_scenarios,
        evidence_completeness=complete_pairs / expected_pairs if expected_pairs else None,
        complete_expected_pairs=complete_pairs, expected_pairs=expected_pairs,
        scenarios=scenario_results, missed_detections=missed, unexpected_alerts=unexpected,
        recommendations=recommendations,
        limitations=[
            "All scenarios and evidence are synthetic; the results do not establish real-world detection accuracy.",
            "Metrics describe only the small, hand-labeled scenario library and are not statistical estimates.",
            "Replay calls deterministic local rules only; it performs no network activity or defensive actions.",
        ],
    )


def _scenario_batch(scenario: ReplayScenario):
    """Adapt already-validated scenario records to the existing telemetry normalizer."""
    from private_api.telemetry import SyntheticTelemetryBatch

    event_time = max(event.occurred_at for event in scenario.events)
    return SyntheticTelemetryBatch(
        schema_version="1.0", source_id="local_synthetic_fixture_v1", data_classification="synthetic",
        label="SYNTHETIC - NOT REAL CLIENT DATA", generated_at=event_time, events=scenario.events,
    )


def report_json(report: ReplayEvaluationReport) -> str:
    return json.dumps(report.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n"


def library_fingerprint(library: ReplayScenarioLibrary) -> str:
    """Stable content fingerprint; replay IDs remain unique per invocation."""
    return hashlib.sha256(library.model_dump_json().encode("utf-8")).hexdigest()
