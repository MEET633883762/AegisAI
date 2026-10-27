# Research experiment reports

[`research_report.py`](research_report.py) converts an A/B/C `ComparisonResult` into deterministic JSON. It includes each configuration's aggregate metrics, the exported adaptation/generalization score differences, and the three manifest fingerprints.

The serializer does not run experiments, write a file, or persist to a database by itself. Its caller decides where to save the JSON. This research report contract is separate from the local operations API's SQLite-backed telemetry, findings, cases, and executive reports; a planned `evaluation_runs`/`evaluation_metrics` research database is not implemented by this module.

Use the Python 3.11 [development environment](../../docs/DEVELOPMENT.md) for this package. The [experiment protocol](../experiments/README.md) explains test-double versus real-provider evidence and the fixed output file written by the offline CLI. The [current status](../../docs/CURRENT_STATUS.md) records fresh project checks rather than treating historical phase totals as current.
