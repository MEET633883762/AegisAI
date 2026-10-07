# Adaptive Memory — Phase 10

Phase 10 implements evidence-grounded, versioned knowledge patches.

Flow:

`Attack → Evidence → Failure Detection → Lesson → Candidate Patch → Validation → Version → Retest/Measure → Validated Memory`

The MVP does **not** retrain model weights. Candidate lessons are derived only from role-visible XAI traces. A patch is never accepted merely because an LLM generated it. Validation requires an explicit held-out experiment and a measurable improvement threshold. Validated memory is rendered as bounded, non-executable context for a future agent integration.

Threat model controls:
- evidence trace IDs are mandatory;
- candidate, validated, rejected and revoked states are explicit;
- version history is append-only at the repository level;
- unvalidated patches cannot become agent context;
- memory never executes simulator actions or controller policy;
- revocation preserves prior versions.
