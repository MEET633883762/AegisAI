# Reproduce and verify AegisAI

Current runtime, feature inventory, and dated verification results: [CURRENT_STATUS.md](CURRENT_STATUS.md).

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

## Start the local operations API

After the setup above, start the API from the repository root using the environment's interpreter. Verify it with `.\.venv\Scripts\python.exe --version` on Windows or `.venv/bin/python --version` on Linux; it must be Python 3.11 or later.

On Windows:

```powershell
.\.venv\Scripts\python.exe scripts/run_private_api.py
```

On Linux:

```bash
.venv/bin/python scripts/run_private_api.py
```

If the reviewed dependencies are already installed directly in Python 3.11 on Windows, `py -3.11 scripts/run_private_api.py` also selects that interpreter explicitly. Keep the API terminal open and use its startup token in the separate local dashboard.

### Python version mismatch (`StrEnum`)

`ImportError: cannot import name 'StrEnum'` with a `Python310` path means the command used Python 3.10. The API requires Python 3.11 or later; the reviewed environment uses 3.11. `.python-version` records that choice but does not change an existing `python` command or Windows `PATH`.

From the repository root, prepare and start the reviewed environment:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-demo.txt
.\.venv\Scripts\python.exe scripts/run_private_api.py
```

If `.venv` was previously created with an older interpreter, create a separate Python 3.11 environment, such as `.aegisai-local/venv311`, and use that directory's interpreter for installation and startup.

## Verify the engine and the browser artifact

On Windows:

```powershell
$pytestBase = Join-Path (Get-Location) ('.aegisai-local/test-artifacts/run-' + [guid]::NewGuid().ToString('N'))
.\.venv\Scripts\python.exe -m pytest -q --basetemp $pytestBase
.\.venv\Scripts\python.exe scripts/run_judging_demo.py --check
npm.cmd --prefix frontend test
.\.venv\Scripts\python.exe scripts/build_static_site.py --output dist/aegisai-verified
```

On Linux:

```bash
.venv/bin/python -m pytest -q --basetemp ".aegisai-local/test-artifacts/run-$(date +%s)-$$"
.venv/bin/python scripts/run_judging_demo.py --check
npm --prefix frontend test
.venv/bin/python scripts/build_static_site.py --output dist/aegisai-verified
```

The static publisher requires a new or empty destination. A subsequent run should use a different output path. It copies the explicit public allowlist, excluding the private API, local dashboard, databases and source evidence. Preparing this directory does not deploy it.

Test runs use a fresh directory under `.aegisai-local/test-artifacts/`; the optional pytest cache is also configured under `.aegisai-local/`. Existing root-level test folders have been preserved in `test-artifacts/legacy/` there. Keep generated outputs in these ignored locations rather than alongside source packages. A unique temp directory also keeps separate local runs from sharing pytest's working files. Leave pytest's cache plugin enabled for these commands: `pytest.ini` configures `cache_dir`, and disabling that plugin can produce an unknown-option warning.

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

CI selects its interpreter using `actions/setup-python`, so the workflow's unqualified `python` runs in that configured environment. For local terminals, keep using the explicit virtual-environment path.

The workflow uses the documented version-file and lockfile-cache inputs from the official [setup-python](https://github.com/actions/setup-python) and [setup-node](https://github.com/actions/setup-node) actions. Actions are pinned to immutable release commits. A local pass does not establish that a hosted workflow has run: inspect the repository's Actions results after committing and pushing the workflow.

For the project story and presentation rehearsal, see [JUDGES_GUIDE.md](JUDGES_GUIDE.md).
