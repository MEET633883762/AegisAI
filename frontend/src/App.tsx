import { useEffect, useState, type ChangeEvent } from "react";
import type { AssessmentReport, EpisodeRecord, PublicEpisode } from "./types";
import { parseEpisodeArtifact, readBoundedResponseText } from "./researchArtifact";
import { compareAssessmentReports, readAssessmentFile, readAssessmentResponse } from "./assessment";
import { EpisodeWalkthrough, EpisodeOutcome } from "./EpisodeWalkthrough";
import { describeRecord } from "./episodeStory";
import { Icon } from "./icons";
import baselineSample from "../data/public_demo_assessment_baseline.json";
import hardenedSample from "../data/public_demo_assessment_hardened.json";
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
          <h1 id="hero-title">Practice the attack.<br /><span>Understand the defense.</span></h1>
          <p className="hero-lede">A flight simulator for cybersecurity decisions. Follow an attacker and a defender through a fictional network—and see the evidence behind every move.</p>
          <div className="hero-actions"><a className="button button-primary" href="dashboard.html">Explore the demo <Icon name="arrow" /></a><a className="button button-secondary" href="#research">How it works</a></div>
          <p className="hero-note"><strong>Sample content is synthetic.</strong> A recorded, scripted exercise you can explore without an API key or an internet connection once running locally.</p>
        </div>
        <aside className="hero-panel" aria-label="Demo principles"><div className="panel-top"><span className="panel-icon" aria-hidden="true">◎</span><span>DESIGNED FOR INSPECTION</span></div>
          <div className="signal-row"><span className="signal signal-red" aria-hidden="true" /><span><b>The attacker</b><small>Tries to reach fictional records</small></span><span className="signal-label">RED TEAM</span></div><div className="flow-line" aria-hidden="true" />
          <div className="signal-row"><span className="signal signal-gold" aria-hidden="true" /><span><b>The safety gate</b><small>Checks every proposed action</small></span><span className="signal-label">CONTROLLER</span></div><div className="flow-line" aria-hidden="true" />
          <div className="signal-row"><span className="signal signal-blue" aria-hidden="true" /><span><b>The defender</b><small>Investigates the warning signs</small></span><span className="signal-label">BLUE TEAM</span></div>
          <div className="panel-foot"><span aria-hidden="true">↳</span> Precomputed example · no public execution</div>
        </aside>
      </section>
      <section className="proof-strip" aria-label="Project boundaries"><div className="page-width proof-items"><span><i aria-hidden="true">✓</i>Synthetic scenarios</span><span><i aria-hidden="true">✓</i>Controller-gated actions</span><span><i aria-hidden="true">✓</i>Read-only public experience</span></div></section>
      <section className="section page-width" id="research" aria-labelledby="research-title"><div className="section-intro"><p className="eyebrow">WHY THIS EXISTS</p><h2 id="research-title">An alert is only<br /><span>half the story.</span></h2><p>Spotting an attack does not guarantee it gets stopped. AegisAI makes that gap visible, so a security decision can be understood, questioned, and tested again.</p></div>
        <div className="feature-grid"><article className="feature-card"><span className="feature-number">01</span><h3>Watch the story</h3><p>Six key moments explain how an attacker moves toward fictional customer records.</p><span className="feature-tag">GUIDED WALKTHROUGH</span></article><article className="feature-card"><span className="feature-number">02</span><h3>Check the evidence</h3><p>Open the exact observations, permissions, and outcomes behind every recorded move.</p><span className="feature-tag">AUDITABLE DECISIONS</span></article><article className="feature-card"><span className="feature-number">03</span><h3>See a measurable change</h3><p>Compare four website protection settings before and after local hardening.</p><span className="feature-tag">BEFORE & AFTER</span></article></div>
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

  return <section className="research-demo" id="research-demo" aria-labelledby="research-demo-title">
    <div className="section-head research-demo-head"><div><p className="eyebrow">01 / FOLLOW THE EXERCISE</p><h2 id="research-demo-title">One attack. Every decision visible.</h2><p className="muted">Explore six key moments. The map and explanation follow the record you select.</p></div><span className="badge replay-badge"><span className="dot" />Recorded, not live</span></div>
    <p className="load-status" role="status" aria-live="polite">{status}</p>
    {artifact && selected && <>
      <EpisodeWalkthrough artifact={artifact} selected={selected} onSelect={setSelected} />
      <EpisodeOutcome artifact={artifact} />
      <div className="takeaway"><span className="takeaway-icon"><Icon name="eye" /></span><p><strong>The lesson: noticing a threat is not the same as stopping it.</strong> In this scripted sample, the defender keeps investigating while the attacker advances. The trace makes that response gap visible.</p></div>
      <details className="technical-evidence"><summary><Icon name="code" /><span>Look under the hood <small>All {artifact.records.length} actions, original evidence & metric definitions</small></span><span className="expand-label">EXPAND +</span></summary><div className="evidence-content">
        <section className="research-provenance" aria-label="Sample provenance"><h3>Sample provenance and outcome</h3><p>{artifact.labels.display}</p><p>{artifact.provenance.scenario_id} · seed {artifact.provenance.seed} · {artifact.records.length} recorded actions</p><p>{artifact.provenance.red_policy} vs {artifact.provenance.blue_policy} · {artifact.provenance.research_split}</p><p>Episode objective recorded as {artifact.objective_result.achieved ? "achieved" : "not achieved"} in this one sample.</p></section>
        <section className="research-metrics-section" aria-labelledby="research-metrics-title"><div className="section-head"><h3 id="research-metrics-title">Episode metrics</h3><span className="badge">Single synthetic episode</span></div><div className="research-metrics">{artifact.metrics.map((metric) => <article className="research-metric" key={metric.id}><h3>{metric.label}</h3><p className="research-metric-value">{metric.numerator} / {metric.denominator} {metric.unit} · {(metric.value * 100).toFixed(1)}%</p><p className="research-metric-definition">{metric.definition}</p></article>)}</div></section>
        <div className="research-demo-grid"><section className="research-timeline-panel" aria-labelledby="research-timeline-title"><div className="section-head"><h3 id="research-timeline-title">Recorded action timeline</h3><span className="badge">Select a step</span></div><ol className="research-timeline" aria-label="Precomputed Red and Blue actions">{artifact.records.map((record) => <li key={record.id}><button type="button" className="research-timeline-button" aria-pressed={selected.id === record.id} onClick={() => setSelected(record)}><span className={`timeline-role ${record.role}`}>{record.role.toUpperCase()}</span><span>{describeRecord(record).title}<small>Step {record.step} · {record.action.type} · {record.result.outcome}</small></span></button></li>)}</ol></section>
          <section className="research-detail-panel" aria-labelledby="research-detail-title"><h3 id="research-detail-title">Selected action details</h3><div aria-live="polite" aria-atomic="true"><RecordDetails record={selected} /></div></section></div>
        <section className="research-limitations" aria-labelledby="research-limitations-title"><h3 id="research-limitations-title">Sample limitations</h3><ul>{artifact.limitations.map((limitation, index) => <li key={`${index}-${limitation}`}>{limitation}</li>)}</ul></section>
      </div></details>
    </>}
    <div className="research-download-row"><p className="muted">Synthetic data · Scripted agents · One reproducible episode · No real-world accuracy claim</p><a className="download-sample" href={episodeUrl} download="aegisai-synthetic-episode-v1.json">Download sample report <span aria-hidden="true">↓</span></a></div>
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
  return <>{comparison && <div className="comparison"><Icon name="check" /><span><strong>Before / after:</strong> {comparison.resolved} finding(s) resolved; {comparison.remaining} remain in the hardened report.</span></div>}{reports.map((report) => <AssessmentReportView report={report} key={report.profile} />)}</>;
}

const headerExplanations: Record<string, string> = {
  "Content-Security-Policy": "Control which content can load",
  "X-Content-Type-Options": "Prevent risky file-type guessing",
  "Referrer-Policy": "Limit information shared with links",
  "Permissions-Policy": "Restrict browser feature access",
};

function HeaderComparisonPreview() {
  return <section className="header-preview" aria-label="Published website protection comparison"><div className="header-preview-head"><span>WEBSITE PROTECTION SETTING</span><span>BEFORE</span><span>AFTER</span></div>{baselineSample.header_results.map((before) => {
    const after = hardenedSample.header_results.find((item) => item.header === before.header);
    return <div className="header-preview-row" key={before.header}><span><Icon name="shield" /><span><strong>{headerExplanations[before.header] ?? before.header}</strong><small>{before.header}</small></span></span><span className={before.present ? "header-set" : "header-missing"}>{before.present ? "✓ Set" : "− Missing"}</span><span className={after?.present ? "header-set" : "header-missing"}>{after?.present ? "✓ Set" : "− Missing"}</span></div>;
  })}<div className="header-preview-foot"><span className="preview-result"><Icon name="check" />{baselineSample.finding_count - hardenedSample.finding_count} missing settings corrected</span><span>Fixed published examples · Four headers only</span></div></section>;
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

  return <section className="assessment-section" id="assessment" aria-labelledby="assessment-title"><div className="section-head research-demo-head"><div><p className="eyebrow">02 / SEE THE IMPROVEMENT</p><h2 id="assessment-title">Small changes. Visible protection.</h2><p className="muted">A separate local website example: compare four browser protection settings before and after hardening.</p></div><span className="badge">Published samples</span></div>
    <HeaderComparisonPreview />
    <p className="assessment-limit">These settings help control browser behavior. This checks HTTP status and four response headers only; it is not a general website security assessment.</p>
    <details className="technical-evidence assessment-evidence"><summary><Icon name="code" /><span>Inspect the header reports <small>Original findings, local file comparison & downloads</small></span><span className="expand-label">EXPAND +</span></summary><div className="evidence-content">
      <h3>Website Header Assessment</h3><button className="assessment-sample-button" id="load-assessment-samples" type="button" onClick={() => void loadPublishedSamples()} disabled={loadingSamples}>{loadingSamples ? "Loading samples…" : "Load published baseline and hardened samples"}</button>
      <p className="assessment-downloads">Download: <a href={baselineUrl} download="aegisai-assessment-baseline-sample.json">baseline JSON</a> · <a href={hardenedUrl} download="aegisai-assessment-hardened-sample.json">hardened JSON</a></p>
      <label htmlFor="assessment-file">Assessment JSON files</label><input id="assessment-file" type="file" accept="application/json,.json" multiple onChange={(event) => void loadLocalFiles(event)} />
      <p id="assessment-status" className="muted" role="status" aria-live="polite">{status}</p><div id="assessment-results"><AssessmentComparison reports={reports} /></div>
    </div></details>
  </section>;
}

function DashboardPage() {
  const [presenting, setPresenting] = useState(false);
  return <div className={`demo-page${presenting ? " presentation-view" : ""}`}><a className="skip-link" href="#dashboard-main">Skip to dashboard</a>
    <nav className="demo-nav" aria-label="Main navigation"><Brand /><div className="demo-nav-links"><a href="index.html">Overview</a><a className="current" href="#research-demo" aria-current="page">The exercise</a><a href="#assessment">Before & after</a></div><button className="presentation-toggle" type="button" aria-pressed={presenting} onClick={() => { setPresenting(!presenting); window.scrollTo?.({ top: 0, behavior: "instant" }); }}><Icon name={presenting ? "monitor" : "play"} />{presenting ? "Exit presentation" : "Present demo"}</button></nav>
    <main id="dashboard-main">
      <header className="demo-hero"><div><p className="eyebrow">THE AEGISAI EXPERIENCE</p><h1>A cyberattack,<br /><span>explained.</span></h1><p className="demo-lede">An attacker looks for a way in. A defender follows the clues.<br className="desktop-break" /> See what happens when finding a threat isn't enough to stop it.</p></div><div className="demo-hero-note"><span className="hero-note-icon"><Icon name="play" /></span><strong>A security rehearsal.<br />With the evidence included.</strong><p>A guided replay of a fictional network.<br />No real systems or customer data.</p><a href="#research-demo">Start exploring <Icon name="arrow" /></a></div></header>
      <section className="actor-cards" aria-label="Meet the three roles"><article className="actor-card actor-card-red"><span className="actor-card-icon"><Icon name="target" /></span><div><p>THE ATTACKER <span>RED TEAM</span></p><h2>Finds a way in.</h2><span>Tries to reach the fictional records.</span></div></article><article className="actor-card actor-card-gate"><span className="actor-card-icon"><Icon name="lock" /></span><div><p>THE SAFETY GATE <span>CONTROLLER</span></p><h2>Checks every move.</h2><span>Enforces the simulation's permissions.</span></div></article><article className="actor-card actor-card-blue"><span className="actor-card-icon"><Icon name="shield" /></span><div><p>THE DEFENDER <span>BLUE TEAM</span></p><h2>Follows the clues.</h2><span>Investigates the warning signs.</span></div></article></section>
      <aside className="demo-disclosure"><Icon name="eye" /><p><strong>You're watching a recorded, scripted exercise.</strong> All data is synthetic. Selecting a step changes the view; it does not execute an attack or call an AI model.</p><span>READ-ONLY DEMO</span></aside>
      <ResearchDemo /><WebsiteAssessment />
      <section className="why-aegis"><span className="eyebrow">WHAT MAKES THIS USEFUL?</span><h2>Don't just count alerts.<br /><span>Understand the decision behind them.</span></h2><div><p><Icon name="eye" /><span><strong>Evidence you can inspect</strong>See what each role actually knew before it acted.</span></p><p><Icon name="lock" /><span><strong>Permissions you can verify</strong>The Controller owns execution and authorization.</span></p><p><Icon name="arrow" /><span><strong>A result you can reproduce</strong>Replay the same seeded scenario and compare outcomes.</span></p></div></section>
      <footer className="demo-footer"><Brand /><p>Built to question security decisions.<br />Research prototype · Synthetic results · Read-only</p><a href="privacy.html">Privacy & data handling <span aria-hidden="true">↗</span></a></footer>
    </main>
  </div>;
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
