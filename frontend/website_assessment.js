'use strict';

const assessmentInput = document.getElementById('assessment-file');
const assessmentStatus = document.getElementById('assessment-status');
const assessmentResults = document.getElementById('assessment-results');
const escapeAssessmentText = value => String(value).replace(/[&<>"']/g, char => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
}[char]));

function readAssessment(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      try {
        const report = JSON.parse(String(reader.result));
        const valid = report && report.schema_version === '1.0'
          && report.assessment_type === 'http_security_header_check'
          && report.url === 'http://127.0.0.1:8765/'
          && ['baseline', 'hardened'].includes(report.profile)
          && Array.isArray(report.header_results)
          && Array.isArray(report.findings)
          && Array.isArray(report.limitations);
        if (!valid) throw new Error(`${file.name} is not a supported local header assessment.`);
        resolve(report);
      } catch (error) {
        reject(error);
      }
    };
    reader.onerror = () => reject(new Error(`Could not read ${file.name}.`));
    reader.readAsText(file);
  });
}

function renderReport(report) {
  const headers = report.header_results.map(item => `
    <div class="assessment-row">
      <strong>${escapeAssessmentText(item.header)}</strong>
      <span class="${item.present ? 'ok' : 'finding-state'}">${item.present ? 'PRESENT' : 'MISSING / INCORRECT'}</span>
      <div class="muted">Expected: <code>${escapeAssessmentText(item.expected_value)}</code></div>
    </div>`).join('');
  const findings = report.findings.map(item => `
    <article class="finding">
      <div class="finding-title"><strong>${escapeAssessmentText(item.title)}</strong><span class="badge">${escapeAssessmentText(item.severity)}</span></div>
      <p>${escapeAssessmentText(item.description)}</p>
      <p><b>Evidence:</b> ${escapeAssessmentText(item.evidence)}</p>
      <p><b>Remediation:</b> ${escapeAssessmentText(item.remediation)}</p>
    </article>`).join('');
  const limitations = report.limitations.map(escapeAssessmentText).join(' ');
  return `<section class="assessment-report"><h3>${escapeAssessmentText(report.profile)} profile · ${escapeAssessmentText(report.status)}</h3><p class="muted">${escapeAssessmentText(report.checked_at_utc)} · ${report.finding_count} finding(s)</p><div class="assessment-grid">${headers}</div>${findings ? `<h4>Findings</h4>${findings}` : '<p class="ok">No missing checked headers.</p>'}<p class="muted">${limitations}</p></section>`;
}

function renderComparison(reports) {
  if (reports.length < 2) return '';
  const baseline = reports.find(report => report.profile === 'baseline');
  const hardened = reports.find(report => report.profile === 'hardened');
  if (!baseline || !hardened) return '<p class="muted">Load one baseline and one hardened report to compare them.</p>';

  const baselineIds = new Set(baseline.findings.map(item => item.id));
  const hardenedIds = new Set(hardened.findings.map(item => item.id));
  const resolved = [...baselineIds].filter(id => !hardenedIds.has(id));
  const remaining = [...hardenedIds];
  return `<div class="comparison"><strong>Before / after:</strong> ${resolved.length} finding(s) resolved; ${remaining.length} remain in the hardened report.</div>`;
}

assessmentInput.addEventListener('change', async () => {
  const files = [...(assessmentInput.files || [])];
  assessmentResults.replaceChildren();
  if (!files.length) {
    assessmentStatus.textContent = 'No website assessment loaded.';
    return;
  }
  try {
    const reports = await Promise.all(files.map(readAssessment));
    if (reports.length > 2 || new Set(reports.map(report => report.profile)).size !== reports.length) {
      throw new Error('Select one report per profile (baseline and/or hardened).');
    }
    assessmentStatus.textContent = `${reports.length} report(s) loaded for ${reports[0].url}.`;
    assessmentResults.innerHTML = `${renderComparison(reports)}${reports.map(renderReport).join('')}`;
  } catch (error) {
    assessmentStatus.textContent = error.message;
    assessmentResults.replaceChildren();
  }
});
