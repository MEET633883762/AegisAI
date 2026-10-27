import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent, type ReactNode } from "react";
import { getLocalApi, postLocalApi, LocalApiError, type ApiRoute } from "./api";
import { downloadExecutiveReport } from "./executiveReportExport";
import { Icon, type IconName } from "../icons";
import type { AssessmentResponse, DetectionEvaluationResponse, EvidenceResponse, ExecutiveReportResponse, FindingsResponse, HealthResponse, InvestigationCaseResponse, InvestigationCasesResponse, ProcessingResponse, PurpleScenarioRunsResponse, SourceResponse, TelemetryFinding } from "./types";

type View = "overview" | "findings" | "detection" | "scenarios" | "assessment" | "executive" | "investigations" | "health";
const NAV: { id: View; label: string; icon: IconName; description: string }[] = [
  { id: "overview", label: "Overview", icon: "monitor", description: "Your local evidence, findings, and processing activity in one place." },
  { id: "findings", label: "Findings", icon: "eye", description: "Follow each rule output back to the evidence that produced it." },
  { id: "detection", label: "Detection Lab", icon: "target", description: "Measure the detector against labeled synthetic scenarios and inspect its gaps." },
  { id: "scenarios", label: "Scenario Validation", icon: "play", description: "Review recorded, authorized exercises against the fixed local test site." },
  { id: "assessment", label: "Assessment", icon: "shield", description: "Inspect observed website controls, inferred risks, and changes between runs." },
  { id: "executive", label: "Executive Reports", icon: "code", description: "Turn linked observations into a clear, downloadable incident review." },
  { id: "investigations", label: "Cases", icon: "database", description: "Connect findings, verified evidence, and clearly attributed analyst notes." },
  { id: "health", label: "System Health", icon: "server", description: "Check the local service, processing runs, and source availability." },
];
const SEVERITIES = ["critical", "high", "medium", "low"] as const;
const dateText = (value?: string | null) => value ? new Date(value).toLocaleString() : "Not recorded";
const viewFromHash = (): View | undefined => window.location.hash === "" ? "overview" : NAV.find((item) => `#${item.id}` === window.location.hash)?.id;

type Snapshot = {
  health: HealthResponse | null;
  findings: TelemetryFinding[] | null;
  processing: ProcessingResponse | null;
  source: SourceResponse | null;
  assessment: AssessmentResponse | null;
  evaluation: DetectionEvaluationResponse | null;
  executive: ExecutiveReportResponse | null;
  investigations: InvestigationCasesResponse | null;
  scenarios: PurpleScenarioRunsResponse | null;
  assessmentMissing: boolean;
  errors: Partial<Record<"health" | "findings" | "processing" | "source" | "assessment" | "evaluation" | "executive" | "investigations" | "scenarios", string>>;
  loadedAt: number;
};

const emptySnapshot = (): Snapshot => ({ health: null, findings: null, processing: null, source: null, assessment: null, evaluation: null, executive: null, investigations: null, scenarios: null, assessmentMissing: false, errors: {}, loadedAt: 0 });

export function LocalDashboard() {
  const [view, setView] = useState<View>(() => viewFromHash() ?? "overview");
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
  const [selectedCaseId, setSelectedCaseId] = useState("");
  const [caseDetail, setCaseDetail] = useState<InvestigationCaseResponse | null>(null);
  const [caseTitle, setCaseTitle] = useState("");
  const [caseNote, setCaseNote] = useState("");
  const [caseNoteClass, setCaseNoteClass] = useState<"analyst_conclusion" | "unresolved_hypothesis">("unresolved_hypothesis");
  const [caseFindingId, setCaseFindingId] = useState("");
  const [caseRationale, setCaseRationale] = useState("");
  const [caseError, setCaseError] = useState("");
  const [caseBusy, setCaseBusy] = useState(false);
  const refreshGeneration = useRef(0);
  const navigationFocus = useRef(false);

  const navigate = useCallback((next: View) => {
    if (window.location.hash !== `#${next}`) window.history.pushState(null, "", `#${next}`);
    navigationFocus.current = true;
    setView(next);
  }, []);

  useEffect(() => {
    const syncView = () => {
      const next = viewFromHash();
      if (next) { navigationFocus.current = true; setView(next); }
    };
    window.addEventListener("popstate", syncView);
    window.addEventListener("hashchange", syncView);
    return () => {
      window.removeEventListener("popstate", syncView);
      window.removeEventListener("hashchange", syncView);
    };
  }, []);

  useEffect(() => {
    if (!navigationFocus.current) return;
    document.getElementById("ops-view-title")?.focus({ preventScroll: true });
    navigationFocus.current = false;
  }, [view]);

  const refresh = useCallback(async (activeToken: string) => {
    const generation = ++refreshGeneration.current;
    setLoading(true);
    setRefreshError("");
    const read = async <T,>(name: "health" | "findings" | "processing" | "source" | "assessment" | "evaluation" | "executive" | "investigations" | "scenarios", route: ApiRoute) => {
      try { return { name, value: await getLocalApi<T>(route, activeToken), error: "", status: null as number | null }; }
      catch (error) {
        const safe = error instanceof LocalApiError ? error.message : "The local API request failed.";
        return { name, value: null, error: safe, status: error instanceof LocalApiError ? error.status : null };
      }
    };
    const results = await Promise.all([
      read<HealthResponse>("health", "/health"),
      read<FindingsResponse>("findings", "/api/telemetry/findings"),
      read<ProcessingResponse>("processing", "/api/processing"),
      read<SourceResponse>("source", "/api/telemetry/sources/live-website/status"),
      read<AssessmentResponse>("assessment", "/api/assessment/reports/latest"),
      read<DetectionEvaluationResponse>("evaluation", "/api/evaluation/reports/latest"),
      read<ExecutiveReportResponse>("executive", "/api/reports/executive/latest"),
      read<InvestigationCasesResponse>("investigations", "/api/investigations/cases"),
      read<PurpleScenarioRunsResponse>("scenarios", "/api/purple-team/scenarios/runs"),
    ]);
    if (generation !== refreshGeneration.current) return;
    setSnapshot((previous) => {
      const next: Snapshot = { ...emptySnapshot(), loadedAt: results.some((item) => !item.error) ? Date.now() : previous.loadedAt };
      for (const result of results) {
        if (result.name === "health") next.health = result.value as HealthResponse | null ?? previous.health;
        if (result.name === "findings") next.findings = result.value ? (result.value as FindingsResponse).findings : previous.findings;
        if (result.name === "processing") next.processing = result.value as ProcessingResponse | null ?? previous.processing;
        if (result.name === "source") next.source = result.value as SourceResponse | null ?? previous.source;
        if (result.name === "assessment") {
          if (result.value) {
            next.assessment = result.value as AssessmentResponse;
            next.assessmentMissing = next.assessment.report === null;
          } else next.assessment = previous.assessment;
        }
        if (result.name === "evaluation") next.evaluation = result.value as DetectionEvaluationResponse | null ?? previous.evaluation;
        if (result.name === "executive") next.executive = result.value as ExecutiveReportResponse | null ?? previous.executive;
        if (result.name === "investigations") next.investigations = result.value as InvestigationCasesResponse | null ?? previous.investigations;
        if (result.name === "scenarios") next.scenarios = result.value as PurpleScenarioRunsResponse | null ?? previous.scenarios;
        if (result.error) next.errors[result.name] = result.error;
      }
      return next;
    });
    const requiredViews = results.filter((item) => item.name !== "source" && item.name !== "assessment" && item.name !== "investigations" && item.name !== "scenarios");
    const failedRequiredCount = requiredViews.filter((item) => item.error).length;
    setRefreshError(failedRequiredCount === requiredViews.length
      ? "The local API could not refresh any view. Previously loaded values are retained and may be stale."
      : failedRequiredCount ? "Some local API views could not refresh. Previously loaded values for those views are retained and may be stale." : "");
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

  const loadCaseDetail = useCallback(async (caseId: string, activeToken = token) => {
    if (!caseId || !activeToken) { setCaseDetail(null); return; }
    setCaseError("");
    try {
      const result = await getLocalApi<InvestigationCaseResponse>(
        `/api/investigations/cases/${encodeURIComponent(caseId)}` as ApiRoute, activeToken,
      );
      setCaseDetail(result);
    } catch (error) {
      setCaseError(error instanceof LocalApiError ? error.message : "Investigation details are unavailable.");
    }
  }, [token]);

  useEffect(() => {
    if (!token || view !== "investigations") return;
    if (selectedCaseId) void loadCaseDetail(selectedCaseId);
    else setCaseDetail(null);
  }, [token, view, selectedCaseId, loadCaseDetail]);

  async function runCaseAction(path: string, data: Record<string, unknown>) {
    if (!token) return;
    setCaseBusy(true); setCaseError("");
    try {
      await postLocalApi<Record<string, unknown>>(path as ApiRoute, token, data);
      await refresh(token);
      if (selectedCaseId) await loadCaseDetail(selectedCaseId);
    } catch (error) {
      setCaseError(error instanceof LocalApiError ? error.message : "The case update could not be completed.");
    } finally { setCaseBusy(false); }
  }

  async function createCase(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token || !caseTitle.trim()) return;
    setCaseBusy(true); setCaseError("");
    try {
      const result = await postLocalApi<{ case_id: string }>("/api/investigations/cases", token, { title: caseTitle.trim() });
      setCaseTitle(""); setSelectedCaseId(result.case_id);
      await refresh(token);
      await loadCaseDetail(result.case_id);
    } catch (error) {
      setCaseError(error instanceof LocalApiError ? error.message : "The case could not be created.");
    } finally { setCaseBusy(false); }
  }

  function disconnect() {
    refreshGeneration.current += 1;
    setLoading(false);
    setRefreshError(""); setEvidenceError(""); setCaseError("");
    setToken(""); setTokenInput(""); setSnapshot(emptySnapshot()); setSelectedId(""); setEvidence(null);
    setSelectedCaseId(""); setCaseDetail(null); setCaseNote(""); setCaseTitle("");
  }

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
  const currentView = NAV.find((item) => item.id === view)!;

  function clearFilters() {
    setSearch(""); setSeverity("all"); setTypeFilter("all"); setStatus("all");
  }

  function openFinding(id: string) {
    clearFilters();
    setSelectedId(id);
    navigate("findings");
  }

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

  return <div className="local-ops">
    <a className="ops-skip" href="#ops-main">Skip to dashboard content</a>
    <header className="ops-topbar"><a className="ops-brand" href="index.html" aria-label="AegisAI public site"><span className="ops-logo"><Icon name="shield" /></span><span>Aegis<span>AI</span><small>LOCAL OPERATIONS</small></span></a>
      <span className="ops-top-context">Research workspace <span>/</span> Operations</span>
      <div className="ops-top-actions"><span className="ops-loopback"><Icon name="lock" /> LOOPBACK ONLY</span>{token ? <button type="button" className="ops-quiet-button" onClick={disconnect}>Disconnect</button> : <span className="ops-lock">Session disconnected</span>}</div>
    </header>
    <div className="ops-layout">
      <aside className="ops-sidebar"><div className="ops-side-label">RESEARCH WORKSPACE</div><nav aria-label="Dashboard sections">{NAV.map((item) => <button key={item.id} type="button" className={view === item.id ? "ops-nav-active" : ""} aria-current={view === item.id ? "page" : undefined} onClick={() => navigate(item.id)}><Icon name={item.icon} />{item.label}{item.id === "findings" && snapshot.findings && <b aria-hidden="true">{findings.length}</b>}</button>)}</nav>
        <section className="ops-connection"><div className="ops-side-label">SESSION</div>{token ? <><div className="ops-connected"><i /> Local token loaded</div><p>Held only in page memory. Use Refresh to request the latest available snapshot.</p></> : <><div className="ops-disconnected"><Icon name="lock" /> Awaiting connection</div><p>Use the connection panel to open this computer's synthetic research data.</p></>}</section>
        <a className="ops-public-link" href="dashboard.html"><Icon name="play" /><span>Present the public demo<small>No local API required</small></span><span aria-hidden="true">↗</span></a>
        <div className="ops-side-foot"><span className="ops-mini-logo"><Icon name="shield" /></span><span>Synthetic research lab<br/><b>Evidence before conclusions</b></span></div>
      </aside>
      <main id="ops-main" className="ops-main">
        <div className="ops-page-heading"><div><div className="ops-eyebrow">LOCAL OPERATIONS <span>/ {currentView.label}</span></div><h1 id="ops-view-title" tabIndex={-1}>{view === "overview" ? "Security command center" : currentView.label}</h1><p>{currentView.description}</p></div><div className="ops-heading-controls">{snapshot.loadedAt > 0 && <span className="ops-updated">Updated {dateText(new Date(snapshot.loadedAt).toISOString())}</span>}<button type="button" className="ops-refresh" disabled={!token || loading} onClick={() => token && void refresh(token)}><span aria-hidden="true">↻</span> {loading ? "Refreshing…" : "Refresh"}</button></div></div>
        <div className="ops-disclosure" role="note"><span className="ops-disclosure-icon" aria-hidden="true">i</span><p><strong>Synthetic local prototype.</strong> Findings and activity shown here come from synthetic fixtures or the harmless local demo site. This is not a production SOC or evidence of real-world attack detection. Telemetry views are read only; optional case notes and associations require an explicitly scoped local analyst token.</p></div>
        {!token && <section className="ops-welcome" aria-labelledby="ops-connect-title"><div className="ops-welcome-copy"><span className="ops-welcome-icon"><Icon name="lock" /></span><span className="ops-eyebrow">YOUR PRIVATE RESEARCH SESSION</span><h2 id="ops-connect-title">Connect to view local data</h2><p>Open the synthetic service on this computer to inspect findings, trace evidence, and review detector performance.</p><div className="ops-start-command"><span>01 / Start with Python 3.11 (Windows)</span><code>py -3.11 scripts/run_private_api.py</code></div><a href="dashboard.html">Just presenting? Open the guided public demo <span aria-hidden="true">↗</span></a></div><form className="ops-connect-form" onSubmit={connect}><span className="ops-eyebrow">02 / OPEN YOUR SESSION</span><h3>A local connection.<br/>Your evidence stays here.</h3><label htmlFor="ops-token">Startup bearer token</label><input id="ops-token" type="password" autoComplete="off" spellCheck={false} value={tokenInput} onChange={(event) => setTokenInput(event.currentTarget.value)} placeholder="Paste token from API startup"/><button className="ops-connect-button" type="submit" disabled={!tokenInput.trim()}>Connect <Icon name="arrow" /></button><small><Icon name="lock" /> Held only in page memory. Never saved.</small></form></section>}
        {refreshError && <p className="ops-error-banner" role="alert">{refreshError}</p>}
        {view === "overview" && <Overview findings={findings} totals={totals} snapshot={snapshot} connected={Boolean(token)} onOpenFindings={() => navigate("findings")} onSelect={openFinding} />}
        {view === "findings" && <FindingsView findings={filtered} available={snapshot.findings !== null} unavailableMessage={snapshot.errors.findings ?? "Findings are not available."} types={Array.from(new Set(findings.map((item) => item.rule_id))).sort()} total={findings.length} selected={selected} evidence={evidence} evidenceError={evidenceError} connected={Boolean(token)} search={search} setSearch={setSearch} severity={severity} setSeverity={setSeverity} typeFilter={typeFilter} setTypeFilter={setTypeFilter} status={status} setStatus={setStatus} onSelect={setSelectedId} onClearFilters={clearFilters} />}
        {view === "detection" && <DetectionView snapshot={snapshot} connected={Boolean(token)} loading={loading} />}
        {view === "scenarios" && <ScenarioValidationView response={snapshot.scenarios} connected={Boolean(token)} loading={loading} unavailable={snapshot.errors.scenarios} />}
        {view === "assessment" && <AssessmentView snapshot={snapshot} connected={Boolean(token)} loading={loading} />}
        {view === "executive" && <ExecutiveReportView response={snapshot.executive} connected={Boolean(token)} loading={loading} unavailable={snapshot.errors.executive} />}
        {view === "investigations" && <InvestigationsView
          connected={Boolean(token)} cases={snapshot.investigations?.cases ?? []} findings={findings}
          assessment={snapshot.assessment?.report ?? null} evaluationRun={snapshot.evaluation?.report.history[0] ?? null}
          selectedCaseId={selectedCaseId} detail={caseDetail} error={caseError || snapshot.errors.investigations || ""} busy={caseBusy}
          title={caseTitle} setTitle={setCaseTitle} note={caseNote} setNote={setCaseNote}
          noteClass={caseNoteClass} setNoteClass={setCaseNoteClass} findingId={caseFindingId}
          setFindingId={setCaseFindingId} rationale={caseRationale} setRationale={setCaseRationale}
          onSelect={setSelectedCaseId} onCreate={createCase}
          onNote={() => runCaseAction(`/api/investigations/cases/${selectedCaseId}/notes`, { classification: caseNoteClass, text: caseNote })}
          onLinkFinding={() => runCaseAction(`/api/investigations/cases/${selectedCaseId}/findings`, {
            finding_id: caseFindingId, relationship: "inferred_relationship", rationale: caseRationale,
          })}
          onLinkEvidence={(evidenceRef) => runCaseAction(`/api/investigations/cases/${selectedCaseId}/evidence`, {
            finding_id: caseFindingId, evidence_ref: evidenceRef, rationale: caseRationale,
          })}
          onStatus={(nextStatus) => runCaseAction(`/api/investigations/cases/${selectedCaseId}/status`, { status: nextStatus })}
          onContext={(sourceType, sourceId) => runCaseAction(`/api/investigations/cases/${selectedCaseId}/context`, {
            source_type: sourceType, source_id: sourceId,
          })}
        />}
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
  const count = (value: number | null | undefined) => value == null ? "—" : value;
  return <>
    <div className="ops-section-title"><div><span className="ops-eyebrow">CURRENT SNAPSHOT</span><h2>Security overview</h2></div><span className="ops-synthetic-tag"><i /> Synthetic data</span></div>
    {snapshot.errors.source && <Unavailable text="Live website source status could not refresh. Source counters below may be stale." />}
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

function FindingsView({ findings, available, unavailableMessage, types, total, selected, evidence, evidenceError, connected, search, setSearch, severity, setSeverity, typeFilter, setTypeFilter, status, setStatus, onSelect, onClearFilters }: {
  findings: TelemetryFinding[]; available: boolean; unavailableMessage: string; types: string[]; total: number; selected: TelemetryFinding | null; evidence: EvidenceResponse | null; evidenceError: string; connected: boolean; search: string; setSearch: (v: string) => void; severity: string; setSeverity: (v: string) => void; typeFilter: string; setTypeFilter: (v: string) => void; status: string; setStatus: (v: string) => void; onSelect: (id: string) => void; onClearFilters: () => void;
}) {
  const filtered = Boolean(search.trim() || severity !== "all" || typeFilter !== "all" || status !== "all");
  return <div className="ops-investigation"><Panel title="Finding queue" kicker="SYNTHETIC TELEMETRY" action={<span className="ops-panel-count">{!connected ? "Not connected" : !available ? "Unavailable" : `${findings.length} of ${total}`}</span>}>
    <div className="ops-filters"><label className="ops-search">Search findings<input type="search" value={search} onChange={(e) => setSearch(e.currentTarget.value)} placeholder="ID, rule, asset, text"/></label><label>Severity<select value={severity} onChange={(e) => setSeverity(e.currentTarget.value)}><option value="all">All severities</option>{SEVERITIES.map((value) => <option key={value}>{value}</option>)}</select></label><label>Type<select value={typeFilter} onChange={(e) => setTypeFilter(e.currentTarget.value)}><option value="all">All rule types</option>{types.map((value) => <option key={value}>{value}</option>)}</select></label><label>Status<select value={status} onChange={(e) => setStatus(e.currentTarget.value)}><option value="all">All statuses</option><option value="open">open</option><option value="acknowledged">acknowledged</option><option value="closed">closed</option></select></label></div>
    {connected && available && <div className="ops-filter-summary"><span role="status" aria-live="polite">Showing {findings.length} of {total} findings</span>{filtered && <button type="button" onClick={onClearFilters}>Clear filters <span aria-hidden="true">×</span></button>}</div>}
    {!connected ? <EmptyState title="Connect to investigate" text="The list is populated from the authenticated local telemetry findings endpoint."/> : !available ? <Unavailable text={unavailableMessage}/> : findings.length === 0 ? <EmptyState title={total === 0 ? "No findings yet" : "No matching findings"} text={total === 0 ? "The local API returned no synthetic findings for this tenant. Refresh after a processing run to check for new results." : "No findings match the current search and filters. Clear filters to return to the full queue."}/> : <div className="ops-table-wrap"><table className="ops-findings-table"><thead><tr><th>Finding</th><th>Severity</th><th>Confidence</th><th>Last seen</th><th>Status</th></tr></thead><tbody>{findings.map((item) => <tr key={item.finding_id} className={selected?.finding_id === item.finding_id ? "selected-row" : ""}><td><button type="button" className="finding-select" aria-pressed={selected?.finding_id === item.finding_id} onClick={() => onSelect(item.finding_id)}><b>{item.rule_id}</b><small>{item.finding_id} · {item.asset_ref}</small></button></td><td><span className={`ops-severity-pill severity-pill-${item.severity}`}>{item.severity}</span></td><td>{Math.round(item.confidence * 100)}%</td><td>{dateText(item.last_seen_utc)}</td><td>{item.status}</td></tr>)}</tbody></table></div>}
    </Panel>
    {selected && <Panel title="Investigation detail" kicker={selected.finding_id}>{!findings.some((item) => item.finding_id === selected.finding_id) && <p className="ops-selected-filter-note">This selected finding is outside the current filters. <button type="button" onClick={onClearFilters}>Show selected finding</button></p>}<div className="ops-detail-summary"><span className={`ops-severity-pill severity-pill-${selected.severity}`}>{selected.severity}</span><span>Confidence {Math.round(selected.confidence * 100)}%</span><span>Rule {selected.rule_id} v{selected.rule_version}</span></div><p className="ops-explanation">{selected.explanation}</p><dl className="ops-detail-grid"><dt>Asset</dt><dd>{selected.asset_ref}</dd><dt>First seen</dt><dd>{dateText(selected.first_seen_utc)}</dd><dt>Last seen</dt><dd>{dateText(selected.last_seen_utc)}</dd><dt>Finding status</dt><dd>{selected.status}</dd><dt>Event IDs</dt><dd>{selected.event_ids.join(", ")}</dd></dl><h3 className="ops-subheading">Evidence references</h3>
      {evidenceError ? <Unavailable text={evidenceError}/> : !evidence ? <p className="ops-muted">Loading evidence from the tenant-scoped API…</p> : evidence.evidence.length === 0 ? <p className="ops-muted">No evidence records were returned.</p> : <ul className="ops-evidence-list">{evidence.evidence.map((item) => <li key={item.evidence_ref}><b>{item.evidence_ref}</b><span>{item.event_type} · {dateText(item.occurred_at_utc)}</span><small>Actor {item.actor_ref} · Source {item.source_ref} · Asset {item.asset_ref}</small></li>)}</ul>}
      <h3 className="ops-subheading">Confidence factors</h3><ul className="ops-factor-list">{selected.confidence_factors.map((factor) => <li key={factor}>{factor}</li>)}</ul><p className="ops-panel-footnote">Investigation is observational only. This dashboard has no acknowledge, close, or response controls.</p></Panel>}
  </div>;
}

function DetectionView({ snapshot, connected, loading }: { snapshot: Snapshot; connected: boolean; loading: boolean }) {
  const response = snapshot.evaluation;
  const report = response?.report;
  const counts = report?.counts;
  const metricCards = counts ? [
    ["True positives", counts.true_positives], ["True negatives", counts.true_negatives],
    ["False positives", counts.false_positives], ["False negatives", counts.false_negatives],
    ["Total evaluated pairs", report.total_evaluated_pairs],
  ] as const : [];
  return <div className="ops-detection-grid"><Panel title="Detection evaluation" kicker="PHASE 6B BENCHMARK">
    {!connected ? <EmptyState title="Connect to view evaluation" text="The synthetic benchmark summary is served by the authenticated local API." />
      : loading && !report ? <p className="ops-muted" role="status">Loading the synthetic evaluation report…</p>
        : !report ? <Unavailable text={snapshot.errors.evaluation ?? "The synthetic evaluation report is unavailable."} />
          : <>
            {snapshot.errors.evaluation && <p className="ops-unavailable" role="status">Showing previously loaded evaluation data; this view may be stale. {snapshot.errors.evaluation}</p>}
            <p className="ops-synthetic-tag"><i />{response.label}</p>
            <p className="ops-body-copy">Synthetic evaluation only. These results do not measure real-world detection accuracy, establish compromise, or validate a live security control.</p>
            <div className="ops-assessment-meta"><span>Dataset {report.dataset_id} v{report.dataset_version}</span><span>{report.valid_scenario_count} accepted scenarios</span><span>{report.rejected_scenario_count} rejected scenarios (excluded)</span><span>{report.total_evaluated_pairs} evaluated pairs</span><span>Rule catalog v{report.rule_catalog_version}; detector rules v{report.detector_rule_version}</span></div>
            <p className="ops-panel-footnote">Dataset SHA-256: {report.dataset_sha256}<br/>Detector configuration SHA-256: {report.detector_config_sha256}<br/>Scenario-rule mapping v{report.scenario_rule_mapping_version}; ATT&amp;CK mapping v{report.attack_mapping_catalog_version}<br/>Counting unit: {report.counting_unit}</p>
            <div className="ops-metric-grid">{metricCards.map(([label, value]) => <MetricCard key={label} label={label} value={value} note="Phase 6B synthetic benchmark" />)}</div>
            <h3 className="ops-subheading">Aggregate metrics</h3>
            <div className="ops-assessment-meta">{(["precision", "recall", "specificity", "f1"] as const).map((key) => {
              const metric = report.metrics[key];
              return <span key={key}>{key[0].toUpperCase() + key.slice(1)}: {metric.value === null ? `Unavailable (${metric.denominator} denominator)` : `${(metric.value * 100).toFixed(1)}% (${metric.denominator})`}</span>;
            })}</div>
            <h3 className="ops-subheading">Results by supported rule</h3>
            <div className="ops-table-wrap"><table className="ops-findings-table"><thead><tr><th>Rule</th><th>TP</th><th>TN</th><th>FP</th><th>FN</th><th>Precision</th><th>Recall</th><th>Specificity</th><th>F1</th></tr></thead><tbody>{report.per_rule.map((item) => <tr key={item.rule_id}><td>{item.rule_id}</td><td>{item.counts.true_positives}</td><td>{item.counts.true_negatives}</td><td>{item.counts.false_positives}</td><td>{item.counts.false_negatives}</td>{(["precision", "recall", "specificity", "f1"] as const).map((key) => <td key={key}>{item.metrics[key].value === null ? `N/A (denom ${item.metrics[key].denominator})` : `${(item.metrics[key].value! * 100).toFixed(1)}% (${item.metrics[key].denominator})`}</td>)}</tr>)}</tbody></table></div>
            <h3 className="ops-subheading">Scenario coverage and rule mapping</h3>
            <p className="ops-panel-footnote">Each accepted scenario is evaluated against every supported rule. Rejected inputs are shown separately and do not enter metric denominators.</p>
            <div className="ops-table-wrap"><table className="ops-findings-table"><thead><tr><th>Scenario</th><th>Status</th><th>Expected rules</th><th>Observed rules</th><th>ATT&amp;CK mapping</th></tr></thead><tbody>{report.scenario_rule_mapping.map((item) => <tr key={item.scenario_id}><td>{item.scenario_id}</td><td>{item.status}</td><td>{item.expected_rule_ids.join(", ") || "None"}</td><td>{item.observed_rule_ids.join(", ") || "None"}</td><td>{item.technique_ids.join(", ") || "Not mapped"}</td></tr>)}</tbody></table></div>
            <h3 className="ops-subheading">ATT&amp;CK coverage and gaps</h3>
            {report.technique_coverage.length ? <ul className="ops-factor-list">{report.technique_coverage.map((item) => <li key={item.technique_id}>{item.technique_id} {item.name}: covered by {item.scenario_ids.length} labeled scenario(s); {item.scope_note}</li>)}</ul> : <p className="ops-muted">No ATT&amp;CK technique is directly mapped by this dataset.</p>}
            {report.untested_techniques.map((item) => <p className="ops-panel-footnote" key={item.technique_id}>Untested candidate {item.technique_id} {item.name}: {item.rationale}</p>)}
            {report.coverage_status !== "complete" && <p className="ops-unavailable" role="status">Coverage is {report.coverage_status}; untested areas remain.</p>}
            <h3 className="ops-subheading">Evaluation history</h3>
            {report.history.length ? <div className="ops-table-wrap"><table className="ops-findings-table"><thead><tr><th>Run / report SHA-256</th><th>Generated</th><th>Pairs</th><th>TP / TN / FP / FN</th><th>Comparison to prior run</th></tr></thead><tbody>{report.history.map((run) => <tr key={run.run_id}><td>{run.run_id}<small className="ops-assessment-subline">{run.report_sha256}</small></td><td>{dateText(run.generated_at_utc)}</td><td>{run.total_evaluated_pairs}</td><td>{run.counts.true_positives} / {run.counts.true_negatives} / {run.counts.false_positives} / {run.counts.false_negatives}</td><td>{run.comparison ? <>Newly failing: {run.comparison.newly_failing_scenario_ids.join(", ") || "none"}<br/>Resolved: {run.comparison.resolved_scenario_ids.join(", ") || "none"}</> : "Baseline"}</td></tr>)}</tbody></table></div> : <p className="ops-muted">No historical runs recorded. An operator can record bounded history with the local evaluation CLI.</p>}
            {report.warnings.map((warning) => <p className="ops-unavailable" key={warning}>{warning}</p>)}
            <h3 className="ops-subheading">Benchmark limitations</h3><ul className="ops-factor-list">{report.limitations.map((item, index) => <li key={`${index}-${item}`}>{item}</li>)}</ul>
          </>}
  </Panel><Panel title="What the benchmark measures" kicker="INTERPRETATION"><p className="ops-body-copy">Phase 6B compares expected and observed rule types for accepted synthetic scenario × supported-rule pairs. Invalid inputs are reported separately and excluded from confusion counts. Nullable metrics remain undefined when their denominator is zero.</p><p className="ops-panel-footnote">This benchmark is a deterministic regression/evaluation artifact, not evidence of operational performance.</p></Panel></div>;
}

function AssessmentView({ snapshot, connected, loading }: { snapshot: Snapshot; connected: boolean; loading: boolean }) {
  const response = snapshot.assessment;
  const report = response?.report;
  const observations = report?.raw_observations ?? [];
  return <div className="ops-assessment-grid">
    <Panel title="Local website assessment" kicker="FIXED LOOPBACK CHECKS">
      {!connected ? <EmptyState title="Connect to view assessment" text="Assessment reports are read from the authenticated, tenant-scoped local API." />
        : loading && !report ? <p className="ops-muted" role="status">Loading the latest local assessment…</p>
          : !report && snapshot.errors.assessment ? <Unavailable text={snapshot.errors.assessment} />
            : !report ? <EmptyState title={snapshot.assessmentMissing ? "No assessment report yet" : "Assessment unavailable"} text="Run the fixed local assessment command, then refresh. No target or path can be entered here." />
              : <>
                {snapshot.errors.assessment && <p className="ops-unavailable" role="status">Showing previously loaded assessment data; this view may be stale. {snapshot.errors.assessment}</p>}
                <div className="ops-assessment-meta"><span className="ops-synthetic-tag"><i />{report.label}</span><span>Report {report.report_id}</span><span>Generated {dateText(report.generated_at_utc)}</span><span>{report.duplicate_observation_count} duplicate observation(s) collapsed</span>{report.schema_version === "2.0" && <span>Catalog {report.check_catalog_version} · Config {report.configuration_version}</span>}</div>
                <p className="ops-assessment-target">Approved target: <code>http://127.0.0.1:8767</code> · fixed by local policy</p>
                <h3 className="ops-subheading">Checks and observations</h3>
                {observations.length === 0 ? <p className="ops-muted">No check observations were recorded.</p> : <div className="ops-table-wrap"><table className="ops-findings-table ops-assessment-table"><thead><tr><th>Check</th><th>Controller decision</th><th>Result</th><th>Time</th><th>Evidence</th></tr></thead><tbody>{observations.map((item, index) => <tr key={`${item.check_id}-${item.evidence?.evidence_ref ?? index}`}>
                  <td><b>{item.check_id}</b><small className="ops-assessment-subline">{item.category} · severity {item.severity} · v{item.check_version}</small><small className="ops-assessment-subline">{item.description}</small></td><td>{item.decision.allowed ? "Allowed" : "Denied"} · {item.decision.reason_code}</td>
                  <td><b>{item.outcome_status ?? item.outcome}</b><small className="ops-assessment-subline">Expected: {item.expected_result}</small><small className="ops-assessment-subline">Observed: {item.observed_result}</small>{item.error_category && <small className="ops-assessment-subline">{item.error_category}</small>}
                    {Object.entries(item.facts).map(([key, value]) => <small className="ops-assessment-subline" key={key}>{key}: {value === null ? "not observed" : String(value)}</small>)}</td>
                  <td>{dateText(item.observed_at_utc ?? item.evidence?.observed_at_utc)}</td><td>{item.evidence ? <><b>{item.evidence.evidence_ref}</b><small className="ops-assessment-subline">{item.evidence.request_method} {item.evidence.request_path} · HTTP {item.evidence.response_status} · {item.evidence.response_bytes} bytes · SHA-256 {item.evidence.response_sha256}</small></> : "No response evidence"}</td>
                </tr>)}</tbody></table></div>}
                <h3 className="ops-subheading">Inferred risks</h3>
                {report.inferred_risks.length ? <ul className="ops-assessment-issues">{report.inferred_risks.map((issue) => <li key={issue.issue_id}><b>{issue.title}</b><span>{issue.rationale}</span><small>{issue.check_id} · {issue.severity} · Evidence: {issue.evidence_refs.join(", ")}</small><small>Recommended manual review: {issue.recommendation}</small></li>)}</ul> : <p className="ops-muted">No inferred risks were recorded.</p>}
                <h3 className="ops-subheading">Confirmed findings</h3>
                {report.confirmed_findings.length ? <ul className="ops-assessment-issues">{report.confirmed_findings.map((issue) => <li key={issue.issue_id}><b>{issue.title}</b><span>{issue.rationale}</span><small>{issue.check_id} · Evidence: {issue.evidence_refs.join(", ")}</small></li>)}</ul> : <p className="ops-muted">None. These configuration observations do not establish a confirmed vulnerability.</p>}
                {report.comparison && <><h3 className="ops-subheading">Run comparison</h3><p className="ops-muted">{report.comparison.status === "baseline" ? "No prior valid report was available as a comparison baseline." : `Compared with ${report.comparison.previous_report_id}.`}</p>{report.comparison.status === "compared" && <ul className="ops-factor-list"><li>{report.comparison.newly_introduced.length} newly introduced inferred risk(s)</li><li>{report.comparison.resolved.length} resolved inferred risk(s)</li><li>{report.comparison.unchanged.length} unchanged inferred risk(s)</li></ul>}</>}
                <h3 className="ops-subheading">Limitations</h3><ul className="ops-factor-list">{report.limitations.map((item) => <li key={item}>{item}</li>)}</ul>
              </>}
    </Panel>
    <Panel title="Assessment history" kicker="RECENT RUNS">
      {!connected ? <EmptyState title="Connect to view history" text="History is available from the authenticated local API." />
        : loading && !response ? <p className="ops-muted" role="status">Loading assessment history…</p>
        : snapshot.errors.assessment && !response ? <Unavailable text={snapshot.errors.assessment} />
          : !response?.history.length ? <EmptyState title="No assessment history" text="Stored assessment summaries will appear here after local runs." />
            : <><p className="ops-panel-footnote">Showing at most 20 retained summaries. Counts are derived from tenant-scoped synthetic reports.</p>
              <div className="ops-table-wrap"><table className="ops-findings-table"><thead><tr><th>Report</th><th>Generated</th><th>Inferred / confirmed</th><th>Change from prior</th></tr></thead><tbody>{response.history.map((item) => <tr key={item.report_id}><td>{item.report_id}</td><td>{dateText(item.generated_at_utc)}</td><td>{item.inferred_risk_count} / {item.confirmed_finding_count}</td><td>{item.comparison_status === "compared" ? `${item.newly_introduced_count} introduced; ${item.resolved_count} resolved` : "Baseline"}</td></tr>)}</tbody></table></div></>}
    </Panel>
  </div>;
}

function ScenarioValidationView({ response, connected, loading, unavailable }: {
  response: PurpleScenarioRunsResponse | null; connected: boolean; loading: boolean; unavailable?: string;
}) {
  if (!connected) return <Panel title="Scenario validation history" kicker="SYNTHETIC PURPLE TEAM"><EmptyState title="Connect to view scenario results" text="A reports:read token is required to read tenant-scoped local run history." /></Panel>;
  if (!response) return <Panel title="Scenario validation history" kicker="SYNTHETIC PURPLE TEAM">{unavailable ? <Unavailable text={unavailable} /> : <EmptyState title={loading ? "Loading scenario history" : "Scenario history unavailable"} text="Refresh to retrieve the bounded local run history." />}</Panel>;
  return <div className="ops-assessment-grid">
    {unavailable && <Unavailable text={`Showing previously loaded scenario data; it may be stale. ${unavailable}`} />}
    <Panel title="Scenario validation history" kicker="SYNTHETIC LOCAL RUNS">
      <p className="ops-executive-boundary">{response.label}. These fixed loopback scenarios show observed telemetry and rule output; a pass does not establish real-world control effectiveness.</p>
      {response.runs.length === 0 ? <EmptyState title="No scenario runs recorded" text="Run an approved scenario locally; this dashboard only reads reports and cannot start checks." />
        : <div className="ops-scenario-list">{response.runs.map((run) => <article className="ops-scenario-card" key={run.run_id}>
          <div className="ops-executive-risk-head"><div><b>{run.scenario_id} v{run.scenario_version}</b><small>{run.run_id}</small></div><span className="ops-severity-pill">{run.status}</span></div>
          <p className="ops-muted">Started {dateText(run.started_at_utc)} · completed {dateText(run.completed_at_utc)}</p>
          <div className="ops-health-facts"><div><span>Execution scope</span><b>{run.execution_scope} · {run.target_origin}</b></div><div><span>Policy decision</span><b>{run.policy_decision.allowed ? "Allowed" : "Denied"} · {run.policy_decision.reason_code} · max {run.policy_decision.maximum_requests} request(s)</b></div><div><span>Expected telemetry</span><b>{run.expected_count} × {run.expected_telemetry_type} / {run.expected_route_code} / HTTP {run.expected_status}</b></div><div><span>Observed</span><b>{run.observed_telemetry.length} event(s); HTTP {run.observed_http_statuses.join(", ") || "none"}</b></div><div><span>Expected rule(s)</span><b>{run.expected_detection_rule_ids.join(", ") || "No detection expected"}</b></div><div><span>Observed findings</span><b>{run.observed_findings.map((item) => `${item.rule_id} (${item.finding_id})`).join(", ") || "None"}</b></div>
            {run.error_category && <div><span>Error category</span><b>{run.error_category}</b></div>}{run.comparison.previous_run_id && <div><span>Previous run</span><b>{run.comparison.previous_status}; outcome {run.comparison.outcome_changed ? "changed" : "unchanged"}</b></div>}</div>
          {run.observed_telemetry.length > 0 && <><h3 className="ops-subheading">Evidence references</h3><ul className="ops-factor-list">{run.observed_telemetry.map((item) => <li key={item.evidence_ref}>{item.evidence_ref} · {item.event_type} · {item.route_code} · HTTP {item.status_code} · {dateText(item.occurred_at_utc)}</li>)}</ul></>}
          {run.observed_findings.length > 0 && <ul className="ops-factor-list">{run.observed_findings.map((item) => <li key={item.finding_id}>Finding {item.finding_id} ({item.rule_id}); evidence: {item.evidence_refs.join(", ") || "none linked"}</li>)}</ul>}
          <ul className="ops-factor-list">{run.limitations.map((item) => <li key={item}>{item}</li>)}</ul>
        </article>)}</div>}
    </Panel>
  </div>;
}

function ExecutiveReportView({ response, connected, loading, unavailable }: {
  response: ExecutiveReportResponse | null; connected: boolean; loading: boolean; unavailable?: string;
}) {
  const report = response?.report;
  const downloadAction = <button type="button" className="ops-refresh" disabled={!report} title={!report ? "Load a valid report before downloading." : "Download a self-contained HTML report."} onClick={() => report && downloadExecutiveReport(report)}>Download HTML report</button>;
  if (!connected) return <Panel title="Executive incident report" kicker="SYNTHETIC REPORT" action={downloadAction}><EmptyState title="Connect to view executive reports" text="A current local API token with reports:read permission is required."/><p className="ops-panel-footnote">Download disabled: no validated report is loaded.</p></Panel>;
  if (!report) return <Panel title="Executive incident report" kicker="SYNTHETIC REPORT" action={downloadAction}>{unavailable
    ? <Unavailable text={unavailable}/>
    : <EmptyState title={loading ? "Loading executive report" : "Executive report unavailable"} text={loading ? "Retrieving the tenant-scoped synthetic report." : "Refresh to request the latest report from the local API."}/>}<p className="ops-panel-footnote">Download disabled: no validated report is loaded.</p></Panel>;

  const risks = report.inferred_risks;
  const priorityOrder: Record<string, number> = { critical: 0, high: 1, medium: 2, low: 3 };
  const riskById = new Map(risks.map((risk) => [risk.finding_id, risk]));
  const prioritizedRecommendations = [...report.recommendations].sort((left, right) =>
    (priorityOrder[riskById.get(left.finding_id)?.severity ?? "low"] - priorityOrder[riskById.get(right.finding_id)?.severity ?? "low"])
    || left.finding_id.localeCompare(right.finding_id));
  return <div className="ops-executive-view">
    {unavailable && <Unavailable text={`The executive report could not refresh; the previously loaded report may be stale. ${unavailable}`}/>}
    <Panel title="Executive incident report" kicker="SYNTHETIC REPORT" action={downloadAction}>
      <div className="ops-executive-meta"><span className="ops-synthetic-tag"><i/> {report.label}</span><span>Generated {dateText(report.generated_at_utc)}</span><span>Report {report.report_id}</span></div>
      <p className="ops-executive-summary">{report.executive_summary}</p>
      <p className="ops-executive-boundary">Synthetic results do not establish real-world compromise, exploitability, or detection accuracy. Findings below are inferred risks for manual review; confirmed findings: {report.confirmed_findings.length}.</p>
    </Panel>
    <div className="ops-executive-counts">
      <Panel title={`Findings (${risks.length})`} kicker="BY SEVERITY"><div className="ops-executive-breakdown">{SEVERITIES.map((key) => <div key={key}><span className={`severity-dot severity-${key}`}/><span>{key}</span><b>{report.finding_counts.by_severity[key]}</b></div>)}</div></Panel>
      <Panel title="Finding status" kicker="BY STATUS"><div className="ops-executive-breakdown">{(["open", "acknowledged", "closed"] as const).map((key) => <div key={key}><span>{key}</span><b>{report.finding_counts.by_status[key]}</b></div>)}</div></Panel>
    </div>
    {risks.length === 0 ? <Panel title="No findings in this report" kicker="FINDINGS"><EmptyState title="No synthetic findings" text="The API returned a valid report with no inferred risks."/></Panel> : <Panel title="Inferred risks" kicker="MANUAL REVIEW"><div className="ops-executive-risks">{risks.map((risk) => <article className="ops-executive-risk" id={`executive-finding-${encodeURIComponent(risk.finding_id)}`} key={risk.finding_id}>
      <div className="ops-executive-risk-head"><div><b>{risk.rule_id}</b><small>{risk.finding_id} · {risk.asset_ref}</small></div><span className={`ops-severity-pill severity-pill-${risk.severity}`}>{risk.severity}</span></div>
      <div className="ops-detail-summary"><span>Inferred risk</span><span>{risk.status}</span><span>{Math.round(risk.confidence * 100)}% confidence</span></div>
      <p className="ops-explanation">{risk.explanation}</p>
      <dl className="ops-detail-grid"><dt>First seen</dt><dd>{dateText(risk.first_seen_utc)}</dd><dt>Last seen</dt><dd>{dateText(risk.last_seen_utc)}</dd></dl>
      <h3 className="ops-subheading">Evidence references</h3>
      <ul className="ops-executive-evidence-links">{risk.evidence_refs.map((ref) => <li key={ref}><a href={`#executive-evidence-${encodeURIComponent(ref)}`}>{ref}</a></li>)}</ul>
    </article>)}</div></Panel>}
    {report.timeline.length > 0 && <Panel title="Chronological timeline" kicker="LINKED EVIDENCE"><ol className="ops-executive-timeline">{report.timeline.map((entry, index) => <li key={`${entry.evidence_ref}-${index}`} id={`executive-evidence-${encodeURIComponent(entry.evidence_ref)}`}><time dateTime={entry.occurred_at_utc}>{dateText(entry.occurred_at_utc)}</time><span>{entry.event_type} · {entry.event_id}</span><small>Evidence: {entry.evidence_ref}</small><span>Findings: {entry.finding_ids.map((id, itemIndex) => <span key={id}>{itemIndex > 0 ? ", " : ""}<a href={`#executive-finding-${encodeURIComponent(id)}`}>{id}</a></span>)}</span></li>)}</ol></Panel>}
    {prioritizedRecommendations.length > 0 && <Panel title="Recommendations" kicker="MANUAL ACTIONS ONLY · PRIORITIZED BY FINDING SEVERITY"><ul className="ops-executive-recommendations">{prioritizedRecommendations.map((item, index) => <li key={`${item.finding_id}-${item.category}-${index}`}><b>{riskById.get(item.finding_id)?.severity ?? "Unranked"} priority · {item.category === "investigation" ? "Manual investigation" : "Manual remediation recommendation"}</b><span>{item.text}</span><small>Related finding: <a href={`#executive-finding-${encodeURIComponent(item.finding_id)}`}>{item.finding_id}</a></small></li>)}</ul><p className="ops-panel-footnote">Priority ordering is a display aid based only on the associated synthetic finding severity; it does not authorize or perform remediation.</p></Panel>}
    <Panel title="Limitations" kicker="INTERPRETATION"><ul className="ops-factor-list">{report.limitations.map((item, index) => <li key={`${index}-${item}`}>{item}</li>)}</ul></Panel>
  </div>;
}

function InvestigationsView(props: {
  connected: boolean; cases: InvestigationCasesResponse["cases"]; findings: TelemetryFinding[];
  assessment: AssessmentResponse["report"]; evaluationRun: DetectionEvaluationResponse["report"]["history"][number] | null;
  selectedCaseId: string; detail: InvestigationCaseResponse | null; error: string; busy: boolean;
  title: string; setTitle: (value: string) => void; note: string; setNote: (value: string) => void;
  noteClass: "analyst_conclusion" | "unresolved_hypothesis";
  setNoteClass: (value: "analyst_conclusion" | "unresolved_hypothesis") => void;
  findingId: string; setFindingId: (value: string) => void; rationale: string; setRationale: (value: string) => void;
  onSelect: (id: string) => void; onCreate: (event: FormEvent<HTMLFormElement>) => void;
  onNote: () => void; onLinkFinding: () => void; onLinkEvidence: (evidenceRef: string) => void;
  onStatus: (value: "open" | "under_review" | "closed") => void;
  onContext: (sourceType: "assessment_report" | "evaluation_run", sourceId: string) => void;
}) {
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [evidenceRef, setEvidenceRef] = useState("");
  const visibleCases = props.cases.filter((item) => (statusFilter === "all" || item.status === statusFilter)
    && `${item.case_id} ${item.title}`.toLowerCase().includes(query.toLowerCase()));
  const detail = props.detail?.case;
  return <div className="ops-investigation-grid">
    <Panel title="Investigation cases" kicker="HUMAN-LED · TENANT-SCOPED">
      <p className="ops-body-copy">A case organizes existing synthetic findings and evidence. Links can be inferred relationships; analyst notes remain conclusions or unresolved hypotheses.</p>
      {!props.connected ? <EmptyState title="Connect to view cases" text="Case data is available only through the authenticated local API." /> : <>
        {props.error && <p className="ops-error-banner" role="alert">{props.error}</p>}
        <form className="ops-case-create" onSubmit={props.onCreate}>
          <label>New case title<input maxLength={120} value={props.title} onChange={(event) => props.setTitle(event.currentTarget.value)} placeholder="e.g. Review repeated authentication signal" /></label>
          <button type="submit" disabled={props.busy || !props.title.trim()}>Create case</button>
        </form>
        <div className="ops-filters"><label className="ops-search">Search cases<input type="search" value={query} onChange={(event) => setQuery(event.currentTarget.value)} placeholder="Case ID or title" /></label>
          <label>Status<select value={statusFilter} onChange={(event) => setStatusFilter(event.currentTarget.value)}><option value="all">All statuses</option><option value="open">Open</option><option value="under_review">Under review</option><option value="closed">Closed</option></select></label></div>
        {visibleCases.length === 0 ? <EmptyState title="No matching cases" text="Create a case to organize tenant-scoped findings and evidence." />
          : <ul className="ops-case-list">{visibleCases.map((item) => <li key={item.case_id}><button type="button" className={props.selectedCaseId === item.case_id ? "selected-row" : ""} onClick={() => props.onSelect(item.case_id)}>
            <b>{item.title}</b><small>{item.case_id} · {item.status} · {item.finding_count} findings · {item.evidence_count} evidence refs</small></button></li>)}</ul>}
      </>}
    </Panel>
    <Panel title={detail?.title ?? "Case detail"} kicker="TIMELINE & EVIDENCE">
      {!props.connected ? <EmptyState title="Case detail unavailable" text="Connect the local API to inspect a case." />
        : !detail ? <EmptyState title="Select a case" text="Case history loads from the authenticated tenant-scoped API." />
          : <>
            <p className="ops-panel-footnote">Stable ID {detail.case_id} · created {dateText(detail.created_at_utc)} · updated {dateText(detail.updated_at_utc)}</p>
            <div className="ops-case-status"><span>Status: <b>{detail.status}</b></span><button type="button" disabled={props.busy || detail.status === "under_review"} onClick={() => props.onStatus("under_review")}>Mark under review</button><button type="button" disabled={props.busy || detail.status === "closed"} onClick={() => props.onStatus("closed")}>Close case</button><button type="button" disabled={props.busy || detail.status === "open"} onClick={() => props.onStatus("open")}>Reopen</button></div>
            <form className="ops-case-action" onSubmit={(event) => { event.preventDefault(); props.onLinkFinding(); }}>
              <label>Existing tenant finding<select value={props.findingId} onChange={(event) => props.setFindingId(event.currentTarget.value)}><option value="">Select finding</option>{props.findings.map((item) => <option value={item.finding_id} key={item.finding_id}>{item.rule_id} · {item.finding_id}</option>)}</select></label>
              <label>Why associated<textarea maxLength={500} value={props.rationale} onChange={(event) => props.setRationale(event.currentTarget.value)} placeholder="Explain the relationship; keep uncertainty explicit." /></label>
              <button type="submit" disabled={props.busy || !props.findingId || !props.rationale.trim()}>Link finding</button>
            </form>
            <form className="ops-case-action" onSubmit={(event) => { event.preventDefault(); if (evidenceRef.trim()) { props.onLinkEvidence(evidenceRef.trim()); setEvidenceRef(""); } }}>
              <label>Evidence reference for selected finding<input maxLength={100} value={evidenceRef} onChange={(event) => setEvidenceRef(event.currentTarget.value)} placeholder="synthetic-evidence-…" /></label>
              <button type="submit" disabled={props.busy || !props.findingId || !evidenceRef.trim()}>Link verified evidence</button>
            </form>
            <form className="ops-case-action" onSubmit={(event) => { event.preventDefault(); props.onNote(); }}>
              <label>Analyst note type<select value={props.noteClass} onChange={(event) => props.setNoteClass(event.currentTarget.value as "analyst_conclusion" | "unresolved_hypothesis")}><option value="analyst_conclusion">Analyst conclusion</option><option value="unresolved_hypothesis">Unresolved hypothesis</option></select></label>
              <label>Append-only note<textarea maxLength={1000} value={props.note} onChange={(event) => props.setNote(event.currentTarget.value)} /></label>
              <button type="submit" disabled={props.busy || !props.note.trim()}>Add note</button>
            </form>
            <div className="ops-case-status">
              {props.assessment && <button type="button" disabled={props.busy} onClick={() => props.onContext("assessment_report", props.assessment!.report_id)}>Link latest assessment context</button>}
              {props.evaluationRun && <button type="button" disabled={props.busy} onClick={() => props.onContext("evaluation_run", props.evaluationRun!.run_id)}>Link evaluation run context</button>}
            </div>
            <h3 className="ops-subheading">Classification guide</h3><p className="ops-panel-footnote">Verified evidence means a reference was checked against this tenant’s stored evidence. An inferred relationship is a working association. Analyst conclusions and unresolved hypotheses are attributed notes. None establishes compromise by itself.</p>
            <h3 className="ops-subheading">Recommendations linked to findings</h3>
            {detail.recommendations.length ? <ul className="ops-factor-list">{detail.recommendations.map((item, index) => <li key={`${item.category}-${index}`}>{item.category}: {item.text} Supporting findings: {item.supporting_finding_ids.join(", ")}</li>)}</ul> : <p className="ops-muted">No linked findings have recommendations.</p>}
            <h3 className="ops-subheading">Chronological history</h3>
            {detail.timeline.length ? <ol className="ops-case-timeline">{detail.timeline.map((item, index) => <li key={`${item.reference_id}-${item.occurred_at_utc}-${index}`}><time>{dateText(item.occurred_at_utc)}</time><b>{item.classification}</b><span>{item.description} · {item.reference_id}</span></li>)}</ol> : <p className="ops-muted">No timeline entries.</p>}
            {!!detail.context.length && <><h3 className="ops-subheading">Historical context</h3><ul className="ops-factor-list">{detail.context.map((item) => <li key={`${item.source_type}-${item.source_id}`}>{item.label} · {item.source_id} · {dateText(item.generated_at_utc)}</li>)}</ul></>}
            {!!detail.notes.length && <><h3 className="ops-subheading">Analyst notes</h3><ul className="ops-factor-list">{detail.notes.map((item, index) => <li key={`${item.created_at_utc}-${index}`}>{item.classification} · {dateText(item.created_at_utc)} · {item.text}</li>)}</ul></>}
          </>}
    </Panel>
  </div>;
}

function HealthView({ snapshot, connected }: { snapshot: Snapshot; connected: boolean }) {
  const service = snapshot.health;
  const source = snapshot.errors.source ? null : snapshot.source;
  const run = snapshot.processing?.latest_run;
  return <div className="ops-health-grid"><Panel title="Service status" kicker="LOCAL API"><StatusRow label="Loopback API" state={!connected ? "Not connected" : service ? "Healthy" : "Unavailable"} ok={Boolean(connected && service)}/><StatusRow label="Telemetry scheduler" state={!connected ? "Not connected" : snapshot.processing?.scheduler_state ?? "Unavailable"} ok={snapshot.processing?.scheduler_state === "running"}/><StatusRow label="Live demo source" state={!connected ? "Not connected" : source?.status === "unavailable" ? "Unavailable" : source?.status ?? "No status recorded"} ok={source?.status === "healthy"}/><p className="ops-panel-footnote">A missing source status is shown as unavailable, not as a healthy source.</p></Panel><Panel title="Latest processing run" kicker="RUN DETAIL">{!connected ? <EmptyState title="No authorized status" text="Connect with a current local token."/> : run ? <div className="ops-health-facts"><div><span>Run status</span><b>{run.status}</b></div><div><span>Started</span><b>{dateText(run.started_at_utc)}</b></div><div><span>Accepted records</span><b>{run.accepted_event_count}</b></div><div><span>Duplicate records</span><b>{run.duplicate_event_count}</b></div><div><span>Finding count</span><b>{run.finding_count}</b></div>{run.error_code && <div><span>Error category</span><b>{run.error_code}</b></div>}</div> : <Unavailable text={snapshot.errors.processing ?? "No processing run is available."}/>}</Panel><Panel title="Source counters" kicker="FIXED LOCAL SOURCE">{source ? <div className="ops-health-facts"><div><span>Last attempt</span><b>{dateText(source.last_attempt_at_utc)}</b></div><div><span>Last success</span><b>{dateText(source.last_success_at_utc)}</b></div><div><span>Input</span><b>{source.input_event_count ?? "—"}</b></div><div><span>Accepted</span><b>{source.accepted_event_count ?? "—"}</b></div><div><span>Duplicates</span><b>{source.duplicate_event_count ?? "—"}</b></div><div><span>Rejected</span><b>{source.rejected_record_count ?? "—"}</b></div>{source.error_code && <div><span>Error category</span><b>{source.error_code}</b></div>}</div> : <Unavailable text={snapshot.errors.source ?? "No source status has been recorded."}/>}</Panel></div>;
}

function StatusRow({ label, state, ok }: { label: string; state: string; ok: boolean }) { return <div className="ops-status-row"><span className={ok ? "status-pip status-ok" : "status-pip"}/><span>{label}</span><b>{state}</b></div>; }
function EmptyState({ title, text }: { title: string; text: string }) { return <div className="ops-empty"><span aria-hidden="true">◌</span><h3>{title}</h3><p>{text}</p></div>; }
function Unavailable({ text }: { text: string }) { return <p className="ops-unavailable" role="status"><span aria-hidden="true">!</span>{text}</p>; }
