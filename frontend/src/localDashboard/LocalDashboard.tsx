import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent, type ReactNode } from "react";
import { getLocalApi, LocalApiError, type ApiRoute } from "./api";
import type { EvidenceResponse, FindingsResponse, HealthResponse, ProcessingResponse, SourceResponse, TelemetryFinding } from "./types";

type View = "overview" | "findings" | "detection" | "health";
const NAV: { id: View; label: string }[] = [
  { id: "overview", label: "Overview" }, { id: "findings", label: "Findings" },
  { id: "detection", label: "Detection Lab" }, { id: "health", label: "System Health" },
];
const SEVERITIES = ["critical", "high", "medium", "low"] as const;
const dateText = (value?: string | null) => value ? new Date(value).toLocaleString() : "Not recorded";

type Snapshot = {
  health: HealthResponse | null;
  findings: TelemetryFinding[] | null;
  processing: ProcessingResponse | null;
  source: SourceResponse | null;
  errors: Partial<Record<"health" | "findings" | "processing" | "source", string>>;
  loadedAt: number;
};

const emptySnapshot = (): Snapshot => ({ health: null, findings: null, processing: null, source: null, errors: {}, loadedAt: 0 });

export function LocalDashboard() {
  const [view, setView] = useState<View>("overview");
  const [tokenInput, setTokenInput] = useState("");
  const [token, setToken] = useState("");
  const [snapshot, setSnapshot] = useState<Snapshot>(emptySnapshot);
  const [loading, setLoading] = useState(false);
  const [refreshError, setRefreshError] = useState("");
  const [search, setSearch] = useState("");
  const [severity, setSeverity] = useState("all");
  const [typeFilter, setTypeFilter] = useState("all");
  const [status, setStatus] = useState("all");
  const [selectedId, setSelectedId] = useState("");
  const [evidence, setEvidence] = useState<EvidenceResponse | null>(null);
  const [evidenceError, setEvidenceError] = useState("");
  const refreshGeneration = useRef(0);

  const refresh = useCallback(async (activeToken: string) => {
    const generation = ++refreshGeneration.current;
    setLoading(true);
    setRefreshError("");
    const read = async <T,>(name: "health" | "findings" | "processing" | "source", route: ApiRoute) => {
      try { return { name, value: await getLocalApi<T>(route, activeToken), error: "" }; }
      catch (error) {
        const safe = error instanceof LocalApiError ? error.message : "The local API request failed.";
        return { name, value: null, error: safe };
      }
    };
    const results = await Promise.all([
      read<HealthResponse>("health", "/health"),
      read<FindingsResponse>("findings", "/api/telemetry/findings"),
      read<ProcessingResponse>("processing", "/api/processing"),
      read<SourceResponse>("source", "/api/telemetry/sources/live-website/status"),
    ]);
    if (generation !== refreshGeneration.current) return;
    setSnapshot((previous) => {
      const next: Snapshot = { ...emptySnapshot(), loadedAt: results.some((item) => !item.error) ? Date.now() : previous.loadedAt };
      for (const result of results) {
        if (result.name === "health") next.health = result.value as HealthResponse | null ?? previous.health;
        if (result.name === "findings") next.findings = result.value ? (result.value as FindingsResponse).findings : previous.findings;
        if (result.name === "processing") next.processing = result.value as ProcessingResponse | null ?? previous.processing;
        if (result.name === "source") next.source = result.value as SourceResponse | null ?? previous.source;
        if (result.error) next.errors[result.name] = result.error;
      }
      return next;
    });
    const failedCount = results.filter((item) => item.error).length;
    setRefreshError(failedCount === results.length
      ? "The local API could not refresh any view. Previously loaded values are retained and may be stale."
      : failedCount ? "Some local API views could not refresh. Previously loaded values for those views are retained and may be stale." : "");
    setLoading(false);
  }, []);

  useEffect(() => {
    if (token && selectedId) {
      let alive = true;
      setEvidence(null); setEvidenceError("");
      void getLocalApi<EvidenceResponse>(`/api/telemetry/findings/${encodeURIComponent(selectedId)}/evidence`, token)
        .then((data) => { if (alive) setEvidence(data); })
        .catch((error: unknown) => { if (alive) setEvidenceError(error instanceof LocalApiError ? error.message : "Evidence is unavailable."); });
      return () => { alive = false; };
    }
    setEvidence(null); setEvidenceError("");
  }, [token, selectedId]);

  const findings = snapshot.findings ?? [];
  const filtered = useMemo(() => findings.filter((finding) => {
    const text = `${finding.finding_id} ${finding.rule_id} ${finding.asset_ref} ${finding.explanation}`.toLowerCase();
    return (severity === "all" || finding.severity === severity)
      && (status === "all" || finding.status === status)
      && (typeFilter === "all" || finding.rule_id === typeFilter)
      && text.includes(search.trim().toLowerCase());
  }), [findings, search, severity, status, typeFilter]);
  const selected = findings.find((finding) => finding.finding_id === selectedId) ?? null;
  const totals = useMemo(() => SEVERITIES.map((key) => ({ key, count: findings.filter((item) => item.severity === key).length })), [findings]);

  function connect(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const candidate = tokenInput.trim();
    if (!candidate) return;
    setToken(candidate);
    setTokenInput("");
    setSelectedId("");
    setEvidence(null);
    void refresh(candidate);
  }

  function disconnect() {
    refreshGeneration.current += 1;
    setLoading(false);
    setToken(""); setTokenInput(""); setSnapshot(emptySnapshot()); setSelectedId(""); setEvidence(null);
  }

  return <div className="local-ops">
    <a className="ops-skip" href="#ops-main">Skip to dashboard content</a>
    <header className="ops-topbar"><a className="ops-brand" href="index.html" aria-label="AegisAI public site"><span className="ops-logo">A</span><span>Aegis<span>AI</span><small>LOCAL OPERATIONS</small></span></a>
      <div className="ops-top-actions"><span className="ops-loopback"><i /> LOOPBACK ONLY</span>{token ? <button type="button" className="ops-quiet-button" onClick={disconnect}>Disconnect</button> : <span className="ops-lock">Local token required</span>}</div>
    </header>
    <div className="ops-layout">
      <aside className="ops-sidebar"><div className="ops-side-label">WORKSPACE</div><nav aria-label="Dashboard sections">{NAV.map((item) => <button key={item.id} type="button" className={view === item.id ? "ops-nav-active" : ""} aria-current={view === item.id ? "page" : undefined} onClick={() => setView(item.id)}><span className={`ops-nav-glyph glyph-${item.id}`} aria-hidden="true" />{item.label}{item.id === "findings" && snapshot.findings && <b>{findings.length}</b>}</button>)}</nav>
        <section className="ops-connection"><div className="ops-side-label">LOCAL API</div><p>Connect to the synthetic service running on this computer.</p>{token ? <div className="ops-connected"><i /> Token held in memory</div> : <form onSubmit={connect}><label htmlFor="ops-token">Startup bearer token</label><input id="ops-token" type="password" autoComplete="off" value={tokenInput} onChange={(event) => setTokenInput(event.currentTarget.value)} placeholder="Paste current token"/><button className="ops-connect-button" type="submit" disabled={!tokenInput.trim()}>Connect</button><small>Held only in page memory. Never saved.</small></form>}</section>
        <div className="ops-side-foot"><span className="ops-mini-logo">A</span><span>Synthetic prototype<br/><b>Read only · Local data</b></span></div>
      </aside>
      <main id="ops-main" className="ops-main">
        <div className="ops-page-heading"><div><div className="ops-eyebrow">AEGISAI / LOCAL WORKSPACE</div><h1>{NAV.find((item) => item.id === view)?.label}</h1><p>Inspect synthetic telemetry and rule outputs from your local prototype.</p></div><div className="ops-heading-controls">{snapshot.loadedAt > 0 && <span className="ops-updated">Updated {dateText(new Date(snapshot.loadedAt).toISOString())}</span>}<button type="button" className="ops-refresh" disabled={!token || loading} onClick={() => token && void refresh(token)}><span aria-hidden="true">↻</span> {loading ? "Refreshing…" : "Refresh"}</button></div></div>
        <div className="ops-disclosure" role="note"><span className="ops-disclosure-icon" aria-hidden="true">i</span><p><strong>Synthetic local prototype.</strong> Findings and activity shown here come from synthetic fixtures or the harmless local demo site. This is not a production SOC or evidence of real-world attack detection. All views are read only.</p></div>
        {!token && <div className="ops-callout" role="status"><strong>Connect to view local data</strong><span>Start the private API in another terminal, then paste its one-time startup token in the sidebar.</span><code>python scripts/run_private_api.py</code></div>}
        {refreshError && <p className="ops-error-banner" role="alert">{refreshError}</p>}
        {view === "overview" && <Overview findings={findings} totals={totals} snapshot={snapshot} connected={Boolean(token)} onOpenFindings={() => setView("findings")} onSelect={setSelectedId} />}
        {view === "findings" && <FindingsView findings={filtered} available={snapshot.findings !== null} unavailableMessage={snapshot.errors.findings ?? "Findings are not available."} types={Array.from(new Set(findings.map((item) => item.rule_id))).sort()} total={findings.length} selected={selected} evidence={evidence} evidenceError={evidenceError} connected={Boolean(token)} search={search} setSearch={setSearch} severity={severity} setSeverity={setSeverity} typeFilter={typeFilter} setTypeFilter={setTypeFilter} status={status} setStatus={setStatus} onSelect={setSelectedId} />}
        {view === "detection" && <DetectionView />}
        {view === "health" && <HealthView snapshot={snapshot} connected={Boolean(token)} />}
        <footer className="ops-footer"><span>AEGISAI LOCAL PROTOTYPE</span><span>Synthetic data · No response actions · No external connections</span><a href="index.html">Public research site ↗</a></footer>
      </main>
    </div>
  </div>;
}

function MetricCard({ label, value, note, tone = "" }: { label: string; value: string | number; note: string; tone?: string }) {
  return <article className={`ops-metric ${tone}`}><div className="ops-metric-top"><span>{label}</span><i aria-hidden="true" /></div><strong>{value}</strong><small>{note}</small></article>;
}

function Panel({ title, kicker, children, action }: { title: string; kicker?: string; children: ReactNode; action?: ReactNode }) {
  return <section className="ops-panel"><div className="ops-panel-head"><div>{kicker && <span>{kicker}</span>}<h2>{title}</h2></div>{action}</div>{children}</section>;
}

function Overview({ findings, totals, snapshot, connected, onOpenFindings, onSelect }: {
  findings: TelemetryFinding[]; totals: { key: string; count: number }[]; snapshot: Snapshot; connected: boolean; onOpenFindings: () => void; onSelect: (id: string) => void;
}) {
  const run = snapshot.processing?.latest_run;
  const source = snapshot.source;
  const count = (value: number | undefined) => value === undefined ? "—" : value;
  return <>
    <div className="ops-section-title"><div><span className="ops-eyebrow">CURRENT SNAPSHOT</span><h2>Security overview</h2></div><span className="ops-synthetic-tag"><i /> Synthetic data</span></div>
    <div className="ops-metric-grid"><MetricCard label="Open findings" value={connected && snapshot.findings ? findings.filter((item) => item.status === "open").length : "—"} note={connected ? "From authorized telemetry API" : "Connect to load local data"} tone="metric-blue"/><MetricCard label="High severity" value={connected && snapshot.findings ? findings.filter((item) => item.severity === "high" || item.severity === "critical").length : "—"} note="High + critical findings" tone="metric-red"/><MetricCard label="Accepted events" value={count(run?.accepted_event_count ?? source?.accepted_event_count)} note="Latest available processing result" tone="metric-green"/><MetricCard label="Duplicates" value={count(run?.duplicate_event_count ?? source?.duplicate_event_count)} note="Deduplicated source records" tone="metric-purple"/><MetricCard label="Rejected records" value={count(source?.rejected_record_count)} note="Reported by fixed local source only" tone="metric-red"/></div>
    <div className="ops-content-grid"><Panel title="Findings by severity" kicker="DETECTION SNAPSHOT" action={<button type="button" className="ops-link-button" onClick={onOpenFindings}>View all <span aria-hidden="true">→</span></button>}>
      {!connected ? <EmptyState title="Connect to load findings" text="Severity totals are calculated from the authorized local API response."/> : snapshot.findings === null ? <Unavailable text={snapshot.errors.findings ?? "Findings are not available."}/> : findings.length === 0 ? <EmptyState title="No findings yet" text="No synthetic findings are currently returned for this tenant."/> : <div className="ops-severity-list">{totals.map((item) => <div className="ops-severity-row" key={item.key}><span className={`severity-dot severity-${item.key}`} /><span>{item.key}</span><div className="ops-severity-track"><i className={`severity-fill fill-${item.key}`} style={{ width: `${Math.max(item.count ? 3 : 0, findings.length ? item.count / findings.length * 100 : 0)}%` }}/></div><b>{item.count}</b></div>)}</div>}
      <p className="ops-panel-footnote">Counts include the currently loaded finding records only.</p>
    </Panel><Panel title="Recent findings" kicker="INVESTIGATE" action={<span className="ops-panel-count">{connected ? `${findings.length} total` : "Not connected"}</span>}>
      {!connected ? <EmptyState title="Local data unavailable" text="Connect the local API to inspect findings."/> : snapshot.findings === null ? <Unavailable text={snapshot.errors.findings ?? "Findings are not available."}/> : findings.length === 0 ? <EmptyState title="No recent findings" text="New findings will appear here after a successful synthetic processing run."/> : <ul className="ops-recent-list">{[...findings].sort((a,b) => b.last_seen_utc.localeCompare(a.last_seen_utc)).slice(0,4).map((finding) => <li key={finding.finding_id}><button type="button" onClick={() => onSelect(finding.finding_id)}><span className={`severity-dot severity-${finding.severity}`} /><span className="recent-main"><b>{finding.rule_id}</b><small>{finding.asset_ref} · {dateText(finding.last_seen_utc)}</small></span><span className={`ops-severity-pill severity-pill-${finding.severity}`}>{finding.severity}</span></button></li>)}</ul>}
    </Panel></div>
    <div className="ops-content-grid ops-lower-grid"><Panel title="Latest processing run" kicker="PROCESSING">
      {!connected ? <EmptyState title="Run status unavailable" text="Connect to read scheduler status and latest run counters."/> : !snapshot.processing ? <Unavailable text={snapshot.errors.processing ?? "Processing information is not available."}/> : run ? <div className="ops-run-summary"><div className="ops-run-status"><span className={`run-indicator run-${run.status}`} />{run.status}</div><dl><dt>Started</dt><dd>{dateText(run.started_at_utc)}</dd><dt>Input records</dt><dd>{run.input_event_count}</dd><dt>Accepted</dt><dd>{run.accepted_event_count}</dd><dt>Duplicates</dt><dd>{run.duplicate_event_count}</dd><dt>Findings in report</dt><dd>{run.finding_count}</dd></dl></div> : <EmptyState title="No run recorded" text="The API has not returned a processing run yet."/>}
    </Panel><Panel title="Source activity" kicker="LOCAL TEST SITE">
      {!connected ? <EmptyState title="Source status unavailable" text="Connect to check the authenticated local source status."/> : source ? <div className="ops-run-summary"><div className="ops-run-status"><span className={`run-indicator run-${source.status}`} />{source.status}</div><dl><dt>Last attempt</dt><dd>{dateText(source.last_attempt_at_utc)}</dd><dt>Last success</dt><dd>{dateText(source.last_success_at_utc)}</dd><dt>Accepted</dt><dd>{source.accepted_event_count}</dd><dt>Duplicates</dt><dd>{source.duplicate_event_count}</dd><dt>Rejected records</dt><dd>{source.rejected_record_count}</dd></dl></div> : <Unavailable text={snapshot.errors.source ?? "No source status has been recorded. This is not a healthy status."}/>}
    </Panel></div>
  </>;
}

function FindingsView({ findings, available, unavailableMessage, types, total, selected, evidence, evidenceError, connected, search, setSearch, severity, setSeverity, typeFilter, setTypeFilter, status, setStatus, onSelect }: {
  findings: TelemetryFinding[]; available: boolean; unavailableMessage: string; types: string[]; total: number; selected: TelemetryFinding | null; evidence: EvidenceResponse | null; evidenceError: string; connected: boolean; search: string; setSearch: (v: string) => void; severity: string; setSeverity: (v: string) => void; typeFilter: string; setTypeFilter: (v: string) => void; status: string; setStatus: (v: string) => void; onSelect: (id: string) => void;
}) {
  return <div className="ops-investigation"><Panel title="Finding queue" kicker="SYNTHETIC TELEMETRY" action={<span className="ops-panel-count">{connected ? `${findings.length} of ${total}` : "Not connected"}</span>}>
    <div className="ops-filters"><label className="ops-search">Search findings<input type="search" value={search} onChange={(e) => setSearch(e.currentTarget.value)} placeholder="ID, rule, asset, text"/></label><label>Severity<select value={severity} onChange={(e) => setSeverity(e.currentTarget.value)}><option value="all">All severities</option>{SEVERITIES.map((value) => <option key={value}>{value}</option>)}</select></label><label>Type<select value={typeFilter} onChange={(e) => setTypeFilter(e.currentTarget.value)}><option value="all">All rule types</option>{types.map((value) => <option key={value}>{value}</option>)}</select></label><label>Status<select value={status} onChange={(e) => setStatus(e.currentTarget.value)}><option value="all">All statuses</option><option value="open">open</option><option value="acknowledged">acknowledged</option><option value="closed">closed</option></select></label></div>
    {!connected ? <EmptyState title="Connect to investigate" text="The list is populated from the authenticated local telemetry findings endpoint."/> : !available ? <Unavailable text={unavailableMessage}/> : findings.length === 0 ? <EmptyState title="No matching findings" text="Adjust the search and filters, or wait for the next synthetic processing run."/> : <div className="ops-table-wrap"><table className="ops-findings-table"><thead><tr><th>Finding</th><th>Severity</th><th>Confidence</th><th>Last seen</th><th>Status</th></tr></thead><tbody>{findings.map((item) => <tr key={item.finding_id} className={selected?.finding_id === item.finding_id ? "selected-row" : ""}><td><button type="button" className="finding-select" onClick={() => onSelect(item.finding_id)}><b>{item.rule_id}</b><small>{item.finding_id} · {item.asset_ref}</small></button></td><td><span className={`ops-severity-pill severity-pill-${item.severity}`}>{item.severity}</span></td><td>{Math.round(item.confidence * 100)}%</td><td>{dateText(item.last_seen_utc)}</td><td>{item.status}</td></tr>)}</tbody></table></div>}
    </Panel>
    {selected && <Panel title="Investigation detail" kicker={selected.finding_id}><div className="ops-detail-summary"><span className={`ops-severity-pill severity-pill-${selected.severity}`}>{selected.severity}</span><span>Confidence {Math.round(selected.confidence * 100)}%</span><span>Rule {selected.rule_id} v{selected.rule_version}</span></div><p className="ops-explanation">{selected.explanation}</p><dl className="ops-detail-grid"><dt>Asset</dt><dd>{selected.asset_ref}</dd><dt>First seen</dt><dd>{dateText(selected.first_seen_utc)}</dd><dt>Last seen</dt><dd>{dateText(selected.last_seen_utc)}</dd><dt>Finding status</dt><dd>{selected.status}</dd><dt>Event IDs</dt><dd>{selected.event_ids.join(", ")}</dd></dl><h3 className="ops-subheading">Evidence references</h3>
      {evidenceError ? <Unavailable text={evidenceError}/> : !evidence ? <p className="ops-muted">Loading evidence from the tenant-scoped API…</p> : evidence.evidence.length === 0 ? <p className="ops-muted">No evidence records were returned.</p> : <ul className="ops-evidence-list">{evidence.evidence.map((item) => <li key={item.evidence_ref}><b>{item.evidence_ref}</b><span>{item.event_type} · {dateText(item.occurred_at_utc)}</span><small>Actor {item.actor_ref} · Source {item.source_ref} · Asset {item.asset_ref}</small></li>)}</ul>}
      <h3 className="ops-subheading">Confidence factors</h3><ul className="ops-factor-list">{selected.confidence_factors.map((factor) => <li key={factor}>{factor}</li>)}</ul><p className="ops-panel-footnote">Investigation is observational only. This dashboard has no acknowledge, close, or response controls.</p></Panel>}
  </div>;
}

function DetectionView() {
  return <div className="ops-detection-grid"><Panel title="Detection evaluation" kicker="PHASE 6B BENCHMARK"><div className="ops-unavailable-card"><span className="unavailable-glyph" aria-hidden="true">⌁</span><h3>Report not available through the local API</h3><p>The authenticated API exposes telemetry findings and the latest telemetry report, but it does not expose the Phase 6B evaluation report. This panel will not load a private evaluation file into the browser.</p><div className="ops-boundary-list"><span>Dataset and report stay local to the repository</span><span>No static publication or new API route</span><span>Synthetic benchmark only; no real-world accuracy claim</span></div></div></Panel><Panel title="What the benchmark measures" kicker="INTERPRETATION"><p className="ops-body-copy">Phase 6B compares expected and observed rule types for accepted synthetic scenario × supported-rule pairs. Invalid inputs are reported separately. Its confusion counts and nullable metrics should be reviewed from the local evaluation command and do not estimate operational detection performance.</p><p className="ops-command"><code>python scripts/run_detection_evaluation.py --stdout</code></p><p className="ops-panel-footnote">No report data is displayed here because there is no approved read path.</p></Panel></div>;
}

function HealthView({ snapshot, connected }: { snapshot: Snapshot; connected: boolean }) {
  const service = snapshot.health;
  const source = snapshot.source;
  const run = snapshot.processing?.latest_run;
  return <div className="ops-health-grid"><Panel title="Service status" kicker="LOCAL API"><StatusRow label="Loopback API" state={!connected ? "Not connected" : service ? "Healthy" : "Unavailable"} ok={Boolean(connected && service)}/><StatusRow label="Telemetry scheduler" state={!connected ? "Not connected" : snapshot.processing?.scheduler_state ?? "Unavailable"} ok={snapshot.processing?.scheduler_state === "running"}/><StatusRow label="Live demo source" state={!connected ? "Not connected" : source?.status ?? "No status recorded"} ok={source?.status === "healthy"}/><p className="ops-panel-footnote">A missing source status is shown as unavailable, not as a healthy source.</p></Panel><Panel title="Latest processing run" kicker="RUN DETAIL">{!connected ? <EmptyState title="No authorized status" text="Connect with a current local token."/> : run ? <div className="ops-health-facts"><div><span>Run status</span><b>{run.status}</b></div><div><span>Started</span><b>{dateText(run.started_at_utc)}</b></div><div><span>Accepted records</span><b>{run.accepted_event_count}</b></div><div><span>Duplicate records</span><b>{run.duplicate_event_count}</b></div><div><span>Finding count</span><b>{run.finding_count}</b></div>{run.error_code && <div><span>Error category</span><b>{run.error_code}</b></div>}</div> : <Unavailable text={snapshot.errors.processing ?? "No processing run is available."}/>}</Panel><Panel title="Source counters" kicker="FIXED LOCAL SOURCE">{source ? <div className="ops-health-facts"><div><span>Last attempt</span><b>{dateText(source.last_attempt_at_utc)}</b></div><div><span>Last success</span><b>{dateText(source.last_success_at_utc)}</b></div><div><span>Input</span><b>{source.input_event_count}</b></div><div><span>Accepted</span><b>{source.accepted_event_count}</b></div><div><span>Duplicates</span><b>{source.duplicate_event_count}</b></div><div><span>Rejected</span><b>{source.rejected_record_count}</b></div>{source.error_code && <div><span>Error category</span><b>{source.error_code}</b></div>}</div> : <Unavailable text={snapshot.errors.source ?? "No source status has been recorded."}/>}</Panel></div>;
}

function StatusRow({ label, state, ok }: { label: string; state: string; ok: boolean }) { return <div className="ops-status-row"><span className={ok ? "status-pip status-ok" : "status-pip"}/><span>{label}</span><b>{state}</b></div>; }
function EmptyState({ title, text }: { title: string; text: string }) { return <div className="ops-empty"><span aria-hidden="true">◌</span><h3>{title}</h3><p>{text}</p></div>; }
function Unavailable({ text }: { text: string }) { return <p className="ops-unavailable" role="status"><span aria-hidden="true">!</span>{text}</p>; }
