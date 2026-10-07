"""Evidence-grounded failure analysis for the adaptive-memory phase."""
from __future__ import annotations

from dataclasses import dataclass

from xai.trace import DecisionTrace
from memory.knowledge_patch import KnowledgePatch


@dataclass(frozen=True)
class FailureAnalyzer:
    """Creates candidate lessons only from observable XAI traces.

    It never reads simulator internals and never promotes a lesson to validated memory.
    """

    def analyze(self, traces: tuple[DecisionTrace, ...]) -> tuple[KnowledgePatch, ...]:
        by_step: dict[int, list[DecisionTrace]] = {}
        for trace in traces:
            by_step.setdefault(trace.step, []).append(trace)

        candidates: list[KnowledgePatch] = []
        for step, rows in sorted(by_step.items()):
            red = next((t for t in rows if t.role.value == "red"), None)
            blue = next((t for t in rows if t.role.value == "blue"), None)
            if red is None or blue is None or not red.success:
                continue
            # A successful Red step paired with a failed/ineffective Blue response is a
            # concrete defensive failure signal. This is intentionally conservative.
            if blue.success and blue.state_change_count > 0:
                continue

            patch_id = f"lesson-{red.episode_id}-{step}"
            lesson = (
                f"A Red action {red.action['action_type']} succeeded at step {step} "
                f"while the paired Blue response had no successful state change."
            )
            recommendation = (
                f"For future defender decisions, explicitly inspect evidence associated with "
                f"{red.action['action_type']} before selecting a response."
            )
            candidates.append(KnowledgePatch.candidate(
                patch_id=patch_id,
                version=1,
                role="blue",
                lesson=lesson,
                recommendation=recommendation,
                trace_ids=(red.trace_id, blue.trace_id),
                episode_ids=(red.episode_id,),
                scenario_ids=(red.scenario_id,),
                steps=(step,),
                outcomes=(red.actual_outcome or "unknown", blue.actual_outcome or "unknown"),
            ))
        return tuple(candidates)
