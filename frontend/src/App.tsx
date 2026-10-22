import { useEffect, useState, type ChangeEvent } from "react";
import type { AssessmentReport, EpisodeRecord, PublicEpisode } from "./types";
import { parseEpisodeArtifact, readBoundedResponseText } from "./researchArtifact";
import { compareAssessmentReports, readAssessmentFile, readAssessmentResponse } from "./assessment";
import episodeUrl from "../data/public_demo_episode.json?url&no-inline";
import baselineUrl from "../data/public_demo_assessment_baseline.json?url&no-inline";
import hardenedUrl from "../data/public_demo_assessment_hardened.json?url&no-inline";

function Brand() {
  return <a className="brand" href="index.html" aria-label="AegisAI home"><span className="brand-mark" aria-hidden="true">A</span><span>Aegis<span className="brand-accent">AI</span></span></a>;
}

function Footer({ dashboard = false }: { dashboard?: boolean }) {
  return <footer className={dashboard ? "footer site-footer" : "site-footer"}>
    <div className="page-width footer-inner"><Brand /><p>Research prototype · Synthetic examples · Read-only</p>
      <a href="privacy.html">Privacy</a><a href={dashboard ? "index.html" : "dashboard.html"}>{dashboard ? "Home" : "Explore dashboard"}</a>
    </div>
  </footer>;
}

function LandingPage() {
  return <>
    <a className="skip-link" href="#main">Skip to content</a>
    <header className="site-header"><Brand /><nav className="primary-nav" aria-label="Main navigation">
      <a href="#research">Research</a><a href="#boundaries">Safety</a><a className="nav-cta" href="dashboard.html">Explore the demo <span aria-hidden="true">↗</span></a>
    </nav></header>
    <main id="main">
      <section className="hero page-width" aria-labelledby="hero-title">
        <div className="hero-copy"><p className="eyebrow"><span className="live-dot" aria-hidden="true" />Research prototype · Read-only demo</p>
          <h1 id="hero-title">Make security decisions <span>clear enough to inspect.</span></h1>
          <p className="hero-lede">AegisAI explores how simulated Red and Blue teams can act within clear authorization boundaries, with evidence and decisions visible at every step.</p>
          <div className="hero-actions"><a className="button button-primary" href="dashboard.html">Explore the demo <span aria-hidden="true">→</span></a><a className="button button-secondary" href="#research">How it works</a></div>
          <p className="hero-note"><strong>Sample content is synthetic.</strong> The dashboard includes illustrative simulator values, not verified security benchmarks.</p>
        </div>
        <aside className="hero-panel" aria-label="Demo principles"><div className="panel-top"><span className="panel-icon" aria-hidden="true">◎</span><span>DESIGNED FOR INSPECTION</span></div>
          <div className="signal-row"><span className="signal signal-red" aria-hidden="true" /><span><b>Red</b><small>Proposes a simulated action</small></span><span className="signal-label">SIMULATED</span></div><div className="flow-line" aria-hidden="true" />
          <div className="signal-row"><span className="signal signal-gold" aria-hidden="true" /><span><b>Controller</b><small>Checks policy and authorization</small></span><span className="signal-label">GATED</span></div><div className="flow-line" aria-hidden="true" />
          <div className="signal-row"><span className="signal signal-blue" aria-hidden="true" /><span><b>Blue</b><small>Responds to available evidence</small></span><span className="signal-label">OBSERVABLE</span></div>
          <div className="panel-foot"><span aria-hidden="true">↳</span> Precomputed example · no public execution</div>
        </aside>
      </section>
      <section className="proof-strip" aria-label="Project boundaries"><div className="page-width proof-items"><span><i aria-hidden="true">✓</i>Synthetic scenarios</span><span><i aria-hidden="true">✓</i>Controller-gated actions</span><span><i aria-hidden="true">✓</i>Read-only public experience</span></div></section>
      <section className="section page-width" id="research" aria-labelledby="research-title"><div className="section-intro"><p className="eyebrow">THE RESEARCH DEMO</p><h2 id="research-title">Follow the evidence.<br /><span>Understand the decision.</span></h2><p>AegisAI is a simulator-first research project. Its demo helps people inspect how actions, observations, authorization, and outcomes connect in a controlled exercise.</p></div>
        <div className="feature-grid"><article className="feature-card"><span className="feature-number">01</span><h3>Trace the exercise</h3><p>Move through a precomputed Red/Blue timeline and inspect each synthetic event in context.</p><span className="feature-tag">SYNTHETIC EPISODE</span></article><article className="feature-card"><span className="feature-number">02</span><h3>Inspect the decision</h3><p>Review structured observations, evidence references, and authorization outcomes where available.</p><span className="feature-tag">STRUCTURED TRACE</span></article><article className="feature-card"><span className="feature-number">03</span><h3>Compare a narrow check</h3><p>See sample baseline and hardened HTTP header reports from the local demo site.</p><span className="feature-tag">HEADERS ONLY</span></article></div>
      </section>
      <section className="boundary-section" id="boundaries" aria-labelledby="boundary-title"><div className="page-width boundary-layout"><div><p className="eyebrow">A SMALL, CONTROLLED SCOPE</p><h2 id="boundary-title">Built to demonstrate.<br /><span>Clear about its limits.</span></h2></div><div className="boundary-content"><p>The public experience serves reviewed sample files. It does not execute simulations or contact websites.</p><ul><li><span aria-hidden="true">—</span>No public simulation runs, uploads, or user-submitted targets.</li><li><span aria-hidden="true">—</span>No public LLM calls, accounts, billing, or customer data store.</li><li><span aria-hidden="true">—</span>The local header check covers selected response headers and status only.</li></ul><p className="boundary-footnote">Synthetic demonstrations do not establish real-world security effectiveness or certify a website as secure.</p></div></div></section>
      <section className="closing-cta page-width" aria-labelledby="cta-title"><div><p className="eyebrow">TAKE A CLOSER LOOK</p><h2 id="cta-title">Explore the read-only demo.</h2><p>Inspect the sample dashboard and its local assessment comparison.</p></div><a className="button button-primary" href="dashboard.html">Open AegisAI demo <span aria-hidden="true">→</span></a></section>
    </main><Footer />
  </>;
}

function ResearchDemo() {
  const [artifact, setArtifact] = useState<PublicEpisode | null>(null);
  const [selected, setSelected] = useState<EpisodeRecord | null>(null);
  const [status, setStatus] = useState("Loading the precomputed sample…");

  useEffect(() => {
    let active = true;
    const load = async () => {
      try {
        const response = await fetch(episodeUrl, { cache: "no-cache", credentials: "same-origin" });
        if (!response.ok) throw new Error(`Sample artifact request failed (${response.status}).`);
        const nextArtifact = parseEpisodeArtifact(await readBoundedResponseText(response));
        if (!active) return;
        setArtifact(nextArtifact);
        setSelected(nextArtifact.records[0] ?? null);
        setStatus(`Loaded ${nextArtifact.records.length} precomputed action records. No actions were executed.`);
      } catch (error) {
        if (active) setStatus(`Could not load the sample: ${error instanceof Error ? error.message : "unexpected error"}`);
      }
    };
    void load();
    return () => { active = false; };
  }, []);

  return <section className="card research-demo" id="research-demo" aria-labelledby="research-demo-title">
    <div className="section-head research-demo-head"><div><h2 id="research-demo-title">Interactive Red / Blue Episode</h2><p className="muted">Select a recorded action to inspect its role-scoped evidence, structured action, validation, authorization, and result.</p></div><span className="badge">Synthetic · Precomputed · Read-only</span></div>
    <p className="muted" role="status" aria-live="polite">{status}</p>
    {artifact && <>
      <section className="research-provenance" aria-label="Sample provenance"><h3>Sample provenance and outcome</h3><p>{artifact.labels.display}</p><p>{artifact.provenance.scenario_id} · seed {artifact.provenance.seed} · {artifact.records.length} recorded actions</p><p>{artifact.provenance.red_policy} vs {artifact.provenance.blue_policy} · {artifact.provenance.research_split}</p><p>Episode objective recorded as {artifact.objective_result.achieved ? "achieved" : "not achieved"} in this one sample.</p></section>
      <section className="research-metrics-section" aria-labelledby="research-metrics-title"><div className="section-head"><h3 id="research-metrics-title">Episode metrics</h3><span className="badge">Single synthetic episode</span></div><div className="research-metrics">{artifact.metrics.map((metric) => <article className="research-metric" key={metric.id}><h3>{metric.label}</h3><p className="research-metric-value">{metric.numerator} / {metric.denominator} {metric.unit} · {(metric.value * 100).toFixed(1)}%</p><p className="research-metric-definition">{metric.definition}</p></article>)}</div></section>
      <div className="research-demo-grid"><section className="research-timeline-panel" aria-labelledby="research-timeline-title"><div className="section-head"><h3 id="research-timeline-title">Recorded action timeline</h3><span className="badge">Select a step</span></div><ol className="research-timeline" aria-label="Precomputed Red and Blue actions">{artifact.records.map((record) => <li key={record.id}><button type="button" className="research-timeline-button" aria-pressed={selected?.id === record.id} onClick={() => setSelected(record)}>Step {record.step} · {record.role.toUpperCase()} · {record.action.type} · {record.result.outcome}</button></li>)}</ol></section>
        <section className="research-detail-panel" aria-labelledby="research-detail-title"><h3 id="research-detail-title">Selected action details</h3><div aria-live="polite" aria-atomic="true">{selected ? <RecordDetails record={selected} /> : <p className="research-muted">Select a recorded action to inspect its details.</p>}</div></section></div>
      <section className="research-limitations" aria-labelledby="research-limitations-title"><h3 id="research-limitations-title">Sample limitations</h3><ul>{artifact.limitations.map((limitation, index) => <li key={`${index}-${limitation}`}>{limitation}</li>)}</ul></section>
    </>}
    <div className="research-download-row"><p className="muted">Download the same reviewed JSON artifact shown here, including schema version, provenance, and limitations.</p><a className="download-sample" href={episodeUrl} download="aegisai-synthetic-episode-v1.json">Download sample report <span aria-hidden="true">↓</span></a></div>
  </section>;
}

function RecordDetails({ record }: { record: EpisodeRecord }) {
  return <><p className="research-detail-kicker">{record.role.toUpperCase()} OBSERVATION · STEP {record.step}</p><h4 className="research-action-title">{record.action.type}</h4>
    <p className="research-scope-note">Evidence below comes only from the {record.role.toUpperCase()} role-specific observation.</p>
    <dl className="research-summary"><dt>Target</dt><dd>{record.action.target}</dd><dt>Validation</dt><dd>{record.validation.accepted ? "Accepted" : "Rejected"} · {record.validation.reason}</dd><dt>Controller authorization</dt><dd>{record.authorization.authorized ? "Authorized" : "Denied"} · {record.authorization.policy_reason}</dd><dt>Recorded result</dt><dd>{record.result.outcome} · {record.result.success ? "success" : "not successful"}</dd><dt>Result message</dt><dd>{record.result.message}</dd><dt>Decision category</dt><dd>{record.action.reason_category}</dd><dt>Expected intent</dt><dd>{record.action.expected_outcome}</dd>{Object.keys(record.action.parameters).length > 0 && <><dt>Parameters</dt><dd className="research-parameters">{Object.entries(record.action.parameters).map(([key, value]) => `${key}: ${value}`).join(" · ")}</dd></>}</dl>
    <h5 className="research-evidence-title">Role-visible evidence ({record.evidence.length})</h5>{record.evidence.length === 0 ? <p className="research-muted">No evidence items were recorded in this role’s pre-action trace.</p> : <ul className="research-evidence-list">{record.evidence.map((item, index) => <li key={`${item.reference}-${index}`}><strong>{item.reference} · {item.source}</strong><span>{item.value}</span></li>)}</ul>}
  </>;
}

function AssessmentReportView({ report }: { report: AssessmentReport }) {
  return <section className="assessment-report"><h3>{report.profile} profile · {report.status}</h3><p className="muted">{report.checked_at_utc} · {report.finding_count} finding(s)</p>
    <div className="assessment-grid">{report.header_results.map((item) => <div className="assessment-row" key={item.header}><strong>{item.header}</strong><span className={item.present ? "ok" : "finding-state"}>{item.present ? "PRESENT" : "MISSING / INCORRECT"}</span><div className="muted">Expected: <code>{item.expected_value}</code></div>{item.observed_value !== null && <div className="muted">Observed: <code>{item.observed_value}</code></div>}</div>)}</div>
    {report.findings.length > 0 ? <><h4>Findings</h4>{report.findings.map((finding) => <article className="finding" key={finding.id}><div className="finding-title"><strong>{finding.title}</strong><span className="badge">{finding.severity}</span></div><p>{finding.description}</p><p><b>Evidence:</b> {finding.evidence}</p><p><b>Remediation:</b> {finding.remediation}</p></article>)}</> : <p className="ok">No missing checked headers.</p>}
    <p className="muted">{report.limitations.join(" ")}</p></section>;
}

function AssessmentComparison({ reports }: { reports: AssessmentReport[] }) {
  const comparison = compareAssessmentReports(reports);
  if (reports.length === 0) return null;
  return <>{comparison && <div className="comparison"><strong>Before / after:</strong> {comparison.resolved} finding(s) resolved; {comparison.remaining} remain in the hardened report.</div>}{reports.map((report) => <AssessmentReportView report={report} key={report.profile} />)}</>;
}

function WebsiteAssessment() {
  const [reports, setReports] = useState<AssessmentReport[]>([]);
  const [status, setStatus] = useState("No website assessment loaded.");
  const [loadingSamples, setLoadingSamples] = useState(false);

  async function loadLocalFiles(event: ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.currentTarget.files ?? []);
    event.currentTarget.value = "";
    setReports([]);
    if (!files.length) { setStatus("No website assessment loaded."); return; }
    try {
      const loaded = await Promise.all(files.map(readAssessmentFile));
      if (loaded.length > 2 || new Set(loaded.map((report) => report.profile)).size !== loaded.length) {
        throw new Error("Select one report per profile (baseline and/or hardened).");
      }
      setReports(loaded);
      setStatus(`${loaded.length} report(s) loaded for ${loaded[0].url}.`);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Could not read this assessment report.");
    }
  }

  async function loadPublishedSamples() {
    setReports([]);
    setStatus("Loading the published sample reports…");
    setLoadingSamples(true);
    try {
      const loaded = await Promise.all([
        fetch(baselineUrl, { cache: "no-cache", credentials: "same-origin" }).then((response) => readAssessmentResponse(response, "baseline sample")),
        fetch(hardenedUrl, { cache: "no-cache", credentials: "same-origin" }).then((response) => readAssessmentResponse(response, "hardened sample")),
      ]);
      setReports(loaded);
      setStatus("2 published sample reports loaded. They cover HTTP status and four headers only.");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Could not load the published sample reports.");
    } finally {
      setLoadingSamples(false);
    }
  }

  return <section className="card" id="assessment" aria-labelledby="assessment-title"><div className="section-head"><h2 id="assessment-title">Website Header Assessment</h2><span className="badge">Local demo · Read-only</span></div>
    <p className="muted">Load the sanitized published samples or select local demo reports to compare remediation. This checks HTTP status and four response headers only; it is not a general website security assessment.</p>
    <button className="assessment-sample-button" id="load-assessment-samples" type="button" onClick={() => void loadPublishedSamples()} disabled={loadingSamples}>{loadingSamples ? "Loading samples…" : "Load published baseline and hardened samples"}</button>
    <p className="assessment-downloads">Download: <a href={baselineUrl} download="aegisai-assessment-baseline-sample.json">baseline JSON</a> · <a href={hardenedUrl} download="aegisai-assessment-hardened-sample.json">hardened JSON</a></p>
    <label htmlFor="assessment-file">Assessment JSON files</label><input id="assessment-file" type="file" accept="application/json,.json" multiple onChange={(event) => void loadLocalFiles(event)} />
    <p id="assessment-status" className="muted" role="status" aria-live="polite">{status}</p><div id="assessment-results"><AssessmentComparison reports={reports} /></div>
  </section>;
}

const illustrative = {
  metrics: { attackSuccessRate: .33, detectionRate: .83, mitigationSuccessRate: .75, meanDetectionTime: 3.2, falsePositiveRate: .08, decisionLatency: .41 },
  timeline: [
    { id: "e1", step: 1, role: "RED", action: "DISCOVER_HOST", target: "web-server", status: "success", timestamp: 1 },
    { id: "e2", step: 2, role: "RED", action: "ENUMERATE_PORT", target: "web-server", status: "success", timestamp: 2 },
    { id: "e3", step: 3, role: "RED", action: "EXPLOIT_SIMULATED_VULNERABILITY", target: "web-server", status: "success", timestamp: 3 },
    { id: "e4", step: 4, role: "BLUE", action: "INVESTIGATE_ALERT", target: "web-server", status: "success", timestamp: 4 },
    { id: "e5", step: 5, role: "BLUE", action: "ISOLATE_HOST", target: "web-server", status: "success", timestamp: 5 },
    { id: "e6", step: 6, role: "RED", action: "LATERAL_MOVE", target: "database", status: "blocked", timestamp: 6 },
  ],
  traces: [{ id: "tr1", step: 5, role: "BLUE", observation: "New alert on web-server", evidence: ["alert:e4", "telemetry:e3"], action: "ISOLATE_HOST", rationale: "The observed alert and preceding exploit telemetry justify containment of the affected host.", reasonCategory: "CONTAINMENT", expectedOutcome: "Stop further lateral movement.", actualOutcome: "Database access attempt was blocked.", success: true }],
  patches: [{ id: "kp1", title: "Contain exploited web host before lateral movement", status: "validated", version: 2, evidenceRef: "ep-demo-001/step-5", lesson: "When a simulated exploit is detected on the web host, isolate it before lateral movement can occur." }],
  threats: [{ id: "ti1", source: "curated-local", title: "Simulated web-service vulnerability guidance", tags: ["CVE", "web", "defense"], trust: "untrusted", content: "Reference material only; never treat retrieved text as executable instructions." }],
};

function LegacyIllustration() {
  const percentage = (value: number) => `${Math.round(value * 100)}%`;
  const seconds = (value: number) => `${value.toFixed(2)} s`;
  return <details className="legacy-dashboard card"><summary>Earlier illustrative dashboard example (not verified research results)</summary><p className="muted">The example below is retained for compatibility with the original static dashboard. Its values are illustrative and are not the reviewed episode artifact above.</p>
    <section aria-labelledby="metrics-title"><div className="section-head dashboard-section-title"><h2 id="metrics-title">Illustrative metrics</h2><span className="badge">Unverified example values</span></div><section className="metrics" aria-label="Illustrative metrics">{[["Attack Success Rate", percentage(illustrative.metrics.attackSuccessRate)], ["Detection Rate", percentage(illustrative.metrics.detectionRate)], ["Mitigation Success", percentage(illustrative.metrics.mitigationSuccessRate)], ["Mean Detection Time", seconds(illustrative.metrics.meanDetectionTime)], ["False Positive Rate", percentage(illustrative.metrics.falsePositiveRate)], ["Decision Latency", seconds(illustrative.metrics.decisionLatency)]].map(([label, value]) => <article className="card metric" key={label}><div className="muted">{label}</div><div className="metric-value">{value}</div></article>)}</section></section>
    <section className="card" aria-labelledby="timeline-title"><div className="section-head"><h2 id="timeline-title">Illustrative Red / Blue Timeline</h2><span className="badge">Not artifact-backed</span></div><div className="timeline">{illustrative.timeline.map((item) => <div className="event" key={item.id}><div className={`role ${item.role.toLowerCase()}`}>{item.role}</div><div><strong>Step {item.step}: {item.action}</strong><div className="muted">Target: {item.target} · t={item.timestamp}s · {item.status}</div></div></div>)}</div></section>
    <section className="card" aria-labelledby="traces-title"><div className="section-head"><h2 id="traces-title">Illustrative Decision Traces</h2><span className="badge">Structured summary · No hidden CoT</span></div>{illustrative.traces.map((trace) => <div className="trace" key={trace.id}><div className="trace-top"><strong>{trace.role} · Step {trace.step}</strong><span className="ok">SUCCESS</span></div><p><b>Observation:</b> {trace.observation}</p><p><b>Evidence:</b> {trace.evidence.join(", ")}</p><p><b>Action:</b> {trace.action} · <b>Reason:</b> {trace.reasonCategory}</p><p><b>Rationale:</b> {trace.rationale}</p><p><b>Expected:</b> {trace.expectedOutcome}</p><p><b>Actual:</b> {trace.actualOutcome}</p></div>)}</section>
    <div className="two-col"><section className="card" aria-labelledby="knowledge-title"><h2 id="knowledge-title">Illustrative Adaptive Knowledge</h2>{illustrative.patches.map((patch) => <div className="item" key={patch.id}><strong>{patch.title}</strong><div className="muted">v{patch.version} · {patch.status} · evidence {patch.evidenceRef}</div><p>{patch.lesson}</p></div>)}</section><section className="card" aria-labelledby="threat-title"><h2 id="threat-title">Illustrative Threat Intelligence</h2>{illustrative.threats.map((threat) => <div className="item" key={threat.id}><strong>{threat.title}</strong><div className="muted">{threat.source} · trust={threat.trust}</div><p>{threat.content}</p></div>)}</section></div>
  </details>;
}

function DashboardPage() {
  return <><a className="skip-link" href="#dashboard-main">Skip to dashboard</a><nav className="dashboard-nav" aria-label="Main navigation"><a className="dashboard-brand" href="index.html"><span aria-hidden="true">A</span> AegisAI</a><div><a href="index.html">Home</a><a className="dashboard-nav-current" href="dashboard.html" aria-current="page">Research demo</a><a href="privacy.html">Privacy</a></div></nav>
    <main id="dashboard-main"><header className="top"><div><div className="eyebrow">AEGISAI · RESEARCH PROTOTYPE</div><h1>Purple-Team Security Dashboard</h1><p className="muted">Inspect a sample Red/Blue timeline, structured decision traces, and local website header reports.</p></div><div className="status"><span className="dot" />SAMPLE EPISODE</div></header>
      <aside className="sample-notice" aria-label="Sample data notice"><strong>Synthetic, precomputed sample.</strong> This page replays reviewed output from one deterministic scripted simulator episode. It is not representative evidence of real-world security effectiveness. Public pages do not execute actions.</aside>
      <section className="meta" aria-label="Sample provenance"><span>Public demo <b>Precomputed artifact</b></span><span>Policy boundary <b>Controller-gated simulator</b></span><span>Access <b>Read-only</b></span></section>
      <ResearchDemo /><WebsiteAssessment /><LegacyIllustration />
      <footer className="footer">Observational sample only. Actions are never executed from this frontend. Synthetic results do not establish security or real-world effectiveness. <a href="privacy.html">Privacy</a></footer>
    </main>
  </>;
}

function PrivacyPage() {
  return <><a className="skip-link" href="#privacy-main">Skip to content</a><header className="site-header"><Brand /><nav className="primary-nav" aria-label="Main navigation"><a href="index.html">Home</a><a href="dashboard.html">Research demo</a></nav></header>
    <main id="privacy-main"><section className="section page-width" aria-labelledby="privacy-title"><div className="section-intro"><p className="eyebrow">PUBLIC DEMO · PRIVACY</p><h1 id="privacy-title">Privacy and data handling</h1><p>This disclosure describes the current static AegisAI research demo.</p></div><div className="privacy-content"><h2>No accounts or submitted data</h2><p>The site has no accounts, database, analytics, contact form, or public simulation service. It serves static pages and reviewed synthetic JSON samples. The site code does not intentionally set analytics cookies or store visitor profiles.</p><h2>Local assessment files</h2><p>If you select an assessment JSON file, your browser reads it locally to display the report. The file is not uploaded by this site. The public comparison button fetches only the two fixed, published sample files from this site. The local website checker is a separate tool and is not run by this public site.</p><h2>Hosting request data</h2><p>The static hosting provider processes network requests to deliver the pages and may process connection or request metadata, such as IP address, requested URL, and browser information, for delivery, reliability, and security. The provider controls its own logging and retention under its current terms and privacy documentation. AegisAI does not control that provider-side processing.</p><h2>Sample data and limitations</h2><p>Published episode and assessment files are reviewed synthetic examples. The assessment comparison checks HTTP status and four configured response headers only. Neither the sample results nor the comparison establish that a real website is secure.</p><h2>Questions</h2><p>This static site currently provides no contact form or dedicated privacy inbox. The project owner must designate a public contact channel before launch. No visitor account or support submission is available through this site.</p><p><a href="dashboard.html">Return to the research demo</a></p></div></section></main><Footer />
  </>;
}

export function App({ page }: { page: string }) {
  if (page === "landing") return <LandingPage />;
  if (page === "dashboard") return <DashboardPage />;
  if (page === "privacy") return <PrivacyPage />;
  return <main className="page-width"><h1>Page unavailable</h1><p>Choose Home or Research demo from the navigation.</p><a href="index.html">Home</a></main>;
}
