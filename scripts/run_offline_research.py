from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path
from time import monotonic

# Make C:\AegisAI importable when this script is launched directly.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pydantic import BaseModel

from agents.blue.llm import LLMBlueAgent
from agents.blue.scripted import ScriptedBlueAgent
from agents.red.llm import LLMRedAgent
from agents.red.scripted import ScriptedRedAgent
from evaluation.experiments.protocol import build_default_split
from evaluation.experiments.research import run_three_configurations
from llm.provider import BaseProviderAdapter, LLMRequest, LLMResponse
from telemetry.observation_builder import BlueObservation, RedObservation


class ObservationPolicyProvider(BaseProviderAdapter):
    """
    Deterministic offline test double.

    It emulates structured LLM output by using the existing
    scripted Red/Blue policies.

    IMPORTANT:
    This is for validating the experiment harness and reproducibility.
    It is NOT a real LLM and its results are NOT scientific evidence
    about real LLM performance.
    """

    def __init__(self, role: str):
        super().__init__(
            model="offline-policy-test",
            provider_name="test-double",
        )

        if role not in {"red", "blue"}:
            raise ValueError(f"Unsupported role: {role}")

        self.role = role
        self.policy = (
            ScriptedRedAgent()
            if role == "red"
            else ScriptedBlueAgent()
        )
        self.last_request: LLMRequest | None = None

    def generate_structured(
        self,
        request: LLMRequest,
        response_model: type[BaseModel],
    ) -> LLMResponse:
        self.last_request = request

        if self.role == "red":
            raw = request.user_content.split(
                "BEGIN RED OBSERVATION\n",
                1,
            )[1].split(
                "\nEND RED OBSERVATION",
                1,
            )[0]

            observation = RedObservation.model_validate(
                json.loads(raw)
            )

            action = self.policy.decide(observation)

        else:
            raw = request.user_content.split(
                "BEGIN BLUE OBSERVATION\n",
                1,
            )[1].split(
                "\nEND BLUE OBSERVATION",
                1,
            )[0]

            observation = BlueObservation.model_validate(
                json.loads(raw)
            )

            action = self.policy.decide(observation)

        return self._wrap(
            action,
            response_model,
            monotonic(),
        )


def main() -> None:
    results_dir = ROOT / "results"
    results_dir.mkdir(exist_ok=True)

    # Two scenario templates × four seeds = 8 scenario/seed pairs.
    #
    # This gives us:
    #   Train      = 4
    #   Validation = 2
    #   Test       = 2
    #
    # The test set is therefore larger than the previous 1-case split.
    template_ids = (
        "web_exploit_lateral_exfil",
        "credential_reuse_known_vuln",
    )

    seeds = (1, 2, 7, 9)

    split = build_default_split(
        template_ids,
        seeds,
    )

    print("=" * 70)
    print("AEGISAI OFFLINE RESEARCH EXPERIMENT")
    print("=" * 70)
    print("Provider: deterministic scripted test double; no model API calls.")
    print("This run validates the harness, not real LLM performance.")

    print("\nScenario split")
    print("-" * 70)
    print(f"Train      : {split.train}")
    print(f"Validation : {split.validation}")
    print(f"Test       : {split.test}")

    print("\nRunning A / B / C...")
    print("-" * 70)
    print("A = Scripted Red + Scripted Blue")
    print("B = LLM Red + LLM Blue without adaptive memory")
    print("C = LLM Red + LLM Blue with adaptive memory")
    print()

    result = run_three_configurations(
        experiment_id="offline_research_001",
        split=split,

        # Configuration A
        scripted_red_factory=ScriptedRedAgent,
        scripted_blue_factory=ScriptedBlueAgent,

        # Configuration B
        llm_red_factory=lambda: LLMRedAgent(
            ObservationPolicyProvider("red")
        ),
        llm_blue_no_memory_factory=lambda: LLMBlueAgent(
            ObservationPolicyProvider("blue")
        ),

        # Configuration C
        llm_blue_adaptive_factory=lambda: LLMBlueAgent(
            ObservationPolicyProvider("blue"),
            memory_context=(
                "Validated offline test-double lesson: "
                "inspect available evidence before selecting "
                "the defensive action."
            ),
        ),

        model_provider="test-double",
        model_name="offline-policy-test",
        temperature=0.0,
        seed=123,

        # Memory may only come from train/validation.
        # Held-out test scenarios are explicitly excluded.
        memory_source_pairs=split.train + split.validation,
    )

    output = {
        "experiment_id": result.baseline.experiment_id,

        "split": {
            "train": list(split.train),
            "validation": list(split.validation),
            "test": list(split.test),
        },

        "baseline": asdict(result.baseline),

        "no_memory": asdict(result.no_memory),

        "adaptive_memory": asdict(result.adaptive),

        "adaptation_improvement": result.adaptation_improvement,

        "generalization_improvement": result.generalization_improvement,

        "manifest_fingerprints": list(
            result.manifest_fingerprints
        ),

        "important_note": (
            "This experiment uses a deterministic offline "
            "test-double provider. It validates the A/B/C "
            "experiment harness, reproducibility, scenario "
            "splitting, and memory isolation. It is NOT evidence "
            "of real LLM performance."
        ),
    }

    output_path = results_dir / "offline_research_result.json"

    output_path.write_text(
        json.dumps(
            output,
            indent=2,
        ),
        encoding="utf-8",
    )

    print("\n" + "=" * 70)
    print("EXPERIMENT COMPLETE")
    print("=" * 70)

    print("\nA - Scripted baseline")
    print(result.baseline.aggregate)

    print("\nB - LLM interface without adaptive memory (offline test double)")
    print(result.no_memory.aggregate)

    print("\nC - LLM interface with adaptive memory (offline test double)")
    print(result.adaptive.aggregate)

    print("\nAdaptation improvement (C - B)")
    print(result.adaptation_improvement)

    print("\nGeneralization improvement")
    print(result.generalization_improvement)

    print("\nResults saved to:")
    print(output_path)

    print("\n" + "=" * 70)


if __name__ == "__main__":
    main()
