import { useEffect, useRef, useState, type ChangeEvent } from "react";
import type { AssessmentReport } from "./types";
import { compareAssessmentReports, readAssessmentFile, readAssessmentResponse } from "./assessment";
import { Icon } from "./icons";
import baselineSample from "../data/public_demo_assessment_baseline.json";
import hardenedSample from "../data/public_demo_assessment_hardened.json";
import baselineUrl from "../data/public_demo_assessment_baseline.json?url&no-inline";
import hardenedUrl from "../data/public_demo_assessment_hardened.json?url&no-inline";

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
  return <section className="header-preview" aria-label="Published website protection comparison">
    <table className="header-preview-table">
      <caption className="sr-only">Browser protection settings before and after hardening</caption>
      <thead><tr className="header-preview-head"><th scope="col">WEBSITE PROTECTION SETTING</th><th scope="col">BEFORE</th><th scope="col">AFTER</th></tr></thead>
      <tbody>{baselineSample.header_results.map((before) => {
        const after = hardenedSample.header_results.find((item) => item.header === before.header);
        return <tr className="header-preview-row" key={before.header}>
          <th scope="row"><span><Icon name="shield" /><span><strong>{headerExplanations[before.header] ?? before.header}</strong><small>{before.header}</small></span></span></th>
          <td><span className={before.present ? "header-set" : "header-missing"}>{before.present ? "✓ Set" : "− Missing"}</span></td>
          <td><span className={after?.present ? "header-set" : "header-missing"}>{after?.present ? "✓ Set" : "− Missing"}</span></td>
        </tr>;
      })}</tbody>
    </table>
    <div className="header-preview-foot"><span className="preview-result"><Icon name="check" />{baselineSample.finding_count - hardenedSample.finding_count} missing settings corrected</span><span>Fixed published examples · Four headers only</span></div>
  </section>;
}

export function WebsiteAssessment() {
  const [reports, setReports] = useState<AssessmentReport[]>([]);
  const [status, setStatus] = useState("No website assessment loaded.");
  const [loadingSamples, setLoadingSamples] = useState(false);
  const loadGeneration = useRef(0);

  useEffect(() => () => { loadGeneration.current += 1; }, []);

  async function loadLocalFiles(event: ChangeEvent<HTMLInputElement>) {
    const generation = ++loadGeneration.current;
    const files = Array.from(event.currentTarget.files ?? []);
    event.currentTarget.value = "";
    setLoadingSamples(false);
    setReports([]);
    if (!files.length) { setStatus("No website assessment loaded."); return; }
    if (files.length > 2) {
      setStatus("Select one report per profile (baseline and/or hardened), at most two files.");
      return;
    }
    setStatus("Reading the selected local reports…");
    try {
      const loaded = await Promise.all(files.map(readAssessmentFile));
      if (generation !== loadGeneration.current) return;
      if (new Set(loaded.map((report) => report.profile)).size !== loaded.length) {
        throw new Error("Select one report per profile (baseline and/or hardened).");
      }
      setReports(loaded);
      setStatus(`${loaded.length} report(s) loaded for ${loaded[0].url}.`);
    } catch (error) {
      if (generation === loadGeneration.current) {
        setStatus(error instanceof Error ? error.message : "Could not read this assessment report.");
      }
    }
  }

  async function loadPublishedSamples() {
    const generation = ++loadGeneration.current;
    setReports([]);
    setStatus("Loading the published sample reports…");
    setLoadingSamples(true);
    try {
      const loaded = await Promise.all([
        fetch(baselineUrl, { cache: "no-cache", credentials: "same-origin" }).then((response) => readAssessmentResponse(response, "baseline sample")),
        fetch(hardenedUrl, { cache: "no-cache", credentials: "same-origin" }).then((response) => readAssessmentResponse(response, "hardened sample")),
      ]);
      if (generation !== loadGeneration.current) return;
      setReports(loaded);
      setStatus("2 published sample reports loaded. They cover HTTP status and four headers only.");
    } catch (error) {
      if (generation === loadGeneration.current) {
        setStatus(error instanceof Error ? error.message : "Could not load the published sample reports.");
      }
    } finally {
      if (generation === loadGeneration.current) setLoadingSamples(false);
    }
  }

  return <section className="assessment-section" id="assessment" aria-labelledby="assessment-title"><div className="section-head research-demo-head"><div><p className="eyebrow">02 / SEE THE IMPROVEMENT</p><h2 id="assessment-title">Small changes. Visible protection.</h2><p className="muted">A separate local website example: compare four browser protection settings before and after hardening.</p></div><span className="badge">Published samples</span></div>
    <HeaderComparisonPreview />
    <p className="assessment-limit">These settings help control browser behavior. This checks HTTP status and four response headers only; it is not a general website security assessment.</p>
    <details className="technical-evidence assessment-evidence"><summary><Icon name="code" /><span>Inspect the header reports <small>Original findings, local file comparison & downloads</small></span><span className="expand-label" aria-hidden="true"><span className="when-closed">EXPAND +</span><span className="when-open">COLLAPSE −</span></span></summary><div className="evidence-content">
      <h3>Website Header Assessment</h3><button className="assessment-sample-button" id="load-assessment-samples" type="button" onClick={() => void loadPublishedSamples()} disabled={loadingSamples}>{loadingSamples ? "Loading samples…" : "Load published baseline and hardened samples"}</button>
      <p className="assessment-downloads">Download: <a href={baselineUrl} download="aegisai-assessment-baseline-sample.json">baseline JSON</a> · <a href={hardenedUrl} download="aegisai-assessment-hardened-sample.json">hardened JSON</a></p>
      <label htmlFor="assessment-file">Assessment JSON files</label><input id="assessment-file" type="file" accept="application/json,.json" multiple onChange={(event) => void loadLocalFiles(event)} />
      <p id="assessment-status" className="muted" role="status" aria-live="polite">{status}</p><div id="assessment-results"><AssessmentComparison reports={reports} /></div>
    </div></details>
  </section>;
}

