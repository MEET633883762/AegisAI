"""Versioned synthetic benchmark cases kept separate from detector inputs."""

from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationError, model_validator

from private_api.telemetry import (
    SyntheticTelemetryBatch,
    SyntheticTelemetryEvent,
    TelemetryConflictError,
    normalize_and_deduplicate,
)
from platform_prototype.replay import SUPPORTED_RULE_IDS

MAX_EVALUATION_DATASET_BYTES = 1_048_576
MAX_EVALUATION_SCENARIOS = 50
MAX_EVENTS_PER_SCENARIO = 50
MAX_EVENTS_PER_DATASET = 500
_SUPPORTED_RULES = frozenset(SUPPORTED_RULE_IDS)


class EvaluationDatasetModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class RequiredEvidence(EvaluationDatasetModel):
    rule_id: str
    evidence_refs: list[str] = Field(min_length=1, max_length=MAX_EVENTS_PER_SCENARIO)

    @model_validator(mode="after")
    def references_are_unique(self) -> RequiredEvidence:
        if len(set(self.evidence_refs)) != len(self.evidence_refs):
            raise ValueError("required evidence references must be unique")
        return self


class EvaluationGroundTruth(EvaluationDatasetModel):
    expected_input_outcome: Literal["accept", "reject"]
    expected_rejection_category: Literal[
        "schema_validation", "event_id_conflict", "evidence_ref_conflict",
    ] | None = None
    expected_finding_types: list[str] = Field(max_length=len(_SUPPORTED_RULES))
    expected_no_finding_types: list[str] = Field(max_length=len(_SUPPORTED_RULES))
    required_evidence: list[RequiredEvidence] = Field(max_length=len(_SUPPORTED_RULES))

    @model_validator(mode="after")
    def labels_are_complete_and_unambiguous(self) -> EvaluationGroundTruth:
        positive = self.expected_finding_types
        negative = self.expected_no_finding_types
        if len(set(positive)) != len(positive) or len(set(negative)) != len(negative):
            raise ValueError("ground-truth rule labels must be unique")
        if not set(positive).issubset(_SUPPORTED_RULES) or not set(negative).issubset(_SUPPORTED_RULES):
            raise ValueError("ground truth contains an unsupported finding type")
        if set(positive) & set(negative) or set(positive) | set(negative) != _SUPPORTED_RULES:
            raise ValueError("ground truth must explicitly partition supported finding types")
        evidence_rules = [item.rule_id for item in self.required_evidence]
        if len(set(evidence_rules)) != len(evidence_rules):
            raise ValueError("ground-truth evidence rules must be unique")
        if not set(evidence_rules).issubset(positive):
            raise ValueError("required evidence must belong to an expected finding")
        if self.expected_input_outcome == "accept" and self.expected_rejection_category is not None:
            raise ValueError("accepted input cannot declare a rejection category")
        if self.expected_input_outcome == "reject":
            if self.expected_rejection_category is None or positive or self.required_evidence:
                raise ValueError("rejected input requires a rejection category and no expected findings")
        return self


class EvaluationScenario(EvaluationDatasetModel):
    scenario_id: str = Field(min_length=1, max_length=48, pattern=r"^p6a-[a-z0-9-]+$")
    category: Literal[
        "suspicious_positive", "benign_control", "threshold_boundary", "exact_duplicate",
        "malformed_input", "identifier_conflict", "insufficient_evidence", "multi_finding",
    ]
    difficulty: Literal["introductory", "intermediate", "edge"]
    description: str = Field(min_length=1, max_length=240)
    detector_input: list[JsonValue] = Field(min_length=1, max_length=MAX_EVENTS_PER_SCENARIO)
    ground_truth: EvaluationGroundTruth

    @model_validator(mode="after")
    def evidence_refs_are_present(self) -> EvaluationScenario:
        refs = {
            item.get("evidence_ref") for item in self.detector_input
            if isinstance(item, dict) and isinstance(item.get("evidence_ref"), str)
        }
        for requirement in self.ground_truth.required_evidence:
            if not set(requirement.evidence_refs).issubset(refs):
                raise ValueError("ground-truth evidence must refer to detector input records")
        return self


class EvaluationDataset(EvaluationDatasetModel):
    schema_version: Literal["1.0"]
    dataset_id: Literal["aegisai_synthetic_detection_evaluation"]
    dataset_version: Literal["1.0"]
    data_classification: Literal["synthetic"]
    label: Literal["SYNTHETIC EVALUATION DATA - NOT REAL SECURITY EVENTS"]
    scenarios: list[EvaluationScenario] = Field(min_length=1, max_length=MAX_EVALUATION_SCENARIOS)

    @model_validator(mode="after")
    def validate_order_ids_and_inputs(self) -> EvaluationDataset:
        scenario_ids = [scenario.scenario_id for scenario in self.scenarios]
        if len(set(scenario_ids)) != len(scenario_ids):
            raise ValueError("scenario IDs must be unique")
        event_total = sum(len(scenario.detector_input) for scenario in self.scenarios)
        if event_total > MAX_EVENTS_PER_DATASET:
            raise ValueError("evaluation dataset exceeds the total record limit")
        event_owners: dict[str, str] = {}
        evidence_owners: dict[str, str] = {}
        for scenario in self.scenarios:
            for record in scenario.detector_input:
                if not isinstance(record, dict):
                    continue
                event_id = record.get("event_id")
                evidence_ref = record.get("evidence_ref")
                if isinstance(event_id, str):
                    prior = event_owners.setdefault(event_id, scenario.scenario_id)
                    if prior != scenario.scenario_id:
                        raise ValueError("event IDs must be unique across scenarios")
                if isinstance(evidence_ref, str):
                    prior = evidence_owners.setdefault(evidence_ref, scenario.scenario_id)
                    if prior != scenario.scenario_id:
                        raise ValueError("evidence references must be unique across scenarios")
            actual_rejection = _input_rejection_category(scenario.detector_input)
            expected = scenario.ground_truth
            if expected.expected_input_outcome == "accept" and actual_rejection is not None:
                raise ValueError("scenario labeled for acceptance does not pass event validation")
            if expected.expected_input_outcome == "reject" and actual_rejection != expected.expected_rejection_category:
                raise ValueError("scenario rejection label does not match its validation failure category")
        return self


class EvaluationDatasetError(ValueError):
    """Safe validation error for a Phase 6A benchmark dataset."""


def _input_rejection_category(records: list[JsonValue]) -> str | None:
    try:
        events = [SyntheticTelemetryEvent.model_validate(record) for record in records]
    except (ValidationError, TypeError, ValueError):
        return "schema_validation"
    batch = SyntheticTelemetryBatch(
        schema_version="1.0", source_id="local_synthetic_fixture_v1",
        data_classification="synthetic", label="SYNTHETIC - NOT REAL CLIENT DATA",
        generated_at=max(event.occurred_at for event in events), events=events,
    )
    try:
        normalize_and_deduplicate(batch)
    except TelemetryConflictError as exc:
        if "evidence reference" in str(exc):
            return "evidence_ref_conflict"
        return "event_id_conflict"
    return None


def validate_detector_input(scenario: EvaluationScenario) -> list[SyntheticTelemetryEvent]:
    """Return only normalized event records; ground-truth metadata is never forwarded."""
    if scenario.ground_truth.expected_input_outcome != "accept":
        raise EvaluationDatasetError("scenario input is labeled for safe rejection")
    try:
        batch = SyntheticTelemetryBatch(
            schema_version="1.0", source_id="local_synthetic_fixture_v1",
            data_classification="synthetic", label="SYNTHETIC - NOT REAL CLIENT DATA",
            generated_at=max(
                SyntheticTelemetryEvent.model_validate(record).occurred_at
                for record in scenario.detector_input
            ),
            events=[SyntheticTelemetryEvent.model_validate(record) for record in scenario.detector_input],
        )
        normalized, _duplicate_count = normalize_and_deduplicate(batch)
    except (ValidationError, TypeError, ValueError) as exc:
        raise EvaluationDatasetError("scenario input failed validation") from None
    return normalized


def load_evaluation_dataset_bytes(raw: bytes) -> EvaluationDataset:
    if len(raw) > MAX_EVALUATION_DATASET_BYTES:
        raise EvaluationDatasetError("evaluation dataset exceeds the 1 MiB size limit")
    try:
        return EvaluationDataset.model_validate_json(raw)
    except (ValidationError, ValueError, RecursionError):
        raise EvaluationDatasetError("evaluation dataset validation failed") from None


def dataset_fingerprint(dataset: EvaluationDataset) -> str:
    """Hash canonical JSON: object key order/whitespace do not affect the fingerprint."""
    payload = dataset.model_dump(mode="json")
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
