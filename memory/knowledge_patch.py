"""Validated, versioned adaptive-memory records for AegisAI.

Memory is contextual knowledge, not executable policy and never directly changes model weights
or simulator state. A patch must cite observable evidence and is accepted only after an explicit
validation run demonstrates the requested improvement.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class PatchStatus(str, Enum):
    CANDIDATE = "candidate"
    VALIDATED = "validated"
    REJECTED = "rejected"
    REVOKED = "revoked"


class ValidationRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    validation_id: str
    baseline_metric: str
    baseline_value: float = Field(ge=0.0)
    candidate_value: float = Field(ge=0.0)
    improvement: float
    threshold: float = Field(ge=0.0)
    held_out: bool = False
    passed: bool
    notes: str = ""
    validated_at: str


class KnowledgePatch(BaseModel):
    """A non-executable lesson that may be supplied to a future agent context."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    patch_id: str
    version: int = Field(ge=1)
    status: PatchStatus = PatchStatus.CANDIDATE
    role: str
    lesson: str = Field(min_length=1, max_length=1000)
    recommendation: str = Field(min_length=1, max_length=1000)
    evidence_trace_ids: tuple[int, ...] = ()
    evidence_episode_ids: tuple[str, ...] = ()
    evidence_scenario_ids: tuple[str, ...] = ()
    evidence_steps: tuple[int, ...] = ()
    source_outcomes: tuple[str, ...] = ()
    created_at: str
    validation: ValidationRecord | None = None
    supersedes_patch_id: str | None = None

    @classmethod
    def candidate(
        cls,
        *,
        patch_id: str,
        version: int,
        role: str,
        lesson: str,
        recommendation: str,
        trace_ids: tuple[int, ...],
        episode_ids: tuple[str, ...],
        scenario_ids: tuple[str, ...],
        steps: tuple[int, ...],
        outcomes: tuple[str, ...],
    ) -> "KnowledgePatch":
        if not trace_ids:
            raise ValueError("candidate patch requires evidence trace ids")
        if not episode_ids or not scenario_ids or not steps:
            raise ValueError("candidate patch requires episode, scenario, and step evidence")
        return cls(
            patch_id=patch_id,
            version=version,
            role=role,
            lesson=lesson,
            recommendation=recommendation,
            evidence_trace_ids=trace_ids,
            evidence_episode_ids=episode_ids,
            evidence_scenario_ids=scenario_ids,
            evidence_steps=steps,
            source_outcomes=outcomes,
            created_at=datetime.now(timezone.utc).isoformat(),
        )

    def validate(self, record: ValidationRecord) -> "KnowledgePatch":
        if record.passed is not True:
            raise ValueError("a patch cannot be marked validated by a failed validation record")
        return self.model_copy(update={"status": PatchStatus.VALIDATED, "validation": record})

    def reject(self, record: ValidationRecord) -> "KnowledgePatch":
        if record.passed:
            raise ValueError("a passing validation record cannot reject a patch")
        return self.model_copy(update={"status": PatchStatus.REJECTED, "validation": record})

    def revoke(self) -> "KnowledgePatch":
        if self.status is not PatchStatus.VALIDATED:
            raise ValueError("only a validated patch can be revoked")
        return self.model_copy(update={"status": PatchStatus.REVOKED})

    def context_text(self) -> str:
        """Render bounded non-executable context for a future agent."""
        if self.status is not PatchStatus.VALIDATED:
            raise ValueError("only validated patches may be rendered as agent context")
        return f"Lesson: {self.lesson}\nRecommendation: {self.recommendation}"
