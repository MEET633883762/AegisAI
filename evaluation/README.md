# Evaluation and reproducible experiments

Simulator metrics come from Controller-owned telemetry and audit evidence, not values supplied by agents. [`metrics/core.py`](metrics/core.py) calculates per-episode outcomes and aggregates them across fresh agent instances and explicit scenario/seed pairs.

## Keep the measurements distinct

The simulator metrics include attack-success rate, detection rate, mean detection time, mitigation-success rate, false-positive rate, and decision latency. An investigated alert and a successful containment response are different events; inspect the metric definitions and denominators before comparing runs. Some timing values are observational rather than deterministic replay facts.

The separate local synthetic detection evaluator measures scenario-by-rule confusion counts against labeled fixtures. Those counts are not the simulator's alert-investigation metrics. Its [method and limits](../docs/DETECTION_ENGINEERING_AND_EVALUATION.md) describe how rejected inputs, rule coverage, and nullable metrics are handled.

## Run a comparison

Prepare the Python 3.11 environment using [DEVELOPMENT.md](../docs/DEVELOPMENT.md). From the repository root on Windows, with dependencies installed:

```powershell
py -3.11 scripts/run_defender_benchmark.py
```

The benchmark runs the baseline and evidence-prioritized scripted defenders on 30 matched scenario pairs and writes a new report under `.aegisai-local/benchmarks/`. Its reviewed [result and method](../docs/DEFENDER_COMPARISON.md) include unchanged pairs and the availability cost of isolation. It does not measure an AI model.

The [A/B/C experiment protocol](experiments/README.md) and [report serializer](reports/README.md) support separate research work. The public browser walkthrough replays reviewed synthetic output rather than running experiments. See [current status](../docs/CURRENT_STATUS.md) for fresh checks; older phase test counts remain historical records.
