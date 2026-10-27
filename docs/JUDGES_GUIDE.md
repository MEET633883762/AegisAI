# Presenting AegisAI to judges

Current runtime, feature inventory, and dated verification results: [CURRENT_STATUS.md](CURRENT_STATUS.md).

AegisAI is a controlled cybersecurity research lab that shows how a simulated attacker gets in, what a defender notices, and whether the defender stops the attack. Every action passes through a permission check and leaves a record of its evidence and outcome. The public dashboard replays a reviewed example without running attacks or depending on a live AI service.

## The pitch

**One sentence:** AegisAI shows how a simulated cyberattack unfolds, what the defender notices, and why noticing a threat does not always mean stopping it.

**Thirty seconds:**

> A security system can notice suspicious activity and still fail to stop it. AegisAI makes that gap visible. In a simulated company network, an attacker tries to reach protected data while a defender investigates. A permission gate checks every action, and the dashboard shows what each side knew and what happened next. We can replay the same exercise to compare decisions and find where the defense needs to improve.

The central contribution to demonstrate is the connection between **observations, decisions, authorization, and outcomes**. The website is the inspection surface; the Python Controller and reproducible experiment pipeline are the engineering underneath it.

## Prepare before the presentation

Run commands from the repository root. These are PowerShell commands; they do not depend on the repository being installed at a particular drive or path. Python 3.11 is a verified interpreter for this workspace. For a fresh machine, prepare an isolated environment while internet access is available:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-demo.txt
npm.cmd --prefix frontend ci
```

On a prepared machine, run the offline preflight:

```powershell
.\.venv\Scripts\python.exe scripts/run_judging_demo.py
```

If using the existing Python 3.11 environment instead of a virtual environment:

```powershell
py -3.11 scripts/run_judging_demo.py
```

The command creates a new packet under `.aegisai-local/judging-demo/` and prints its exact path. It regenerates the Controller episode and synthetic evaluation, checks repeatability, and compares the episode with the checked-in public sample. The packet contains `episode.json`, `detection-evaluation.json`, and `verification.json`; it preserves previous packets and does not change the application database. A nonzero exit means a check needs attention before presenting.

Start the browser demo in another terminal:

```powershell
npm.cmd --prefix frontend run dev -- --host 127.0.0.1
```

Open `http://localhost:5174/dashboard.html`. Choose **Present demo** in the top navigation to focus the exercise and enlarge the text for projection; **Exit presentation** returns to the full dashboard. Use **Next moment** to follow the six-part story and **Back** to revisit a moment. Expand the evidence when a judge wants technical detail. Keep the server running through the presentation; stop it with Ctrl+C afterward. Once dependencies are installed, this route and the offline preflight need no internet connection or API key. Preload the page and the published assessment samples before the session. Use the same computer for the browser and the local server.

For a final rehearsal, run the existing checks before the event:

```powershell
$pytestBase = Join-Path (Get-Location) ('.aegisai-local/test-artifacts/run-' + [guid]::NewGuid().ToString('N'))
py -3.11 -m pytest -q --basetemp $pytestBase
npm.cmd --prefix frontend test
```

If using the virtual environment, substitute `.\.venv\Scripts\python.exe` for `py -3.11` above. Keep the output of the fresh checks; the historical counts in older phase documents describe earlier repository states.

## Suggested four-minute demonstration

The engine also now demonstrates an actual policy improvement. Run `py -3.11 scripts/run_defender_benchmark.py` to compare the original defender with the new defender on 30 matched synthetic cases. The attacker reaches its objective in 3 baseline runs and 0 candidate runs: 3 improved pairs, 0 regressions, and 27 unchanged pairs. The candidate keeps the simulated website isolated, so explain the availability cost rather than calling the policy universally better. The public walkthrough deliberately preserves the original baseline; the comparison is a separate reproducible engine run. See [DEFENDER_COMPARISON.md](DEFENDER_COMPARISON.md) for the method and reviewed evidence.

No judging time limit has been supplied. This is a rehearsal format that can be shortened or extended. Start with the visual story; open technical evidence only after the audience understands the outcome.

| Time | Show | Say |
|---|---|---|
| 0:00–0:30 | Landing page or dashboard introduction | Use the thirty-second pitch. Name the audience: researchers and learners who need to understand and compare security decisions. |
| 0:30–1:00 | Attacker, defender, and permission-gate explanation | “The attacker tries to reach protected data. The defender sees alerts and decides how to respond. The permission gate checks every move before the simulation changes.” |
| 1:00–1:50 | Guided story: move from an early attacker action to a defender action | “First the attacker looks for a way in. Then the defender notices activity and investigates.” Follow the highlighted target and outcome. If asked how this is verified, expand an action's evidence and permission details. |
| 1:50–2:30 | Final Red exfiltration action and episode metrics | “The defender detects 8 of 9 malicious alerts, but mitigates 0 of 6 response-required alerts. Red still reaches its simulated objective. Detection alone did not produce containment. This is exactly the kind of failure the lab should reveal.” |
| 2:30–3:10 | Website Header Assessment; load published baseline and hardened samples | “Here is a separate, narrow before-and-after example: four missing checked headers become zero. Each finding has evidence and a remediation. This demonstrates report comparison for HTTP status and four headers; it does not certify a website as secure.” |
| 3:10–3:40 | Optional: preflight terminal and verification packet | “This is a replay of a real simulator run: 39 recorded actions over 20 steps. We can run the same exercise again and check that the result matches the dashboard.” |
| 3:40–4:00 | Return to the dashboard | “The next milestone is broader independent scenarios and stronger defender policies, evaluated with the same inspectable evidence. The system already gives us a way to identify and measure that work.” |

Use the actual labels and counts printed by the latest preflight if implementation changes. The checked-in showcase currently reports the values above. The 8/9 and 0/6 values belong to **one simulator episode**; they are separate from the synthetic detection-rule evaluation.

For a three-minute slot, omit the header comparison and terminal demonstration. For a five-minute slot, open `verification.json` and explain why repeatability and explicit denominators make a result reviewable. Let the visual story lead; do not spend the opening minute listing folders, frameworks, or development phases.

## Architecture in plain language

| Layer | Responsibility | What to point to |
|---|---|---|
| Red and Blue agents | Choose structured actions using their own observations | `agents/`; scripted policies power the public showcase; separate LLM adapters are also implemented. |
| Controller | Validate and authorize actions before simulator mutation | `controller/`; role separation, turn ordering, and bounded submissions. |
| Synthetic environment | Apply allowed actions and produce events | `environment/`; deterministic scenario template and seed. |
| Evidence and evaluation | Preserve traces, compute defined metrics, compare experiments | `telemetry/`, `xai/`, `evaluation/`; role-visible evidence and factual outcomes, without hidden chain-of-thought. |
| Public dashboard | Display reviewed static artifacts | `frontend/`; provenance, action selection, metrics, and narrow assessment comparison. |
| Separate local operations prototype | Exercise synthetic telemetry, detections, investigations, and reporting | `platform_prototype/` and `private_api/`; loopback-only local capabilities, outside the public site. |

Describe the public showcase and local operations prototype as separate parts of the repository. The public dashboard does not call the private API or start simulator runs.

When presenting, focus the replay and use Left/Right to advance or revisit a key moment; Home/End jumps to the beginning or final moment. The same controls remain available as buttons. Open **Look under the hood** to filter attacker/defender actions or search the recorded evidence. The selected action stays visible in its detail panel while you filter. **Clear action filters** returns to all 39 actions. The landing page's **Questions** section covers execution, AI's role, reproducibility, and the containment tradeoff.

## Evidence to explain carefully

The fixed detection dataset currently contains 15 accepted scenarios, evaluated against five supported rules, plus four rejected-input cases. The checked-in report records 9 true positives, 66 true negatives, zero false positives, and zero false negatives across 75 scenario-by-rule pairs. Rejected-input checks are counted separately. These are hand-authored regression examples, so their perfect scores show agreement with those examples and labels; they do not establish real-world detection accuracy.

Keep these quantities distinct:

- **39 recorded actions** describe the public simulator episode.
- **8/9 detected alerts and 0/6 mitigated alerts** describe that episode's outcomes.
- **75 scenario-by-rule pairs** describe the separate fixed synthetic detector evaluation.
- **Four headers** describe the separate local website assessment sample.
- **Test-suite counts** describe software verification, not cybersecurity effectiveness.

## Likely judge questions

**Where is the AI?** The repository includes structured LLM Red and Blue agents, a provider interface, an OpenAI adapter, and experiment tooling. The public showcase deliberately uses scripted policies to make the presentation repeatable. Offline test-double runs validate the harness; they are not evidence about actual LLM intelligence or improvement.

**What is the novel or valuable part?** The engineering contribution is a controlled experiment workflow that connects role-limited observations, typed actions, authorization, factual outcomes, and reproducible evaluation. Show those connections in one action rather than claiming to be the first system of its kind.

**Why does the attacker succeed in your example?** A useful lab must expose failures. This example shows that detecting alerts and successfully containing an incident are different measurements. The current scripted defender continues investigating rather than achieving mitigation. That gives us a clear policy-improvement target without hiding an unfavorable result.

**Can an AI execute arbitrary commands?** Agents submit typed action objects to the simulator Controller. The action vocabulary is bounded; the showcase does not give the agents shell access or a real target. The public browser only reads static JSON.

**Is the public dashboard live?** It is an interactive replay of precomputed evidence. The offline preflight regenerates that evidence locally. The separate local operations prototype has authenticated API views, but that is not what the public dashboard uses.

**Do perfect detection metrics mean it catches every attack?** No. The fixed synthetic dataset checks authored cases and boundaries for five rules. It is small, known, and unrepresentative of real traffic. Broader independent datasets, unseen scenarios, and operational evaluation are future work.

**Does adaptive memory already make it better?** There is a memory-candidate validation mechanism and A/B/C experiment support. Do not claim an improvement unless a specific held-out experiment with the relevant provider and dataset establishes it. A deterministic test double proves workflow behavior rather than model learning.

**Is it ready for customers?** It is a local research prototype with a static public demonstration. Production authentication, deployment, recovery, external validation, and broader operational testing remain future milestones. The current private API is designed for local development.

**What would you improve next?** Prioritize stronger defender actions, independent held-out scenario families, and comparisons that include containment and false positives. Then evaluate selected real models under bounded budgets. Each step should preserve the same provenance, authorization checks, and evidence trail.

## If something fails during the presentation

If Python reports a `StrEnum` import error, the selected interpreter is too old. Use `.\.venv\Scripts\python.exe scripts/run_private_api.py` after setup, or `py -3.11 scripts/run_private_api.py` when its dependencies are already installed. The public walkthrough needs no API process; this startup applies only to the separate local operations dashboard. `.python-version` does not change Windows `PATH`.

If the browser is blank, confirm Vite is running and open the exact localhost URL. Do not use `file://` to open the HTML. If port 5174 is occupied, stop a known previous AegisAI development server or resolve the conflict before the session; the configured server intentionally refuses to silently pick another port.

If the preflight reports a stale sample, do not dismiss the mismatch. Rehearse and review the changed evidence before regenerating the public artifact. For judging, keep the last verified packet available as a clearly labeled previous run.

If live startup fails during a short slot, open the saved `episode.json` and `verification.json` packet and explain the same action/evidence/outcome flow. Keep a screenshot from a successful rehearsal as a visual backup. A saved report is credible when its provenance is clear; do not describe it as a live run.

End on the research question and demonstrated insight: **which decisions turn available security evidence into effective action, and how can we evaluate that safely and reproducibly?**
