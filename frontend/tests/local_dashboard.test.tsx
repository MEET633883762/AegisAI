import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { LocalDashboard } from "../src/localDashboard/LocalDashboard";
import { downloadExecutiveReport, executiveReportFilename, renderExecutiveReportHtml } from "../src/localDashboard/executiveReportExport";
import type { ExecutiveReport } from "../src/localDashboard/types";

const finding = (overrides: Record<string, unknown> = {}) => ({
  finding_id: "tfinding-aaaaaaaaaaaa", rule_id: "AUTH-001", rule_version: "1.0", severity: "high", confidence: 0.92,
  first_seen_utc: "2026-10-22T08:00:00Z", last_seen_utc: "2026-10-22T08:05:00Z", asset_ref: "synthetic-web-1",
  evidence_refs: ["synthetic-evidence-1"], event_ids: ["syn-auth-1"], explanation: "Synthetic repeated authentication failures.",
  confidence_factors: ["allowlisted synthetic authentication events"], status: "open", ...overrides,
});
const assessmentPayload = {
  data_classification: "synthetic", label: "LOCAL SYNTHETIC WEBSITE ASSESSMENT", tenant_id: "synthetic-org-demo",
  history: [] as { report_id: string; generated_at_utc: string; inferred_risk_count: number; confirmed_finding_count: number;
    comparison_status: "baseline" | "compared" | null; previous_report_id: string | null;
    newly_introduced_count: number; resolved_count: number }[],
  report: {
    schema_version: "1.0", report_id: "assessment-report-0123456789abcdef", generated_at_utc: "2026-10-22T08:10:00Z",
    data_classification: "synthetic", label: "LOCAL SYNTHETIC WEBSITE ASSESSMENT", duplicate_observation_count: 0,
    raw_observations: [{ check_id: "security_headers_v1", decision: { check_id: "security_headers_v1", target_origin: "http://127.0.0.1:8767", allowed: true, reason_code: "approved" }, outcome: "headers_observed", duration_ms: 20, error_category: null, facts: { "content-security-policy": null }, evidence: { evidence_ref: "assessment-evidence-0123456789abcdef01234567", source: "loopback_http_response", observed_at_utc: "2026-10-22T08:09:59Z", request_method: "GET", request_path: "/", response_status: 200, response_bytes: 10, response_sha256: "a".repeat(64) } }],
    inferred_risks: [{ issue_id: "assessment-issue-0123456789abcdef", check_id: "security_headers_v1", classification: "inferred_risk", title: "<img src=x onerror=alert(1)>", rationale: "Review this synthetic observation.", evidence_refs: ["assessment-evidence-0123456789abcdef01234567"] }],
    confirmed_findings: [], limitations: ["Synthetic loopback observations only."],
  },
};
const evalMetric = { value: 0.5, denominator: 2, status: "defined" };
const evaluationPayload = {
  data_classification: "synthetic", label: "SYNTHETIC EVALUATION - NOT REAL SECURITY PERFORMANCE", tenant_id: "synthetic-org-demo",
  report: {
    schema_version: "1.1", report_type: "aegisai_synthetic_detection_evaluation_report", dataset_id: "aegisai-evaluation-v1", dataset_version: "1.0",
    dataset_sha256: "b".repeat(64), detector_config_sha256: "c".repeat(64), counting_unit: "one scenario-by-supported-rule pair",
    rule_catalog_version: "1.0", detector_rule_version: "1.0", scenario_rule_mapping_version: "1.0", attack_mapping_catalog_version: "1.0",
    counts: { true_positives: 1, true_negatives: 2, false_positives: 0, false_negatives: 1 },
    metrics: { precision: evalMetric, recall: evalMetric, f1: evalMetric, specificity: evalMetric, false_positive_rate: evalMetric, false_negative_rate: evalMetric },
    total_evaluated_pairs: 4,
    per_rule: [{ rule_id: "AUTH-001", counts: { true_positives: 1, true_negatives: 2, false_positives: 0, false_negatives: 1 }, metrics: { precision: evalMetric, recall: evalMetric, f1: evalMetric, specificity: evalMetric, false_positive_rate: evalMetric, false_negative_rate: evalMetric } }],
    rule_event_mapping: [{ rule_id: "AUTH-001", event_types: ["auth_failure"] }],
    scenario_rule_mapping: [{ scenario_id: "p6a-auth-boundary", expected_rule_ids: ["AUTH-001"], evaluated_rule_ids: ["AUTH-001"], observed_rule_ids: ["AUTH-001"], technique_ids: [], status: "pass" }],
    technique_coverage: [], untested_techniques: [{ technique_id: "T1110", name: "Brute Force", status: "candidate_not_mapped", rationale: "Auth failure examples do not encode credential guessing." }],
    coverage_status: "partial", warnings: ["Small synthetic sample."], history: [],
    valid_scenario_count: 1, rejected_scenario_count: 2, limitations: ["Synthetic scenarios only."],
  },
};
const executivePayload = {
  data_classification: "synthetic", label: "SYNTHETIC - NOT REAL CLIENT DATA", tenant_id: "synthetic-org-demo",
  report: {
    schema_version: "1.0", report_type: "aegisai_executive_incident_report", report_id: "executive-report-0123456789abcdef",
    tenant_id: "synthetic-org-demo", generated_at_utc: "2026-10-22T08:15:00Z", data_classification: "synthetic",
    label: "SYNTHETIC - NOT REAL CLIENT DATA", executive_summary: "One synthetic inferred risk requires human review.",
    finding_counts: { by_severity: { low: 0, medium: 0, high: 1, critical: 0 }, by_status: { open: 1, acknowledged: 0, closed: 0 } },
    observations: [{ evidence_ref: "synthetic-evidence-1", event_id: "syn-auth-1", event_type: "auth_failure", occurred_at_utc: "2026-10-22T08:00:00Z", related_finding_ids: ["tfinding-aaaaaaaaaaaa"] }],
    inferred_risks: [{ classification: "inferred_risk", finding_id: "tfinding-aaaaaaaaaaaa", rule_id: "AUTH-001", severity: "high", confidence: 0.92,
      status: "open", first_seen_utc: "2026-10-22T08:00:00Z", last_seen_utc: "2026-10-22T08:05:00Z", asset_ref: "synthetic-web-1",
      explanation: '<img src=x onerror="alert(1)">', confidence_factors: ["synthetic evidence"], evidence_refs: ["synthetic-evidence-1"] }],
    confirmed_findings: [],
    timeline: [{ occurred_at_utc: "2026-10-22T08:00:00Z", evidence_ref: "synthetic-evidence-1", event_id: "syn-auth-1", event_type: "auth_failure", finding_ids: ["tfinding-aaaaaaaaaaaa"] }],
    recommendations: [{ category: "investigation", finding_id: "tfinding-aaaaaaaaaaaa", text: "Review the evidence manually." },
      { category: "remediation", finding_id: "tfinding-aaaaaaaaaaaa", text: "Plan changes only after independent confirmation." }],
    limitations: ["Synthetic data only; no real-world accuracy claim."],
  },
};

const basePayloads: Record<string, unknown> = {
  "/health": { status: "ok", mode: "local_synthetic" },
  "/api/telemetry/findings": { data_classification: "synthetic", label: "SYNTHETIC - NOT REAL CLIENT DATA", tenant_id: "synthetic-org-demo", findings: [finding()] },
  "/api/processing": { data_classification: "synthetic", label: "SYNTHETIC - NOT REAL CLIENT DATA", tenant_id: "synthetic-org-demo", scheduler_state: "running", interval_seconds: 600, latest_run: {
    run_id: "trun-aaaaaaaaaaaaaaaa", source_id: "local_synthetic_fixture_v1", status: "completed", scheduled_at_utc: "2026-10-22T08:00:00Z", started_at_utc: "2026-10-22T08:00:00Z", completed_at_utc: "2026-10-22T08:00:01Z", attempt: 1, input_event_count: 5, accepted_event_count: 4, duplicate_event_count: 1, finding_count: 1, error_code: null,
  } },
  "/api/telemetry/sources/live-website/status": { data_classification: "synthetic", label: "SYNTHETIC - NOT REAL CLIENT DATA", tenant_id: "synthetic-org-demo", source_key: "synthetic_demo_site_live_logs_v1", last_attempt_at_utc: "2026-10-22T08:00:00Z", last_success_at_utc: "2026-10-22T08:00:00Z", status: "healthy", input_event_count: 5, accepted_event_count: 4, duplicate_event_count: 1, rejected_record_count: 0, position_sha256: "a".repeat(64), position_bytes: 100, error_code: null },
  "/api/telemetry/findings/tfinding-aaaaaaaaaaaa/evidence": { data_classification: "synthetic", label: "SYNTHETIC - NOT REAL CLIENT DATA", tenant_id: "synthetic-org-demo", finding_id: "tfinding-aaaaaaaaaaaa", evidence: [{ evidence_ref: "synthetic-evidence-1", event_id: "syn-auth-1", event_type: "auth_failure", occurred_at_utc: "2026-10-22T08:00:00Z", asset_ref: "synthetic-web-1", actor_ref: "synthetic-actor-1", source_ref: "synthetic-source-1" }] },
  "/api/assessment/reports/latest": assessmentPayload,
  "/api/evaluation/reports/latest": evaluationPayload,
  "/api/reports/executive/latest": executivePayload,
  "/api/investigations/cases": { data_classification: "synthetic", label: "SYNTHETIC - HUMAN-LED INVESTIGATION", tenant_id: "synthetic-org-demo", cases: [{ case_id: "case-0123456789abcdef", title: "Synthetic auth review", status: "under_review", created_at_utc: "2026-10-22T08:00:00Z", updated_at_utc: "2026-10-22T08:05:00Z", finding_count: 1, evidence_count: 1 }] },
  "/api/purple-team/scenarios/runs": { data_classification: "synthetic", label: "SYNTHETIC LOCAL SCENARIO HISTORY - NOT A REAL-WORLD CONTROL TEST", tenant_id: "synthetic-org-demo", runs: [] },
  "/api/investigations/cases/case-0123456789abcdef": { data_classification: "synthetic", label: "SYNTHETIC - HUMAN-LED INVESTIGATION", tenant_id: "synthetic-org-demo", case: {
    case_id: "case-0123456789abcdef", title: "Synthetic auth review", status: "under_review", created_at_utc: "2026-10-22T08:00:00Z", updated_at_utc: "2026-10-22T08:05:00Z", finding_count: 1, evidence_count: 1,
    findings: [{ finding_id: "tfinding-aaaaaaaaaaaa", relationship: "inferred_relationship", rationale: "Possible related activity.", linked_at_utc: "2026-10-22T08:01:00Z" }],
    evidence: [{ finding_id: "tfinding-aaaaaaaaaaaa", evidence_ref: "synthetic-evidence-1", rationale: "Existing stored event.", linked_at_utc: "2026-10-22T08:02:00Z" }],
    notes: [{ classification: "unresolved_hypothesis", text: "<img src=x onerror=alert(1)> requires independent review.", created_at_utc: "2026-10-22T08:03:00Z" }],
    context: [], timeline: [{ occurred_at_utc: "2026-10-22T08:02:00Z", category: "evidence", reference_id: "synthetic-evidence-1", description: "Verified stored event syn-auth-1.", classification: "verified_evidence" }], recommendations: [{ category: "investigation", text: "Review the evidence manually.", supporting_finding_ids: ["tfinding-aaaaaaaaaaaa"] }],
  } },
};

beforeEach(() => {
  window.history.replaceState(null, "", window.location.pathname);
  basePayloads["/api/telemetry/findings"] = { data_classification: "synthetic", label: "SYNTHETIC - NOT REAL CLIENT DATA", tenant_id: "synthetic-org-demo", findings: [finding()] };
  basePayloads["/api/evaluation/reports/latest"] = evaluationPayload;
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const route = new URL(String(input)).pathname;
    const payload = basePayloads[route];
    if (!payload) return new Response(JSON.stringify({ error: "not_found" }), { status: 404 });
    if (route !== "/health") expect((init?.headers as Record<string, string>)?.Authorization).toBe("Bearer demo-token");
    return new Response(JSON.stringify(payload), { status: 200, headers: { "Content-Type": "application/json" } });
  }));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

async function connect() {
  fireEvent.change(screen.getByLabelText("Startup bearer token"), { target: { value: "demo-token" } });
  fireEvent.click(screen.getByRole("button", { name: "Connect" }));
  await screen.findByText("AUTH-001", { selector: ".recent-main b" });
}

describe("local synthetic dashboard", () => {
  it("returns to Overview when browser Back restores the unfragmented URL", async () => {
    render(<LocalDashboard />);
    fireEvent.click(screen.getByRole("button", { name: "Cases" }));
    expect(window.location.hash).toBe("#investigations");
    window.history.back();
    await screen.findByRole("heading", { name: "Security command center", level: 1 });
    expect(window.location.hash).toBe("");
  });

  it("opens a linked section and follows browser history without persisting a session", async () => {
    window.history.replaceState(null, "", "#detection");
    const page = render(<LocalDashboard />);
    expect(screen.getByRole("heading", { name: "Detection Lab", level: 1 })).toBeTruthy();
    expect(fetch).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Assessment" }));
    expect(window.location.hash).toBe("#assessment");
    expect(document.activeElement).toBe(screen.getByRole("heading", { name: "Assessment", level: 1 }));
    window.history.back();
    await screen.findByRole("heading", { name: "Detection Lab", level: 1 });
    page.unmount();
    render(<LocalDashboard />);
    expect(screen.getByRole("heading", { name: "Detection Lab", level: 1 })).toBeTruthy();
    expect(screen.getByLabelText("Startup bearer token")).toBeTruthy();
    expect(fetch).not.toHaveBeenCalled();
    expect(window.location.hash).not.toContain("token");
  });

  it("opens a recent finding in the queue and clears filters that would hide it", async () => {
    render(<LocalDashboard />);
    await connect();
    fireEvent.click(screen.getByRole("button", { name: "Findings" }));
    fireEvent.change(screen.getByLabelText("Severity"), { target: { value: "low" } });
    fireEvent.click(screen.getByRole("button", { name: "Overview" }));
    fireEvent.click(screen.getByRole("button", { name: /AUTH-001/ }));
    expect(window.location.hash).toBe("#findings");
    expect(screen.getByRole("heading", { name: "Investigation detail" })).toBeTruthy();
    expect(await screen.findByText("synthetic-evidence-1")).toBeTruthy();
    expect((screen.getByLabelText("Severity") as HTMLSelectElement).value).toBe("all");
    expect(screen.getByRole("button", { name: /AUTH-001/ }).getAttribute("aria-pressed")).toBe("true");
  });

  it("clears all finding filters in one step and restores the full queue", async () => {
    render(<LocalDashboard />);
    await connect();
    fireEvent.click(screen.getByRole("button", { name: "Findings" }));
    fireEvent.change(screen.getByLabelText("Search findings"), { target: { value: "unmatched" } });
    fireEvent.change(screen.getByLabelText("Severity"), { target: { value: "low" } });
    fireEvent.change(screen.getByLabelText("Type"), { target: { value: "AUTH-001" } });
    fireEvent.change(screen.getByLabelText("Status"), { target: { value: "closed" } });
    expect(screen.getByText("Showing 0 of 1 findings")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Clear filters" }));
    expect(screen.getByText("Showing 1 of 1 findings")).toBeTruthy();
    expect((screen.getByLabelText("Search findings") as HTMLInputElement).value).toBe("");
    for (const label of ["Severity", "Type", "Status"]) expect((screen.getByLabelText(label) as HTMLSelectElement).value).toBe("all");
    expect(screen.getByRole("button", { name: /AUTH-001/ })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Clear filters" })).toBeNull();
  });

  it("distinguishes a valid empty finding queue from filters that hide findings", async () => {
    basePayloads["/api/telemetry/findings"] = { data_classification: "synthetic", label: "SYNTHETIC - NOT REAL CLIENT DATA", tenant_id: "synthetic-org-demo", findings: [] };
    render(<LocalDashboard />);
    fireEvent.change(screen.getByLabelText("Startup bearer token"), { target: { value: "demo-token" } });
    fireEvent.click(screen.getByRole("button", { name: "Connect" }));
    await screen.findByText("No synthetic findings are currently returned for this tenant.");
    fireEvent.click(screen.getByRole("button", { name: "Findings" }));
    expect(screen.getByRole("heading", { name: "No findings yet" })).toBeTruthy();
    expect(screen.queryByText("No matching findings")).toBeNull();
    expect(screen.getByText("Showing 0 of 0 findings")).toBeTruthy();
  });

  it("shows disclosure and no findings until a local token is supplied", () => {
    render(<LocalDashboard />);
    expect(screen.getByText(/Synthetic local prototype/)).toBeTruthy();
    expect(screen.getByText("Connect to view local data")).toBeTruthy();
    expect(document.querySelectorAll(".ops-metric strong")).toHaveLength(5);
    expect(Array.from(document.querySelectorAll(".ops-metric strong")).every((item) => item.textContent === "—")).toBe(true);
    expect(screen.queryByText("Synthetic repeated authentication failures.")).toBeNull();
  });

  it("loads only local API results and displays derived counters", async () => {
    render(<LocalDashboard />);
    await connect();
    const metricValues = Array.from(document.querySelectorAll(".ops-metric strong")).map((element) => element.textContent);
    expect(metricValues).toEqual(["1", "1", "4", "1", "0"]);
    expect((fetch as unknown as ReturnType<typeof vi.fn>).mock.calls.every(([url]) => String(url).startsWith("http://127.0.0.1:8766/"))).toBe(true);
  });

  it("renders the tenant assessment report as text with decisions, observations, and evidence", async () => {
    render(<LocalDashboard />);
    await connect();
    fireEvent.click(screen.getByRole("button", { name: "Assessment" }));
    expect(await screen.findByText("security_headers_v1")).toBeTruthy();
    expect(screen.getByText("assessment-evidence-0123456789abcdef01234567")).toBeTruthy();
    expect(screen.getByText("Allowed · approved")).toBeTruthy();
    expect(screen.getByText("http://127.0.0.1:8767")).toBeTruthy();
    expect(screen.getByText("<img src=x onerror=alert(1)>")).toBeTruthy();
    expect(document.querySelector(".ops-assessment-issues img")).toBeNull();
  });

  it("renders versioned assessment outcomes, expected results, provenance, and comparison state", async () => {
    const payload = structuredClone(assessmentPayload);
    payload.history = [{ report_id: "assessment-report-0123456789abcdef", generated_at_utc: "2026-10-22T08:10:00Z",
      inferred_risk_count: 1, confirmed_finding_count: 0, comparison_status: "compared",
      previous_report_id: "assessment-report-fedcba9876543210", newly_introduced_count: 1, resolved_count: 0 }];
    Object.assign(payload.report, {
      schema_version: "2.0", run_id: "1234567890abcdef1234567890abcdef",
      started_at_utc: "2026-10-22T08:09:58Z", configuration_version: "local-website-config-v1",
      check_catalog_version: "local-web-checks-v1", provenance: "fixed_loopback_synthetic_website",
      comparison: { status: "baseline", previous_report_id: null, newly_introduced: [], resolved: [], unchanged: [] },
    });
    Object.assign(payload.report.raw_observations[0], {
      category: "response_security", description: "Observe local response headers.", severity: "medium",
      check_version: "1.0", configuration_version: "local-website-config-v1",
      expected_result: "Security headers are present.", observed_result: "Not observed: content-security-policy.",
      outcome_status: "FAIL", observed_at_utc: "2026-10-22T08:09:59Z",
    });
    Object.assign(payload.report.inferred_risks[0], {
      severity: "medium", recommendation: "Review the local response header configuration manually.",
    });
    basePayloads["/api/assessment/reports/latest"] = payload;
    render(<LocalDashboard />);
    await connect();
    fireEvent.click(screen.getByRole("button", { name: "Assessment" }));
    expect(await screen.findByText("FAIL")).toBeTruthy();
    expect(screen.getByText(/Expected: Security headers are present/)).toBeTruthy();
    expect(screen.getByText(/Catalog local-web-checks-v1/)).toBeTruthy();
    expect(screen.getByText(/No prior valid report was available/)).toBeTruthy();
    expect(screen.getByText(/1 introduced; 0 resolved/)).toBeTruthy();
  });

  it("renders the authenticated executive report, evidence links, and safe text", async () => {
    render(<LocalDashboard />);
    await connect();
    fireEvent.click(screen.getByRole("button", { name: "Executive Reports" }));
    expect(await screen.findByText("One synthetic inferred risk requires human review.")).toBeTruthy();
    expect(screen.getByText(/Generated/)).toBeTruthy();
    expect(screen.getByText("Inferred risks")).toBeTruthy();
    expect(screen.getByText("AUTH-001")).toBeTruthy();
    expect(screen.getByText("synthetic-evidence-1").getAttribute("href")).toBe("#executive-evidence-synthetic-evidence-1");
    expect(screen.getByText('<img src=x onerror="alert(1)">')).toBeTruthy();
    expect(document.querySelector(".ops-executive-risk img")).toBeNull();
    expect(screen.getByText(/do not establish real-world compromise/)).toBeTruthy();
    const calls = (fetch as unknown as ReturnType<typeof vi.fn>).mock.calls;
    const executiveCall = calls.find(([url]) => String(url).endsWith("/api/reports/executive/latest"));
    expect(executiveCall).toBeTruthy();
    expect((executiveCall?.[1] as RequestInit).headers).toEqual({ Authorization: "Bearer demo-token" });
  });

  it("exports required report sections with escaped API text and a safe filename", () => {
    const report = executivePayload.report as unknown as ExecutiveReport;
    const html = renderExecutiveReportHtml(report);
    expect(html).toContain("AegisAI Executive Incident Report");
    expect(html).toContain("executive-report-0123456789abcdef");
    expect(html).toContain("Executive summary");
    expect(html).toContain("Finding counts");
    expect(html).toContain("Inferred risks");
    expect(html).toContain("Chronological timeline");
    expect(html).toContain("Manual recommendations");
    expect(html).toContain("Limitations");
    expect(html).toContain("&lt;img src=x onerror=&quot;alert(1)&quot;&gt;");
    expect(html).not.toContain('<img src=x onerror="alert(1)">');
    expect(html).toContain("not evidence of real-world compromise");
    expect(executiveReportFilename("executive-report-0123456789abcdef")).toBe("executive-report-0123456789abcdef.html");
    expect(executiveReportFilename("../../secret")).toBe("aegisai-executive-report.html");
  });

  it("downloads a self-contained HTML blob and revokes its object URL", () => {
    const createUrl = vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:executive-report");
    const revokeUrl = vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => undefined);
    let downloadedName = "";
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) {
      downloadedName = this.download;
    });
    vi.useFakeTimers();
    downloadExecutiveReport(executivePayload.report as unknown as ExecutiveReport);
    expect(createUrl.mock.calls[0][0]).toBeInstanceOf(Blob);
    expect((createUrl.mock.calls[0][0] as Blob).type).toBe("text/html;charset=utf-8");
    expect(downloadedName).toBe("executive-report-0123456789abcdef.html");
    expect(click).toHaveBeenCalledOnce();
    vi.runAllTimers();
    expect(revokeUrl).toHaveBeenCalledWith("blob:executive-report");
    vi.useRealTimers();
    createUrl.mockRestore(); revokeUrl.mockRestore(); click.mockRestore();
  });

  it("disables export and explains why no report is available", () => {
    render(<LocalDashboard />);
    fireEvent.click(screen.getByRole("button", { name: "Executive Reports" }));
    const download = screen.getByRole("button", { name: "Download HTML report" }) as HTMLButtonElement;
    expect(download.disabled).toBe(true);
    expect(screen.getByText("Download disabled: no validated report is loaded.")).toBeTruthy();
  });

  it("shows report loading and unavailable states", async () => {
    let release!: (response: Response) => void;
    const executiveResponse = new Promise<Response>((resolve) => { release = resolve; });
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const route = new URL(String(input)).pathname;
      if (route === "/api/reports/executive/latest") return executiveResponse;
      const payload = basePayloads[route];
      if (!payload) return new Response(JSON.stringify({ error: "not_found" }), { status: 404 });
      if (route !== "/health") expect((init?.headers as Record<string, string>)?.Authorization).toBe("Bearer demo-token");
      return new Response(JSON.stringify(payload), { status: 200 });
    }));
    render(<LocalDashboard />);
    fireEvent.change(screen.getByLabelText("Startup bearer token"), { target: { value: "demo-token" } });
    fireEvent.click(screen.getByRole("button", { name: "Connect" }));
    fireEvent.click(screen.getByRole("button", { name: "Executive Reports" }));
    expect(screen.getByText("Loading executive report")).toBeTruthy();
    release(new Response(JSON.stringify(executivePayload), { status: 200 }));
    expect(await screen.findByText("One synthetic inferred risk requires human review.")).toBeTruthy();

    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const route = new URL(String(input)).pathname;
      if (route === "/api/reports/executive/latest") return new Response(JSON.stringify({ error: "unavailable" }), { status: 503 });
      return new Response(JSON.stringify(basePayloads[route] ?? {}), { status: 200 });
    }));
    fireEvent.click(screen.getByRole("button", { name: /Refresh/ }));
    await waitFor(() => expect(screen.getByText(/could not refresh; the previously loaded report may be stale/i)).toBeTruthy());
  });

  it("shows an unavailable state when no executive report has loaded", async () => {
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const route = new URL(String(input)).pathname;
      if (route === "/api/reports/executive/latest") return new Response(JSON.stringify({ error: "unavailable" }), { status: 503 });
      return new Response(JSON.stringify(basePayloads[route] ?? {}), { status: 200 });
    }));
    render(<LocalDashboard />);
    await connect();
    fireEvent.click(screen.getByRole("button", { name: "Executive Reports" }));
    expect(screen.getByText("The local API returned status 503.")).toBeTruthy();
  });

  it("shows a valid empty executive report without inventing findings", async () => {
    const empty = { ...executivePayload, report: { ...executivePayload.report,
      executive_summary: "No synthetic findings were returned.",
      finding_counts: { by_severity: { low: 0, medium: 0, high: 0, critical: 0 }, by_status: { open: 0, acknowledged: 0, closed: 0 } },
      observations: [], inferred_risks: [], timeline: [], recommendations: [],
    } };
    basePayloads["/api/reports/executive/latest"] = empty;
    render(<LocalDashboard />);
    await connect();
    fireEvent.click(screen.getByRole("button", { name: "Executive Reports" }));
    expect(await screen.findByText("No synthetic findings")).toBeTruthy();
    expect(screen.getByText("Findings (0)")).toBeTruthy();
    expect(screen.queryByText("AUTH-001", { selector: ".ops-executive-risk b" })).toBeNull();
  });

  it("shows investigation provenance and renders note text safely", async () => {
    render(<LocalDashboard />);
    await connect();
    fireEvent.click(screen.getByRole("button", { name: "Cases" }));
    fireEvent.click(await screen.findByRole("button", { name: /Synthetic auth review/ }));
    expect(await screen.findByText(/Verified stored event syn-auth-1/)).toBeTruthy();
    expect(screen.getByText("verified_evidence", { selector: ".ops-case-timeline b" })).toBeTruthy();
    expect(screen.getByText(/<img src=x onerror=alert\(1\)> requires independent review\./)).toBeTruthy();
    expect(document.querySelector(".ops-investigation-grid img")).toBeNull();
    expect(screen.getByText(/Supporting findings: tfinding-aaaaaaaaaaaa/)).toBeTruthy();
  });

  it("shows empty and stale states for assessment report availability", async () => {
    basePayloads["/api/assessment/reports/latest"] = {
      data_classification: "synthetic", label: "LOCAL SYNTHETIC WEBSITE ASSESSMENT",
      tenant_id: "synthetic-org-demo", report: null, history: [],
    };
    render(<LocalDashboard />);
    await connect();
    fireEvent.click(screen.getByRole("button", { name: "Assessment" }));
    expect(await screen.findByText("No assessment report yet")).toBeTruthy();
    basePayloads["/api/assessment/reports/latest"] = assessmentPayload;
    fireEvent.click(screen.getByRole("button", { name: /Refresh/ }));
    await waitFor(() => expect(screen.getByText(/Report assessment-report-0123456789abcdef/)).toBeTruthy());
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const route = new URL(String(input)).pathname;
      if (route === "/api/assessment/reports/latest") return new Response(JSON.stringify({ error: "unavailable" }), { status: 503 });
      return new Response(JSON.stringify(basePayloads[route]), { status: 200 });
    }));
    fireEvent.click(screen.getByRole("button", { name: /Refresh/ }));
    await waitFor(() => expect(screen.getByText(/previously loaded assessment data/i)).toBeTruthy());
    expect(screen.getByText(/Report assessment-report-0123456789abcdef/)).toBeTruthy();
  });

  it("shows an unavailable source without a request error or fabricated counters", async () => {
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const route = new URL(String(input)).pathname;
      if (route === "/api/telemetry/sources/live-website/status") {
        return new Response(JSON.stringify({
          data_classification: "synthetic", label: "SYNTHETIC - NOT REAL CLIENT DATA", tenant_id: "synthetic-org-demo",
          source_key: "synthetic_demo_site_live_logs_v1", last_attempt_at_utc: null, last_success_at_utc: null,
          status: "unavailable", input_event_count: null, accepted_event_count: null, duplicate_event_count: null,
          rejected_record_count: null, position_sha256: null, position_bytes: null, error_code: null,
        }), { status: 200 });
      }
      const payload = basePayloads[route];
      if (!payload) return new Response(JSON.stringify({ error: "not_found" }), { status: 404 });
      if (route !== "/health") expect((init?.headers as Record<string, string>)?.Authorization).toBe("Bearer demo-token");
      return new Response(JSON.stringify(payload), { status: 200 });
    }));
    render(<LocalDashboard />);
    await connect();
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.getByText("AUTH-001", { selector: ".recent-main b" })).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "System Health" }));
    expect(screen.getByText("Unavailable")).toBeTruthy();
    expect(screen.getByText("Input").parentElement?.textContent).toContain("—");
  });

  it("keeps an optional source refresh failure separate and marks retained source data stale", async () => {
    render(<LocalDashboard />);
    await connect();
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const route = new URL(String(input)).pathname;
      if (route === "/api/telemetry/sources/live-website/status") return new Response(JSON.stringify({ error: "unavailable" }), { status: 503 });
      const payload = basePayloads[route];
      if (!payload) return new Response(JSON.stringify({ error: "not_found" }), { status: 404 });
      if (route !== "/health") expect((init?.headers as Record<string, string>)?.Authorization).toBe("Bearer demo-token");
      return new Response(JSON.stringify(payload), { status: 200 });
    }));
    fireEvent.click(screen.getByRole("button", { name: /Refresh/ }));
    await waitFor(() => expect(screen.getByText(/source status could not refresh/i)).toBeTruthy());
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.getByText("AUTH-001", { selector: ".recent-main b" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "System Health" }));
    expect(screen.getByText("The local API returned status 503.")).toBeTruthy();
    expect(screen.getByText("No status recorded")).toBeTruthy();
  });

  it("supports navigation, filtering, selection, and evidence inspection", async () => {
    render(<LocalDashboard />);
    await connect();
    fireEvent.click(screen.getByRole("button", { name: /Findings/ }));
    expect(screen.getByRole("heading", { name: "Finding queue" })).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Severity"), { target: { value: "low" } });
    expect(screen.getByText("No matching findings")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Severity"), { target: { value: "all" } });
    fireEvent.change(screen.getByLabelText("Status"), { target: { value: "closed" } });
    expect(screen.getByText("No matching findings")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Status"), { target: { value: "all" } });
    fireEvent.change(screen.getByLabelText("Search findings"), { target: { value: "no-match" } });
    expect(screen.getByText("No matching findings")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Search findings"), { target: { value: "AUTH-001" } });
    fireEvent.click(screen.getByRole("button", { name: /AUTH-001/ }));
    expect(await screen.findByText("synthetic-evidence-1")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Detection Lab" }));
    expect(screen.getByText("SYNTHETIC EVALUATION - NOT REAL SECURITY PERFORMANCE")).toBeTruthy();
    expect(screen.getByText("True positives")).toBeTruthy();
    expect(screen.getByText("True positives").closest(".ops-metric")?.querySelector("strong")?.textContent).toBe("1");
    expect(screen.getByText("True negatives").closest(".ops-metric")?.querySelector("strong")?.textContent).toBe("2");
    expect(screen.getByText("False negatives")).toBeTruthy();
    expect(screen.getByText("Total evaluated pairs").closest(".ops-metric")?.querySelector("strong")?.textContent).toBe("4");
    expect(screen.getByText("2 rejected scenarios (excluded)")).toBeTruthy();
    expect(screen.getAllByText("AUTH-001", { selector: "tbody td" })).toHaveLength(3);
    expect(screen.getByText("Specificity: 50.0% (2)")).toBeTruthy();
    expect(screen.getByText("p6a-auth-boundary")).toBeTruthy();
    expect(screen.getByText(/Untested candidate T1110 Brute Force/)).toBeTruthy();
    expect(screen.getByText(/Small synthetic sample/)).toBeTruthy();
  });

  it("shows a truthful unavailable state when the evaluation report cannot be read", async () => {
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const route = new URL(String(input)).pathname;
      if (route === "/api/evaluation/reports/latest") return new Response(JSON.stringify({ error: "unavailable" }), { status: 503 });
      const payload = basePayloads[route];
      if (!payload) return new Response(JSON.stringify({ error: "not_found" }), { status: 404 });
      if (route !== "/health") expect((init?.headers as Record<string, string>)?.Authorization).toBe("Bearer demo-token");
      return new Response(JSON.stringify(payload), { status: 200 });
    }));
    render(<LocalDashboard />);
    await connect();
    fireEvent.click(screen.getByRole("button", { name: "Detection Lab" }));
    expect(screen.getByText("The local API returned status 503.")).toBeTruthy();
  });

  it("explains unavailable metrics when their denominators are zero", async () => {
    const payload = structuredClone(evaluationPayload);
    const undefinedMetric = { value: null, denominator: 0, status: "undefined_zero_denominator" };
    Object.assign(payload.report.metrics, { precision: undefinedMetric, specificity: undefinedMetric });
    Object.assign(payload.report.per_rule[0].metrics, { precision: undefinedMetric, specificity: undefinedMetric });
    basePayloads["/api/evaluation/reports/latest"] = payload;
    render(<LocalDashboard />);
    await connect();
    fireEvent.click(screen.getByRole("button", { name: "Detection Lab" }));
    expect(await screen.findByText("Precision: Unavailable (0 denominator)")).toBeTruthy();
    expect(screen.getAllByText("N/A (denom 0)")).toHaveLength(2);
  });

  it("renders stored evaluation history and scenario-level comparison identifiers", async () => {
    const payload = structuredClone(evaluationPayload) as any;
    payload.report.history = [{
      run_id: "00000000-0000-0000-0000-000000000002", generated_at_utc: "2026-10-24T00:01:00Z",
      report_sha256: "d".repeat(64), dataset_sha256: "b".repeat(64), detector_config_sha256: "c".repeat(64),
      counts: payload.report.counts, metrics: payload.report.metrics, total_evaluated_pairs: 4,
      comparison: { previous_run_id: "00000000-0000-0000-0000-000000000001", newly_failing_scenario_ids: ["p6a-auth-edge"], resolved_scenario_ids: ["p6a-benign-control"] },
    }];
    basePayloads["/api/evaluation/reports/latest"] = payload;
    render(<LocalDashboard />);
    await connect();
    fireEvent.click(screen.getByRole("button", { name: "Detection Lab" }));
    const runRow = await screen.findByText("00000000-0000-0000-0000-000000000002");
    expect(runRow.closest("tr")?.textContent).toContain("p6a-auth-edge");
    expect(runRow.closest("tr")?.textContent).toContain("p6a-benign-control");
    expect(screen.getByText("d".repeat(64))).toBeTruthy();
  });

  it("shows the authenticated scenario history view and its empty state", async () => {
    render(<LocalDashboard />);
    await connect();
    fireEvent.click(screen.getByRole("button", { name: "Scenario Validation" }));
    expect(await screen.findByText("No scenario runs recorded")).toBeTruthy();
    const call = (fetch as unknown as ReturnType<typeof vi.fn>).mock.calls.find(([url]) => String(url).endsWith("/api/purple-team/scenarios/runs"));
    expect(call).toBeTruthy();
    expect((call?.[1] as RequestInit).headers).toEqual({ Authorization: "Bearer demo-token" });
    expect(screen.getByText(/not establish real-world control effectiveness/i)).toBeTruthy();
  });

  it("renders scenario outcomes and evidence references as safe text", async () => {
    basePayloads["/api/purple-team/scenarios/runs"] = {
      data_classification: "synthetic", label: "SYNTHETIC LOCAL SCENARIO HISTORY - NOT A REAL-WORLD CONTROL TEST", tenant_id: "synthetic-org-demo",
      runs: [{ schema_version: "1.0", catalog_version: "aegisai-purple-scenarios-v1", run_id: "a".repeat(32), scenario_id: "local-health-baseline", scenario_version: "1.0", status: "PASSED",
        data_classification: "synthetic", label: "SYNTHETIC LOCAL SCENARIO - NOT A REAL-WORLD CONTROL TEST",
        target_origin: "http://127.0.0.1:8767", execution_scope: "fixed_loopback_synthetic_website",
        started_at_utc: "2026-10-22T08:00:00Z", completed_at_utc: "2026-10-22T08:00:01Z",
        policy_decision: { scenario_id: "local-health-baseline", target_origin: "http://127.0.0.1:8767", allowed: true, reason_code: "approved", maximum_requests: 1 },
        expected_telemetry_type: "synthetic_http_access", expected_route_code: "health", expected_status: 200, expected_count: 1,
        observed_http_statuses: [200], observed_telemetry: [{ event_id: "event-1", evidence_ref: "<img src=x>", event_type: "synthetic_http_access", route_code: "health", status_code: 200, occurred_at_utc: "2026-10-22T08:00:00Z" }],
        expected_detection_rule_ids: [], observed_findings: [], assessment_check_ids: ["health_status_v1"], error_category: null, telemetry_report_id: null, telemetry_run_id: null,
        comparison: { previous_run_id: null, previous_status: null, outcome_changed: null }, limitations: ["Synthetic only."] }],
    };
    render(<LocalDashboard />);
    await connect();
    fireEvent.click(screen.getByRole("button", { name: "Scenario Validation" }));
    expect(await screen.findByText("local-health-baseline v1.0")).toBeTruthy();
    expect(document.querySelector(".ops-scenario-card li")?.textContent).toContain("<img src=x>");
    expect(document.querySelector(".ops-scenario-card img")).toBeNull();
  });

  it("distinguishes an unrecorded source from healthy, and displays API errors safely", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({}), { status: 404 })));
    render(<LocalDashboard />);
    fireEvent.change(screen.getByLabelText("Startup bearer token"), { target: { value: "demo-token" } });
    fireEvent.click(screen.getByRole("button", { name: "Connect" }));
    fireEvent.click(screen.getByRole("button", { name: "System Health" }));
    await waitFor(() => expect(screen.getAllByText("No data is available for this view yet.").length).toBeGreaterThan(0));
    expect(screen.getByText("No status recorded")).toBeTruthy();
  });

  it("clears the in-memory connection when disconnected", async () => {
    render(<LocalDashboard />);
    await connect();
    fireEvent.click(screen.getByRole("button", { name: "Disconnect" }));
    expect(screen.getByText("Connect to view local data")).toBeTruthy();
    expect(screen.getByLabelText("Startup bearer token")).toBeTruthy();
  });

  it("shows empty data and keeps source absence distinct from healthy", async () => {
    basePayloads["/api/telemetry/findings"] = { data_classification: "synthetic", label: "SYNTHETIC - NOT REAL CLIENT DATA", tenant_id: "synthetic-org-demo", findings: [] };
    render(<LocalDashboard />);
    fireEvent.change(screen.getByLabelText("Startup bearer token"), { target: { value: "demo-token" } });
    fireEvent.click(screen.getByRole("button", { name: "Connect" }));
    expect(await screen.findByText("No synthetic findings are currently returned for this tenant.")).toBeTruthy();
  });

  it("renders API strings as text rather than interpreting markup", async () => {
    const injected = finding({ explanation: '<img src=x onerror="alert(1)">' });
    basePayloads["/api/telemetry/findings"] = { data_classification: "synthetic", label: "SYNTHETIC - NOT REAL CLIENT DATA", tenant_id: "synthetic-org-demo", findings: [injected] };
    render(<LocalDashboard />);
    await connect();
    fireEvent.click(screen.getByRole("button", { name: /Findings/ }));
    fireEvent.click(screen.getByRole("button", { name: /AUTH-001/ }));
    expect(await screen.findByText('<img src=x onerror="alert(1)">')).toBeTruthy();
    expect(document.querySelector(".ops-explanation img")).toBeNull();
  });

  it("does not persist a token and shows a generic authentication error", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ error: "unauthorized" }), { status: 401 })));
    render(<LocalDashboard />);
    fireEvent.change(screen.getByLabelText("Startup bearer token"), { target: { value: "secret-test-token" } });
    fireEvent.click(screen.getByRole("button", { name: "Connect" }));
    expect((await screen.findAllByText(/Authentication failed/)).length).toBeGreaterThan(0);
    expect(screen.queryByText("No recent findings")).toBeNull();
    expect(window.localStorage.length).toBe(0);
    expect(document.body.textContent).not.toContain("secret-test-token");
  });

  it("announces the loading state while API requests are pending", async () => {
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      await new Promise((resolve) => window.setTimeout(resolve, 50));
      const route = new URL(String(input)).pathname;
      return new Response(JSON.stringify(basePayloads[route] ?? {}), { status: 200 });
    }));
    render(<LocalDashboard />);
    fireEvent.change(screen.getByLabelText("Startup bearer token"), { target: { value: "demo-token" } });
    fireEvent.click(screen.getByRole("button", { name: "Connect" }));
    expect(screen.getByRole("button", { name: /Refreshing/ })).toBeTruthy();
    await screen.findByText("AUTH-001", { selector: ".recent-main b" });
  });

  it("retains prior values with a stale-data message when refresh fails", async () => {
    render(<LocalDashboard />);
    await connect();
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ error: "unavailable" }), { status: 503 })));
    fireEvent.click(screen.getByRole("button", { name: /Refresh/ }));
    expect((await screen.findByRole("alert")).textContent).toContain("Previously loaded values");
    expect(screen.getByText("AUTH-001", { selector: ".recent-main b" })).toBeTruthy();
  });
});
