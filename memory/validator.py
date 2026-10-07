"""Explicit validation gate for adaptive-memory candidates."""
from __future__ import annotations

from memory.knowledge_patch import KnowledgePatch, ValidationRecord


class MemoryValidator:
    """Validates a candidate using externally supplied experimental measurements.

    The validator never executes actions and never calls an LLM. A patch passes only when
    the measured improvement reaches the configured threshold; held-out validation is
    strongly preferred and recorded explicitly.
    """

    def __init__(self, *, minimum_improvement: float = 0.05) -> None:
        if minimum_improvement < 0:
            raise ValueError("minimum_improvement must be non-negative")
        self.minimum_improvement = minimum_improvement

    def evaluate(
        self,
        patch: KnowledgePatch,
        *,
        validation_id: str,
        metric: str,
        baseline_value: float,
        candidate_value: float,
        held_out: bool,
        notes: str = "",
    ) -> KnowledgePatch:
        if patch.status.value != "candidate":
            raise ValueError("only candidate patches can be validated")
        if not metric.strip():
            raise ValueError("metric must not be empty")
        if baseline_value < 0 or candidate_value < 0:
            raise ValueError("metric values must be non-negative")

        # This MVP assumes higher-is-better metrics. For metrics such as attack success
        # rate, callers should supply an appropriate transformed defensive score.
        improvement = candidate_value - baseline_value
        passed = held_out and improvement >= self.minimum_improvement
        record = ValidationRecord(
            validation_id=validation_id,
            baseline_metric=metric,
            baseline_value=baseline_value,
            candidate_value=candidate_value,
            improvement=improvement,
            threshold=self.minimum_improvement,
            held_out=held_out,
            passed=passed,
            notes=notes,
            validated_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        )
        return patch.validate(record) if passed else patch.reject(record)
