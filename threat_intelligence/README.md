# Offline threat intelligence and retrieval

This subsystem provides deterministic, provider-independent retrieval over supplied records:

`source record → normalization → typed record → in-memory store → lexical retrieval → bounded context`

The current implementation has no live CTI download or network dependency. Retrieved documents are untrusted data, not instructions. They have no direct simulator/Controller access and cannot execute tools. MITRE/CVE fields hold supplied metadata; their presence does not independently verify a mapping. Embeddings and vector databases remain outside this implementation.

## Run the local example

Prepare the Python 3.11 environment from [DEVELOPMENT.md](../docs/DEVELOPMENT.md). From the repository root on Windows:

```powershell
py -3.11 -m threat_intelligence
py -3.11 -m pytest -q tests/unit/test_threat_intelligence.py tests/security/test_security_boundaries.py
```

The example creates one in-memory curated demonstration record and performs a lexical search. It does not fetch threat feeds or save a production knowledge base. On Linux, use `.venv/bin/python` after the documented environment setup. An unqualified Windows `python` may select an older interpreter despite `.python-version`.

The lexical retriever supports repeatable evaluation; a future retriever must preserve the same untrusted-data and authorization boundaries. These examples are separate from the browser's scripted replay. See [current verification](../docs/CURRENT_STATUS.md) and the [research protocol](../evaluation/experiments/README.md).
