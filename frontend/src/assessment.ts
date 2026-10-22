import type { AssessmentFinding, AssessmentReport } from "./types";
import { MAX_ARTIFACT_BYTES, readBoundedResponseText } from "./researchArtifact";

const REQUIRED_HEADERS = [
  "Content-Security-Policy", "X-Content-Type-Options", "Referrer-Policy", "Permissions-Policy",
];

const object = (value: unknown): value is Record<string, unknown> =>
  value !== null && typeof value === "object" && !Array.isArray(value);

export function validateAssessmentReport(report: unknown, sourceName = "Report"): AssessmentReport {
  const candidate = report as Partial<AssessmentReport> | null;
  const findings = candidate?.findings;
  const findingIds = Array.isArray(findings) ? findings.map((item) => (item as AssessmentFinding | null)?.id) : [];
  const valid = object(report)
    && candidate?.schema_version === "1.0"
    && candidate.assessment_type === "http_security_header_check"
    && candidate.url === "http://127.0.0.1:8765/"
    && ["baseline", "hardened"].includes(String(candidate.profile))
    && ["passed", "findings"].includes(String(candidate.status))
    && Array.isArray(candidate.checked_headers) && candidate.checked_headers.length === 4
    && new Set(candidate.checked_headers).size === 4
    && REQUIRED_HEADERS.every((header) => candidate.checked_headers?.includes(header))
    && Array.isArray(candidate.header_results) && candidate.header_results.length === 4
    && new Set(candidate.header_results.map((item) => object(item) ? item.header : undefined)).size === 4
    && REQUIRED_HEADERS.every((header) => candidate.header_results?.some((item) => object(item) && item.header === header))
    && candidate.header_results.every((item) => object(item)
      && typeof item.header === "string" && typeof item.expected_value === "string"
      && typeof item.present === "boolean"
      && (item.observed_value === null || typeof item.observed_value === "string"))
    && Array.isArray(findings) && findingIds.every((id) => typeof id === "string")
    && new Set(findingIds).size === findingIds.length
    && Number.isInteger(candidate.finding_count) && candidate.finding_count === findings.length
    && typeof candidate.ok === "boolean" && candidate.ok === (candidate.finding_count === 0)
    && candidate.status === (candidate.ok ? "passed" : "findings")
    && findings.every((item) => object(item)
      && ["id", "severity", "title", "description", "evidence", "remediation"].every((key) => typeof item[key] === "string"))
    && Array.isArray(candidate.limitations) && candidate.limitations.every((item) => typeof item === "string");
  if (!valid) throw new Error(`${sourceName} is not a supported local header assessment.`);
  return candidate as AssessmentReport;
}

export function parseAssessmentReport(text: string, sourceName = "Report"): AssessmentReport {
  if (new TextEncoder().encode(text).byteLength > MAX_ARTIFACT_BYTES) {
    throw new Error(`${sourceName} exceeds the 1 MB size limit.`);
  }
  let report: unknown;
  try {
    report = JSON.parse(text);
  } catch {
    throw new Error(`${sourceName} is not valid JSON.`);
  }
  return validateAssessmentReport(report, sourceName);
}

export async function readAssessmentFile(file: File): Promise<AssessmentReport> {
  if (file.size > MAX_ARTIFACT_BYTES) throw new Error(`${file.name} is too large (maximum 1 MB).`);
  return parseAssessmentReport(await file.text(), file.name);
}

export async function readAssessmentResponse(response: Response, sourceName: string): Promise<AssessmentReport> {
  if (!response.ok) throw new Error(`Could not load ${sourceName} (${response.status}).`);
  return parseAssessmentReport(await readBoundedResponseText(response), sourceName);
}

export function compareAssessmentReports(reports: AssessmentReport[]): { resolved: number; remaining: number } | null {
  if (reports.length < 2) return null;
  const baseline = reports.find((report) => report.profile === "baseline");
  const hardened = reports.find((report) => report.profile === "hardened");
  if (!baseline || !hardened) return null;
  const hardenedIds = new Set(hardened.findings.map((finding) => finding.id));
  return {
    resolved: baseline.findings.filter((finding) => !hardenedIds.has(finding.id)).length,
    remaining: hardened.findings.length,
  };
}
