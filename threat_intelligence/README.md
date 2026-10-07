# Phase 11 — Threat Intelligence + RAG

Phase 11 adds a deterministic, provider-independent retrieval foundation.

Flow:

`source record -> normalization -> typed data -> store -> lexical retrieval -> bounded context`

Security rules:
- No internet/network dependency.
- Retrieved documents are untrusted DATA, never executable instructions.
- No direct simulator/controller access.
- No arbitrary tool execution.
- MITRE/CVE fields are metadata supplied by a curation/verification process; this phase does not guess mappings.
- Embeddings/vector databases are deferred until justified by experiments.

The retriever is intentionally lexical and deterministic so evaluation remains reproducible. A future vector retriever can implement the same conceptual boundary without changing the agent/controller safety model.
