"""Deterministic, isolated metrics for the fixed Phase 6A synthetic dataset."""

from __future__ import annotations

import hashlib
import json
from typing import Callable, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from platform_prototype import pipeline as prototype_pipeline
from platform_prototype.evaluation_dataset import (
    EvaluationDataset,
    EvaluationScenario,
    _input_rejection_category,
    dataset_fingerprint,
    validate_detector_input,
)
from platform_prototype.replay import RULE_EVENT_TYPES, SUPPORTED_RULE_IDS
from private_api import telemetry
from private_api.telemetry import TelemetryFinding, detect_findings

EVALUATION_SCHEMA_VERSION = "1.0"
MAX_REPORT_BYTES = 1_048_576
COUNTING_UNIT = "one scenario-by-supported-rule pair; five pairs per accepted scenario"


class EvaluationModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class MetricValue(EvaluationModel):
    value: float | None
    denominator: int = Field(ge=0)
    status: Literal["defined", "undefined_zero_denominator"]


class ConfusionCounts(EvaluationModel):
    true_positives: int = Field(ge=0)
    false_positives: int = Field(ge=0)
    true_negatives: int = Field(ge=0)
    false_negatives: int = Field(ge=0)


class Metrics(EvaluationModel):
    precision: MetricValue
    recall: MetricValue
    f1: MetricValue
    false_positive_rate: MetricValue
    false_negative_rate: MetricValue


class ScenarioDiagnostic(EvaluationModel):
    scenario_id: str
    category: str
    input_validity: Literal["accepted", "rejected"]
    expected_rejection_category: str | None
    observed_rejection_category: str | None
    expected_finding_types: list[str]
    actual_finding_types: list[str]
    missing_expected_types: list[str]
    unexpected_types: list[str]
    required_evidence: dict[str, list[str]]
    observed_evidence_by_type: dict[str, list[str]]
    missing_evidence: dict[str, list[str]]
    unexpected_evidence: dict[str, list[str]]
    duplicate_event_count: int = Field(ge=0)
    duplicate_finding_count: int = Field(ge=0)
    status: Literal["pass", "fail"]
    reason_codes: list[str]


class PerRuleDiagnostic(EvaluationModel):
    rule_id: str
    counts: ConfusionCounts
    metrics: Metrics


class EvaluationReport(EvaluationModel):
    schema_version: Literal["1.0"]
    report_type: Literal["aegisai_synthetic_detection_evaluation_report"]
    dataset_id: str
    dataset_version: str
    dataset_sha256: str
    detector_config_sha256: str
    data_classification: Literal["synthetic"]
    label: Literal["SYNTHETIC EVALUATION - NOT REAL SECURITY PERFORMANCE"]
    counting_unit: str
    counts: ConfusionCounts
    metrics: Metrics
    per_rule: list[PerRuleDiagnostic]
    valid_scenario_count: int = Field(ge=0)
    rejected_scenario_count: int = Field(ge=0)
    evidence_summary: dict[str, int]
    scenarios: list[ScenarioDiagnostic]
    rejected_inputs: list[ScenarioDiagnostic]
    limitations: list[str] = Field(min_length=1)


class EvaluationExecutionError(ValueError):
    """Safe failure raised when a complete deterministic evaluation cannot be produced."""


def _metric(numerator: int, denominator: int) -> MetricValue:
    if denominator == 0:
        return MetricValue(value=None, denominator=0, status="undefined_zero_denominator")
    return MetricValue(value=numerator / denominator, denominator=denominator, status="defined")


def _metrics(counts: ConfusionCounts) -> Metrics:
    tp, fp = counts.true_positives, counts.false_positives
    tn, fn = counts.true_negatives, counts.false_negatives
    f1_denominator = 2 * tp + fp + fn
    return Metrics(
        precision=_metric(tp, tp + fp),
        recall=_metric(tp, tp + fn),
        f1=_metric(2 * tp, f1_denominator),
        false_positive_rate=_metric(fp, fp + tn),
        false_negative_rate=_metric(fn, fn + tp),
    )


def detector_config_fingerprint() -> str:
    """Fingerprint rule IDs/version and the concrete threshold constants used by rules."""
    config = {
        "rule_ids": sorted(SUPPORTED_RULE_IDS),
        "telemetry_rule_version": telemetry.RULE_VERSION,
        "request_rate_threshold": telemetry.REQUEST_RATE_THRESHOLD,
        "request_rate_window_seconds": telemetry.REQUEST_RATE_WINDOW_SECONDS,
        "authentication_failure_window_seconds": int(telemetry.DETECTION_WINDOW.total_seconds()),
        "auth_correlation_failure_window_seconds": int(prototype_pipeline.AUTH_FAILURE_WINDOW.total_seconds()),
        "auth_success_after_failure_window_seconds": int(prototype_pipeline.SUCCESS_AFTER_FAILURE_WINDOW.total_seconds()),
        "rule_event_mapping": {rule: sorted(values) for rule, values in sorted(RULE_EVENT_TYPES.items())},
    }
    canonical = json.dumps(config, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _scenario_tenant(scenario_id: str) -> str:
    # A deterministic isolated namespace; no tenant is accepted from dataset content.
    suffix = hashlib.sha256(scenario_id.encode("utf-8")).hexdigest()[:20]
    return f"synthetic-org-eval-{suffix}"


def _unique_findings(findings: list[TelemetryFinding]) -> tuple[dict[str, TelemetryFinding], int]:
    by_rule: dict[str, TelemetryFinding] = {}
    duplicate_count = 0
    for finding in findings:
        if not isinstance(finding, TelemetryFinding):
            raise EvaluationExecutionError("detector returned an invalid finding; evaluation incomplete")
        if finding.rule_id in by_rule:
            duplicate_count += 1
            prior = by_rule[finding.rule_id]
            evidence = list(dict.fromkeys([*prior.evidence_refs, *finding.evidence_refs]))
            by_rule[finding.rule_id] = prior.model_copy(update={"evidence_refs": evidence})
        else:
            by_rule[finding.rule_id] = finding
    return by_rule, duplicate_count


def evaluate_dataset(
    dataset: EvaluationDataset,
    *,
    detector: Callable[..., list[TelemetryFinding]] = detect_findings,
) -> EvaluationReport:
    """Evaluate accepted scenarios independently; rejected scenarios never affect metrics."""
    try:
        dataset = EvaluationDataset.model_validate(dataset.model_dump(mode="python"))
    except (AttributeError, TypeError, ValueError, ValidationError):
        raise EvaluationExecutionError("evaluation dataset validation failed; no report produced") from None
    rules = sorted(SUPPORTED_RULE_IDS)
    matrix = {rule: [0, 0, 0, 0] for rule in rules}  # TP, FP, TN, FN
    diagnostics: list[ScenarioDiagnostic] = []
    rejected: list[ScenarioDiagnostic] = []
    evidence_totals = {"expected_references": 0, "present_references": 0,
                       "missing_references": 0, "unexpected_references": 0}

    for scenario in dataset.scenarios:
        ground_truth = scenario.ground_truth
        expected = set(ground_truth.expected_finding_types)
        required = {item.rule_id: set(item.evidence_refs) for item in ground_truth.required_evidence}
        if ground_truth.expected_input_outcome == "reject":
            observed_rejection = _input_rejection_category(scenario.detector_input)
            reason = (["INPUT_REJECTED_AS_EXPECTED"]
                      if observed_rejection == ground_truth.expected_rejection_category
                      else ["REJECTION_CATEGORY_MISMATCH"])
            rejected.append(ScenarioDiagnostic(
                scenario_id=scenario.scenario_id, category=scenario.category,
                input_validity="rejected", expected_rejection_category=ground_truth.expected_rejection_category,
                observed_rejection_category=observed_rejection,
                expected_finding_types=[], actual_finding_types=[], missing_expected_types=[], unexpected_types=[],
                required_evidence={}, observed_evidence_by_type={}, missing_evidence={}, unexpected_evidence={},
                duplicate_event_count=0, duplicate_finding_count=0,
                status="pass" if observed_rejection == ground_truth.expected_rejection_category else "fail",
                reason_codes=reason,
            ))
            continue

        events = validate_detector_input(scenario)
        duplicate_event_count = len(scenario.detector_input) - len(events)
        try:
            raw_findings = detector(events, tenant_id=_scenario_tenant(scenario.scenario_id))
            if not isinstance(raw_findings, list):
                raise EvaluationExecutionError("detector returned an invalid result; evaluation incomplete")
            findings, duplicate_finding_count = _unique_findings(raw_findings)
        except Exception as exc:
            if isinstance(exc, EvaluationExecutionError):
                raise
            raise EvaluationExecutionError("scenario detection failed; evaluation incomplete") from None
        actual = set(findings)
        missing_types = sorted(expected - actual)
        unexpected_types = sorted(actual - expected)
        input_evidence = {event.evidence_ref for event in events}
        observed_evidence = {rule: set(finding.evidence_refs) for rule, finding in findings.items()}
        missing_evidence: dict[str, list[str]] = {}
        unexpected_evidence: dict[str, list[str]] = {}
        for rule, refs in required.items():
            evidence_totals["expected_references"] += len(refs)
            present = refs & observed_evidence.get(rule, set())
            evidence_totals["present_references"] += len(present)
            missing = refs - present
            if missing:
                missing_evidence[rule] = sorted(missing)
                evidence_totals["missing_references"] += len(missing)
        for rule, refs in observed_evidence.items():
            unsupported = refs - input_evidence
            if unsupported:
                unexpected_evidence[rule] = sorted(unsupported)
                evidence_totals["unexpected_references"] += len(unsupported)
        for rule in rules:
            expected_match, actual_match = rule in expected, rule in actual
            slot = 0 if expected_match and actual_match else 1 if actual_match else 3 if expected_match else 2
            matrix[rule][slot] += 1
        reasons = []
        if missing_types:
            reasons.append("MISSING_EXPECTED_FINDING_TYPE")
        if unexpected_types:
            reasons.append("UNEXPECTED_FINDING_TYPE")
        if missing_evidence:
            reasons.append("MISSING_REQUIRED_EVIDENCE")
        if unexpected_evidence:
            reasons.append("EVIDENCE_NOT_IN_INPUT")
        diagnostics.append(ScenarioDiagnostic(
            scenario_id=scenario.scenario_id, category=scenario.category, input_validity="accepted",
            expected_rejection_category=None, observed_rejection_category=None,
            expected_finding_types=sorted(expected), actual_finding_types=sorted(actual),
            missing_expected_types=missing_types, unexpected_types=unexpected_types,
            required_evidence={key: sorted(value) for key, value in sorted(required.items())},
            observed_evidence_by_type={key: sorted(value) for key, value in sorted(observed_evidence.items())},
            missing_evidence=missing_evidence, unexpected_evidence=unexpected_evidence,
            duplicate_event_count=duplicate_event_count, duplicate_finding_count=duplicate_finding_count,
            status="pass" if not reasons else "fail", reason_codes=reasons,
        ))

    if len(diagnostics) + len(rejected) != len(dataset.scenarios):
        raise EvaluationExecutionError("evaluation did not process every scenario; results are incomplete")

    aggregate = ConfusionCounts(**{
        name: sum(values[index] for values in matrix.values())
        for index, name in enumerate(("true_positives", "false_positives", "true_negatives", "false_negatives"))
    })
    per_rule = [PerRuleDiagnostic(
        rule_id=rule,
        counts=ConfusionCounts(**dict(zip(
            ("true_positives", "false_positives", "true_negatives", "false_negatives"), matrix[rule]
        ))),
        metrics=_metrics(ConfusionCounts(**dict(zip(
            ("true_positives", "false_positives", "true_negatives", "false_negatives"), matrix[rule]
        )))),
    ) for rule in rules]
    return EvaluationReport(
        schema_version=EVALUATION_SCHEMA_VERSION,
        report_type="aegisai_synthetic_detection_evaluation_report",
        dataset_id=dataset.dataset_id, dataset_version=dataset.dataset_version,
        dataset_sha256=dataset_fingerprint(dataset), detector_config_sha256=detector_config_fingerprint(),
        data_classification="synthetic",
        label="SYNTHETIC EVALUATION - NOT REAL SECURITY PERFORMANCE",
        counting_unit=COUNTING_UNIT, counts=aggregate, metrics=_metrics(aggregate), per_rule=per_rule,
        valid_scenario_count=len(diagnostics), rejected_scenario_count=len(rejected),
        evidence_summary=evidence_totals, scenarios=diagnostics, rejected_inputs=rejected,
        limitations=[
            "All inputs are authored synthetic examples; results do not establish real-world detection accuracy.",
            "Scenario-by-rule pairs are the counting unit; wrong rule types create a false positive and a false negative.",
            "Rejected inputs are validated separately and are excluded from all confusion-matrix denominators.",
            "The small hand-authored dataset is not a representative statistical sample and must not guide automatic rule tuning.",
        ],
    )


def report_json(report: EvaluationReport) -> str:
    output = json.dumps(report.model_dump(mode="json"), ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if len(output.encode("utf-8")) > MAX_REPORT_BYTES:
        raise ValueError("evaluation report exceeds the 1 MiB output limit")
    return output
