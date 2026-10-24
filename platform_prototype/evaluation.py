"""Deterministic, isolated metrics for the fixed Phase 6A synthetic dataset."""

from __future__ import annotations

import copy
import hashlib
import json
from typing import Callable, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

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

EVALUATION_SCHEMA_VERSION = "1.1"
EVALUATION_RULE_CATALOG_VERSION = "1.0"
SCENARIO_RULE_MAPPING_VERSION = "1.0"
ATTACK_MAPPING_CATALOG_VERSION = "1.0"
MAX_REPORT_BYTES = 1_048_576
COUNTING_UNIT = "one accepted scenario-by-supported-rule pair"
SMALL_SAMPLE_SCENARIO_LIMIT = 30


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
    specificity: MetricValue
    false_positive_rate: MetricValue
    false_negative_rate: MetricValue


class RuleEventMapping(EvaluationModel):
    rule_id: str
    event_types: list[str]


class ScenarioRuleMapping(EvaluationModel):
    scenario_id: str
    expected_rule_ids: list[str]
    evaluated_rule_ids: list[str]
    observed_rule_ids: list[str]
    technique_ids: list[str]
    status: Literal["pass", "fail", "rejected"]


class TechniqueCoverage(EvaluationModel):
    technique_id: str
    name: str
    scenario_ids: list[str]
    rule_ids: list[str]
    status: Literal["covered"]
    scope_note: str


class UntestedTechnique(EvaluationModel):
    technique_id: str
    name: str
    status: Literal["not_tested", "candidate_not_mapped"]
    rationale: str


class ScenarioDiagnostic(EvaluationModel):
    scenario_id: str
    category: str
    technique_ids: list[str] = Field(default_factory=list)
    evaluated_rule_ids: list[str] = Field(default_factory=list)
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
    schema_version: Literal["1.0", "1.1"]
    report_type: Literal["aegisai_synthetic_detection_evaluation_report"]
    dataset_id: str
    dataset_version: str
    dataset_sha256: str
    detector_config_sha256: str
    rule_catalog_version: str = "unavailable"
    detector_rule_version: str = "unavailable"
    scenario_rule_mapping_version: str = "unavailable"
    attack_mapping_catalog_version: str = "unavailable"
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
    rule_event_mapping: list[RuleEventMapping] = Field(default_factory=list)
    scenario_rule_mapping: list[ScenarioRuleMapping] = Field(default_factory=list)
    technique_coverage: list[TechniqueCoverage] = Field(default_factory=list)
    untested_techniques: list[UntestedTechnique] = Field(default_factory=list)
    coverage_status: Literal["complete", "partial", "legacy_unavailable"] = "legacy_unavailable"
    warnings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(min_length=1)

    @model_validator(mode="before")
    @classmethod
    def backfill_specificity_for_legacy_reports(cls, value):
        """Derive specificity when reading saved 1.0 reports created before the field existed."""
        if not isinstance(value, dict):
            return value
        result = copy.deepcopy(value)

        def add(metrics_value, counts_value):
            if isinstance(metrics_value, dict) and "specificity" not in metrics_value and isinstance(counts_value, dict):
                tp = counts_value.get("true_positives", 0)
                fp = counts_value.get("false_positives", 0)
                tn = counts_value.get("true_negatives", 0)
                if all(isinstance(item, int) and not isinstance(item, bool) and item >= 0 for item in (tp, fp, tn)):
                    denominator = tn + fp
                    metrics_value["specificity"] = _metric(tn, denominator).model_dump()

        add(result.get("metrics"), result.get("counts"))
        if isinstance(result.get("per_rule"), list):
            for row in result["per_rule"]:
                if isinstance(row, dict):
                    add(row.get("metrics"), row.get("counts"))
        return result


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
        specificity=_metric(tn, tn + fp),
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
    scenario_mappings: list[ScenarioRuleMapping] = []
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
                technique_ids=[], evaluated_rule_ids=[],
                input_validity="rejected", expected_rejection_category=ground_truth.expected_rejection_category,
                observed_rejection_category=observed_rejection,
                expected_finding_types=[], actual_finding_types=[], missing_expected_types=[], unexpected_types=[],
                required_evidence={}, observed_evidence_by_type={}, missing_evidence={}, unexpected_evidence={},
                duplicate_event_count=0, duplicate_finding_count=0,
                status="pass" if observed_rejection == ground_truth.expected_rejection_category else "fail",
                reason_codes=reason,
            ))
            scenario_mappings.append(ScenarioRuleMapping(
                scenario_id=scenario.scenario_id, expected_rule_ids=[], evaluated_rule_ids=[],
                observed_rule_ids=[], technique_ids=[], status="rejected",
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
            technique_ids=[], evaluated_rule_ids=rules,
            expected_rejection_category=None, observed_rejection_category=None,
            expected_finding_types=sorted(expected), actual_finding_types=sorted(actual),
            missing_expected_types=missing_types, unexpected_types=unexpected_types,
            required_evidence={key: sorted(value) for key, value in sorted(required.items())},
            observed_evidence_by_type={key: sorted(value) for key, value in sorted(observed_evidence.items())},
            missing_evidence=missing_evidence, unexpected_evidence=unexpected_evidence,
            duplicate_event_count=duplicate_event_count, duplicate_finding_count=duplicate_finding_count,
            status="pass" if not reasons else "fail", reason_codes=reasons,
        ))
        scenario_mappings.append(ScenarioRuleMapping(
            scenario_id=scenario.scenario_id, expected_rule_ids=sorted(expected),
            evaluated_rule_ids=rules, observed_rule_ids=sorted(actual), technique_ids=[],
            status="pass" if not reasons else "fail",
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
        rule_catalog_version=EVALUATION_RULE_CATALOG_VERSION,
        detector_rule_version=telemetry.RULE_VERSION,
        scenario_rule_mapping_version=SCENARIO_RULE_MAPPING_VERSION,
        attack_mapping_catalog_version=ATTACK_MAPPING_CATALOG_VERSION,
        data_classification="synthetic",
        label="SYNTHETIC EVALUATION - NOT REAL SECURITY PERFORMANCE",
        counting_unit=f"{COUNTING_UNIT}; {len(rules)} evaluated rule pairs per accepted scenario",
        counts=aggregate, metrics=_metrics(aggregate), per_rule=per_rule,
        valid_scenario_count=len(diagnostics), rejected_scenario_count=len(rejected),
        evidence_summary=evidence_totals, scenarios=diagnostics, rejected_inputs=rejected,
        rule_event_mapping=[RuleEventMapping(rule_id=rule, event_types=sorted(RULE_EVENT_TYPES[rule]))
                            for rule in rules],
        scenario_rule_mapping=scenario_mappings,
        technique_coverage=[],
        untested_techniques=[UntestedTechnique(
            technique_id="T1110", name="Brute Force", status="candidate_not_mapped",
            rationale=("The synthetic authentication cases contain auth_failure events only. They do not establish "
                       "systematic password guessing, credential use, or hash cracking, so this dataset does not "
                       "claim coverage of ATT&CK T1110."),
        )],
        coverage_status="partial",
        warnings=(
            ([f"Small synthetic sample: {len(diagnostics)} accepted scenarios; results are descriptive only."]
             if len(diagnostics) < SMALL_SAMPLE_SCENARIO_LIMIT else [])
            + ["All inputs are synthetic; these results are not real-world detection performance.",
               "No ATT&CK technique is directly mapped; T1110 remains an explicitly untested candidate."]
        ),
        limitations=[
            "All inputs are authored synthetic examples; results do not establish real-world detection accuracy.",
            "Scenario-by-rule pairs are the counting unit; wrong rule types create a false positive and a false negative.",
            "Rejected inputs are validated separately and are excluded from all confusion-matrix denominators.",
            "The small hand-authored dataset is not a representative statistical sample and must not guide automatic rule tuning.",
            "No scenario claims ATT&CK technique coverage; synthetic auth failures alone are not proof of brute-force activity.",
        ],
    )


def report_json(report: EvaluationReport) -> str:
    output = json.dumps(report.model_dump(mode="json"), ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if len(output.encode("utf-8")) > MAX_REPORT_BYTES:
        raise ValueError("evaluation report exceeds the 1 MiB output limit")
    return output
