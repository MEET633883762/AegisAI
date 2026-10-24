import type { ExecutiveReport } from "./types";

const escapeHtml = (value: unknown): string => String(value).replace(/[&<>"']/g, (character) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
}[character] ?? character));

export function executiveReportFilename(reportId: string): string {
  return /^executive-report-[a-f0-9]{16}$/.test(reportId)
    ? `${reportId}.html`
    : "aegisai-executive-report.html";
}

export function renderExecutiveReportHtml(report: ExecutiveReport): string {
  const countRows = [
    ...Object.entries(report.finding_counts.by_severity).map(([key, count]) => ["Severity", key, count]),
    ...Object.entries(report.finding_counts.by_status).map(([key, count]) => ["Status", key, count]),
  ].map(([group, name, count]) => `<tr><th>${escapeHtml(group)}</th><td>${escapeHtml(name)}</td><td>${escapeHtml(count)}</td></tr>`).join("");

  const findings = report.inferred_risks.length
    ? report.inferred_risks.map((risk) => `<article class="finding">
        <h3>${escapeHtml(risk.rule_id)} <span>${escapeHtml(risk.severity)}</span></h3>
        <p><b>Finding ID:</b> ${escapeHtml(risk.finding_id)} · <b>Status:</b> ${escapeHtml(risk.status)} · <b>Confidence:</b> ${escapeHtml((risk.confidence * 100).toFixed(0))}%</p>
        <p><b>Asset:</b> ${escapeHtml(risk.asset_ref)}</p>
        <p><b>First seen:</b> ${escapeHtml(risk.first_seen_utc)} · <b>Last seen:</b> ${escapeHtml(risk.last_seen_utc)}</p>
        <p>${escapeHtml(risk.explanation)}</p>
        <h4>Evidence references</h4>
        <ul>${risk.evidence_refs.map((reference) => `<li>${escapeHtml(reference)}</li>`).join("")}</ul>
      </article>`).join("")
    : "<p>No inferred risks were included in this report.</p>";

  const timeline = report.timeline.length
    ? `<ol>${report.timeline.map((entry) => `<li><time>${escapeHtml(entry.occurred_at_utc)}</time> — ${escapeHtml(entry.event_type)} (${escapeHtml(entry.event_id)}); evidence ${escapeHtml(entry.evidence_ref)}; findings ${entry.finding_ids.map(escapeHtml).join(", ")}</li>`).join("")}</ol>`
    : "<p>No timestamped evidence is available for a timeline.</p>";
  const priority = { critical: 0, high: 1, medium: 2, low: 3 } as const;
  const riskById = new Map(report.inferred_risks.map((risk) => [risk.finding_id, risk]));
  const prioritizedRecommendations = [...report.recommendations].sort((left, right) =>
    (priority[riskById.get(left.finding_id)?.severity ?? "low"] - priority[riskById.get(right.finding_id)?.severity ?? "low"])
    || left.finding_id.localeCompare(right.finding_id));
  const recommendations = prioritizedRecommendations.length
    ? `<ul>${prioritizedRecommendations.map((item) => `<li><b>${escapeHtml(riskById.get(item.finding_id)?.severity ?? "Unranked")} priority · ${escapeHtml(item.category === "investigation" ? "Manual investigation" : "Manual remediation recommendation")}</b> — ${escapeHtml(item.text)} <span>(Finding ${escapeHtml(item.finding_id)})</span></li>`).join("")}</ul><p>Priority order is a display aid based on associated synthetic finding severity only; no remediation is performed.</p>`
    : "<p>No recommendations were included.</p>";

  return `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>AegisAI Executive Report — ${escapeHtml(report.report_id)}</title>
<style>
  :root{color-scheme:light}*{box-sizing:border-box}body{max-width:920px;margin:40px auto;padding:0 28px;color:#172033;font:16px/1.6 Arial,Helvetica,sans-serif}header{border-bottom:3px solid #158b79;padding-bottom:18px}h1{font-size:30px;margin:4px 0}h2{font-size:21px;margin:30px 0 10px}h3{font-size:17px;margin:0 0 8px}h4{font-size:14px;margin:14px 0 4px}.label{display:inline-block;padding:6px 10px;border:1px solid #147c6d;border-radius:5px;color:#075f53;font-size:13px;font-weight:bold;letter-spacing:.04em}.warning{margin:18px 0;padding:14px;border-left:5px solid #7b3fa1;background:#f4eff8;font-weight:bold}.meta{color:#49556b;font-size:14px}.finding{margin:14px 0;padding:16px;border:1px solid #cbd3df;border-radius:7px;break-inside:avoid}.finding h3 span{float:right;text-transform:uppercase}.finding p{margin:7px 0}table{width:100%;border-collapse:collapse}th,td{text-align:left;padding:8px;border:1px solid #cbd3df}th{background:#f2f5f8}li{margin:6px 0}time{font-variant-numeric:tabular-nums}.foot{margin-top:35px;padding-top:12px;border-top:1px solid #cbd3df;color:#4b5668;font-size:13px}@media print{body{max-width:none;margin:0;padding:0 12mm}h2{break-after:avoid}.finding{break-inside:avoid}}
</style></head><body>
<header><span class="label">${escapeHtml(report.label)} · SYNTHETIC</span><h1>AegisAI Executive Incident Report</h1>
<p class="meta"><b>Report ID:</b> ${escapeHtml(report.report_id)}<br><b>Generated:</b> ${escapeHtml(report.generated_at_utc)}<br><b>Classification:</b> ${escapeHtml(report.data_classification)}</p></header>
<p class="warning">Synthetic data only. This report is not evidence of real-world compromise, exploitability, or detection accuracy.</p>
<main><section><h2>Executive summary</h2><p>${escapeHtml(report.executive_summary)}</p></section>
<section><h2>Finding counts</h2><table><thead><tr><th>Group</th><th>Value</th><th>Count</th></tr></thead><tbody>${countRows}</tbody></table></section>
<section><h2>Inferred risks</h2>${findings}<p><b>Confirmed findings:</b> ${escapeHtml(report.confirmed_findings.length)}. Inferred risks remain distinct and have not been promoted to confirmed findings.</p></section>
<section><h2>Chronological timeline</h2>${timeline}</section>
<section><h2>Manual recommendations</h2>${recommendations}</section>
<section><h2>Limitations</h2><ul>${report.limitations.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul></section></main>
<footer class="foot">Generated locally from the validated authenticated dashboard response. No credentials or raw telemetry are included.</footer></body></html>`;
}

export function downloadExecutiveReport(report: ExecutiveReport): void {
  const blob = new Blob([renderExecutiveReportHtml(report)], { type: "text/html;charset=utf-8" });
  const objectUrl = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = objectUrl;
  link.download = executiveReportFilename(report.report_id);
  link.hidden = true;
  document.body.appendChild(link);
  try {
    link.click();
  } finally {
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(objectUrl), 0);
  }
}
