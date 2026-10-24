# Phase 5B — Local Live Telemetry Validation

## Boundaries

Phase 5B adds a small harmless Python test website that binds only to `127.0.0.1:8767`. It is separate from the public React + TypeScript + Vite website and from `demo_site/server.py`. The test site supports a home page, health page, fixed synthetic login-failure response, and a fixed harmless error response. It accepts no credentials or request bodies, runs no exploit code, and has no configuration or remediation functions.

The test site itself writes JSONL access and error records under the ignored local directory `.aegisai-local/website-telemetry/`. Records include generated event/evidence IDs, UTC timestamps, allowlisted method and route codes, status codes, and a fixed error category. It never records raw request paths, query strings, headers, IP addresses, bodies, credentials, or exception text. The server suppresses console request logging and handles Ctrl+C/programmatic shutdown cleanly.

The ingestion CLI accepts an optional `--database` path. It reads only `access.jsonl`, `access.jsonl.1`, `errors.jsonl`, and `errors.jsonl.1` from that fixed directory, validates records with the Phase 5A schema, maps them into the existing Phase 3 event batch, and stores them under the fixed `synthetic-org-demo` tenant. When omitted, it uses `.aegisai-local/private_api.sqlite3`; pass the same explicit database path used by the private API when demonstrating with a separate presentation database. The Phase 3 detector, evidence links, duplicate checks, SQLite transaction, audit event, and retention policy are reused. No API route or database migration is added. The Phase 5A authored fixture and its CLI remain available and unchanged in behavior.

## Run the local test

Use three PowerShell terminals from `C:\AegisAI`:

1. Start the harmless website:

   ```powershell
   python demo_site/telemetry_server.py
   ```

   It reports `http://127.0.0.1:8767/` and listens on loopback only.

2. Generate fixed normal, failed-login, and harmless-error requests:

   ```powershell
   python scripts/generate_local_website_traffic.py
   ```

   The generator has no target argument and sends requests only to `127.0.0.1`. It sends no credentials or request body. Expected statuses include 200, 401, and 500. Three synthetic failed login records meet the existing `AUTH-001` example threshold; the 500 error is recorded as a benign `DEMO_ERROR_RESPONSE` observation and does not trigger a finding.

3. Ingest the live logs:

   ```powershell
   python scripts/ingest_live_website_telemetry.py --database .aegisai-local/presentation.sqlite3
   ```

   The command prints a synthetic telemetry report and writes to the selected presentation database. Repeating ingestion rereads the bounded source snapshot; stable event and evidence IDs make stored events and findings idempotent.

Stop the website with Ctrl+C. Its logs remain in `.aegisai-local/website-telemetry/`. Optional local API read-only views remain available through the existing `python scripts/run_private_api.py`; the public static site does not connect to that API.

## Log bounds, partial records, and rotation

Each of the four fixed files is read with a 1 MiB cap (one sentinel byte is used to detect overflow); each complete JSONL line is capped at 16 KiB; an ingestion batch is capped at 500 records. A trailing line without a newline is treated as a write in progress and ignored. The next ingestion rereads the file, so a subsequently completed line is then validated. A malformed complete line fails the batch with a categorical error; its content is not echoed.

The connector reads the active file and one fixed `.1` rotated copy for both access and error logs. It rereads snapshots instead of maintaining byte offsets, so truncation does not remove persisted SQLite events, and stable event IDs deduplicate records found in both files. The test website does not automatically rotate files. If rotating manually, ingest first, then move the active file to its `.1` name; ingest both copies before replacing an existing `.1`. Only one previous generation is supported. If multiple rotations occur before ingestion, older unpersisted lines can be lost; stored records are not deleted. Files above the size limit fail closed and should be ingested/rotated before further test traffic.

The server and connector reject symlinked log roots/files and paths outside the fixed local directory. Neither CLI accepts a path, URL, tenant, upload, or API request. The local CLI runs with the OS user's authority; it is for a developer's synthetic test data only, not an authenticated multi-user operation.

## Cleanup

Stop the server and any API process. The generated web logs can be removed individually if no longer needed:

```powershell
Remove-Item -LiteralPath .aegisai-local/website-telemetry/access.jsonl, .aegisai-local/website-telemetry/access.jsonl.1, .aegisai-local/website-telemetry/errors.jsonl, .aegisai-local/website-telemetry/errors.jsonl.1 -ErrorAction SilentlyContinue
```

This removes only the four generated log files. It does not remove ingested telemetry from SQLite; the existing per-tenant retention policy applies. Do not remove the database if its other local synthetic records are needed.

## Tests and limitations

Automated tests exercise actual loopback requests and server shutdown, generated access/error log content, malformed records, partial lines, fixed rotation/truncation behavior, byte/line bounds, symlink/path rejection, repeated ingestion, evidence provenance, fixed-tenant isolation, and the unchanged read-only API boundary. All requests target loopback in tests; no external systems are contacted.

These logs demonstrate connector plumbing against a purpose-built local website. They are not customer logs, do not verify the live behavior of the public frontend, and do not establish real-world detection accuracy. The test site is a local fixture server, not a production web-server or security control.
