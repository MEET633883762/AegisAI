import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { LocalDashboard } from "../src/localDashboard/LocalDashboard";

const finding = (overrides: Record<string, unknown> = {}) => ({
  finding_id: "tfinding-aaaaaaaaaaaa", rule_id: "AUTH-001", rule_version: "1.0", severity: "high", confidence: 0.92,
  first_seen_utc: "2026-10-22T08:00:00Z", last_seen_utc: "2026-10-22T08:05:00Z", asset_ref: "synthetic-web-1",
  evidence_refs: ["synthetic-evidence-1"], event_ids: ["syn-auth-1"], explanation: "Synthetic repeated authentication failures.",
  confidence_factors: ["allowlisted synthetic authentication events"], status: "open", ...overrides,
});

const basePayloads: Record<string, unknown> = {
  "/health": { status: "ok", mode: "local_synthetic" },
  "/api/telemetry/findings": { data_classification: "synthetic", label: "SYNTHETIC - NOT REAL CLIENT DATA", tenant_id: "synthetic-org-demo", findings: [finding()] },
  "/api/processing": { data_classification: "synthetic", label: "SYNTHETIC - NOT REAL CLIENT DATA", tenant_id: "synthetic-org-demo", scheduler_state: "running", interval_seconds: 600, latest_run: {
    run_id: "trun-aaaaaaaaaaaaaaaa", source_id: "local_synthetic_fixture_v1", status: "completed", scheduled_at_utc: "2026-10-22T08:00:00Z", started_at_utc: "2026-10-22T08:00:00Z", completed_at_utc: "2026-10-22T08:00:01Z", attempt: 1, input_event_count: 5, accepted_event_count: 4, duplicate_event_count: 1, finding_count: 1, error_code: null,
  } },
  "/api/telemetry/sources/live-website/status": { data_classification: "synthetic", label: "SYNTHETIC - NOT REAL CLIENT DATA", tenant_id: "synthetic-org-demo", source_key: "synthetic_demo_site_live_logs_v1", last_attempt_at_utc: "2026-10-22T08:00:00Z", last_success_at_utc: "2026-10-22T08:00:00Z", status: "healthy", input_event_count: 5, accepted_event_count: 4, duplicate_event_count: 1, rejected_record_count: 0, position_sha256: "a".repeat(64), position_bytes: 100, error_code: null },
  "/api/telemetry/findings/tfinding-aaaaaaaaaaaa/evidence": { data_classification: "synthetic", label: "SYNTHETIC - NOT REAL CLIENT DATA", tenant_id: "synthetic-org-demo", finding_id: "tfinding-aaaaaaaaaaaa", evidence: [{ evidence_ref: "synthetic-evidence-1", event_id: "syn-auth-1", event_type: "auth_failure", occurred_at_utc: "2026-10-22T08:00:00Z", asset_ref: "synthetic-web-1", actor_ref: "synthetic-actor-1", source_ref: "synthetic-source-1" }] },
};

beforeEach(() => {
  basePayloads["/api/telemetry/findings"] = { data_classification: "synthetic", label: "SYNTHETIC - NOT REAL CLIENT DATA", tenant_id: "synthetic-org-demo", findings: [finding()] };
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
    expect(screen.getByText("Report not available through the local API")).toBeTruthy();
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
