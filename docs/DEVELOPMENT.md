# Reproduce and verify AegisAI

Use Python **3.11** and Node **24.14.1** for the reviewed demo environment. `.python-version` and `.node-version` record those choices. The browser application also retains its documented wider Node compatibility; these files identify the version used for repeatable project checks.

## A fresh Windows setup

Run from the repository root in PowerShell:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-demo.txt
.\.venv\Scripts\python.exe -m pip check
npm.cmd --prefix frontend ci
```

## A fresh Linux setup

Run from the repository root with Python 3.11 and the recorded Node version installed:

```bash
python3.11 -m venv .venv
.venv/bin/python -m pip install -r requirements-demo.txt
.venv/bin/python -m pip check
npm --prefix frontend ci
```

`requirements-demo.txt` pins the direct and transitive Python dependencies from the verified local environment. `frontend/package-lock.json` records the frontend dependency tree; use `npm ci` to install it. Installation needs a package registry connection. The simulator, regression tests and judging preflight use offline synthetic inputs once dependencies are installed; their local HTTP tests bind to loopback.

`requirements.txt` keeps the broader development compatibility bounds. Use the pinned demo file when preparing another machine for judging or reproducing a reported result. When dependencies change, review the pins and rerun the checks below rather than silently upgrading the presentation environment.

## Verify the engine and the browser artifact

On Windows:

```powershell
$pytestBase = Join-Path (Get-Location) ('.pytest-tmp-' + [guid]::NewGuid().ToString('N'))
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp $pytestBase
.\.venv\Scripts\python.exe scripts/run_judging_demo.py --check
npm.cmd --prefix frontend test
.\.venv\Scripts\python.exe scripts/build_static_site.py --output dist/aegisai-verified
```

On Linux:

```bash
.venv/bin/python -m pytest -q -p no:cacheprovider
.venv/bin/python scripts/run_judging_demo.py --check
npm --prefix frontend test
.venv/bin/python scripts/build_static_site.py --output dist/aegisai-verified
```

The static publisher requires a new or empty destination. A subsequent run should use a different output path. It copies the explicit public allowlist, excluding the private API, local dashboard, databases and source evidence. Preparing this directory does not deploy it.

The frontend test command includes TypeScript checks, the production build, component tests and static-release checks. The static-release tests call `python` through `PATH`; activate the virtual environment first if that command otherwise resolves to a different Python installation. Activation is `.\.venv\Scripts\Activate.ps1` on PowerShell or `source .venv/bin/activate` on Bash. Alternatively, use an environment where `python` already selects the intended interpreter.

## Compare defender policies

The default paired benchmark reruns both defenders against the same attacker, scenarios and seeds: **30 matched comparisons**, with fresh agents and Controllers for each episode. It reports attacker outcomes alongside the availability cost of isolating hosts.

To run it on Windows and save a new local evidence report:

```powershell
.\.venv\Scripts\python.exe scripts/run_defender_benchmark.py
```

On Linux:

```bash
.venv/bin/python scripts/run_defender_benchmark.py
```

The command prints its evidence path under `.aegisai-local/benchmarks/`. Use `--stdout` to print the complete JSON report without writing files, or `--output <new-file.json>` to choose a new destination. Existing evidence files are never overwritten.

The full **Python** test suite already reruns all 30 matched comparisons and checks the complete report against [the reviewed benchmark](../results/evaluation/defender_benchmark_v1.json), including its source fingerprints. The CI Python-test step therefore covers benchmark drift; a separate duplicate benchmark run is unnecessary. Frontend tests remain a separate check and do not replace the Python suite. These authored synthetic comparisons show regression behavior, not real-world effectiveness.

## Continuous verification

[The verification workflow](../.github/workflows/verify.yml) is configured for pushes, pull requests and manual runs on Windows and Linux. It installs the pinned Python environment and locked frontend dependencies, runs the offline Python suite and judging preflight, then checks and packages the public static site. It uses a read-only repository token and performs no deployment, live-provider request or publication.

The workflow uses the documented version-file and lockfile-cache inputs from the official [setup-python](https://github.com/actions/setup-python) and [setup-node](https://github.com/actions/setup-node) actions. Actions are pinned to immutable release commits. A local pass does not establish that a hosted workflow has run: inspect the repository's Actions results after committing and pushing the workflow.

For the project story and presentation rehearsal, see [JUDGES_GUIDE.md](JUDGES_GUIDE.md).
