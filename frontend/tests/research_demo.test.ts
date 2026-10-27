import React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { App } from "../src/App";
import { MAX_ARTIFACT_BYTES, parseEpisodeArtifact, readBoundedResponseText, validateEpisodeArtifact } from "../src/researchArtifact";
import { parseAssessmentReport, validateAssessmentReport } from "../src/assessment";
import type { PublicEpisode } from "../src/types";
import episode from "../data/public_demo_episode.json";
import baseline from "../data/public_demo_assessment_baseline.json";
import hardened from "../data/public_demo_assessment_hardened.json";

const validEpisode = episode as PublicEpisode;
const assessmentFixture = (profile: "baseline" | "hardened", findings: Array<Record<string, string>> = []) => ({
  schema_version: "1.0", assessment_type: "http_security_header_check", checked_at_utc: "2026-01-01T00:00:00Z",
  status: findings.length ? "findings" : "passed", ok: findings.length === 0, url: "http://127.0.0.1:8765/",
  http_status: 200, profile,
  checked_headers: ["Content-Security-Policy", "X-Content-Type-Options", "Referrer-Policy", "Permissions-Policy"],
  header_results: ["Content-Security-Policy", "X-Content-Type-Options", "Referrer-Policy", "Permissions-Policy"].map((header) => ({
    header, expected_value: "expected", observed_value: null, present: profile === "hardened",
  })),
  missing_or_incorrect_headers: findings.map((finding) => finding.id), finding_count: findings.length, findings,
  limitations: ["Checks configured response headers only."],
});
const finding = (overrides: Record<string, string> = {}) => ({
  id: "missing_content_security_policy", severity: "medium", title: "Missing CSP", description: "Policy missing.",
  evidence: "Not returned.", remediation: "Set a policy.", ...overrides,
});
const response = (text: string, headers: Record<string, string> = {}) => new Response(text, { headers });
const streamedResponse = (chunks: Uint8Array[], declaredSize: string | null = null) => {
  let index = 0;
  return {
    headers: { get: (name: string) => name.toLowerCase() === "content-length" ? declaredSize : null },
    body: {
      getReader: () => ({
        read: async () => index < chunks.length ? { done: false, value: chunks[index++] } : { done: true, value: undefined },
        cancel: async () => undefined,
        releaseLock: () => undefined,
      }),
    },
  } as unknown as Response;
};

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn(async (url: string | URL) => {
    const value = String(url).includes("episode") ? validEpisode : {};
    return response(JSON.stringify(value));
  }));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe("research artifact validation and timeline", () => {
  it("filters the evidence timeline while preserving the selected action", async () => {
    render(React.createElement(App, { page: "dashboard" }));
    await screen.findByText(/Loaded \d+ precomputed action records/);
    fireEvent.click(screen.getByRole("button", { name: "Defender only" }));
    const timeline = screen.getByRole("list", { name: "Precomputed Red and Blue actions" });
    const blueActions = within(timeline).getAllByRole("button");
    expect(blueActions).toHaveLength(validEpisode.records.filter((record) => record.role === "blue").length);
    expect(blueActions.every((button) => button.textContent?.startsWith("BLUE"))).toBe(true);
    expect(screen.getByRole("region", { name: "Current moment explained" }).textContent).toContain("Record 1 / 39");
    expect(screen.getByRole("button", { name: "Show selected action" })).toBeTruthy();
    fireEvent.click(blueActions[0]);
    expect(screen.getByText(/BLUE OBSERVATION/)).toBeTruthy();
    const search = screen.getByRole("searchbox", { name: "Search recorded actions" });
    fireEvent.change(search, { target: { value: "nothing-matches-this-search" } });
    expect(screen.getByText("No actions match these filters.")).toBeTruthy();
    expect(screen.getByText(/BLUE OBSERVATION/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Show all actions" }));
    expect(within(screen.getByRole("list", { name: "Precomputed Red and Blue actions" })).getAllByRole("button")).toHaveLength(39);
    expect((search as HTMLInputElement).value).toBe("");
  });

  it("navigates the focused player by keyboard without changing text-field behavior", async () => {
    render(React.createElement(App, { page: "dashboard" }));
    await screen.findByText(/Loaded \d+ precomputed action records/);
    const player = screen.getByRole("region", { name: "Recorded exercise player" });
    fireEvent.keyDown(player, { key: "ArrowRight" });
    expect(screen.getByRole("region", { name: "Current moment explained" }).textContent).toContain("Foothold established.");
    fireEvent.keyDown(player, { key: "ArrowRight", ctrlKey: true });
    expect(screen.getByRole("region", { name: "Current moment explained" }).textContent).toContain("Foothold established.");
    fireEvent.keyDown(player, { key: "End" });
    expect(screen.getByRole("region", { name: "Current moment explained" }).textContent).toContain("Data exfiltrated.");
    fireEvent.click(screen.getByRole("button", { name: /Restart walkthrough/ }));
    expect(document.activeElement).toBe(within(screen.getByRole("group", { name: "Key moments in the exercise" })).getAllByRole("button")[0]);
    fireEvent.keyDown(screen.getByRole("searchbox", { name: "Search recorded actions" }), { key: "ArrowRight" });
    expect(screen.getByRole("region", { name: "Current moment explained" }).textContent).toContain("Record 1 / 39");
  });

  it("follows same-page section links and reopens the evidence disclosure", async () => {
    const previousUrl = window.location.href;
    try {
      render(React.createElement(App, { page: "dashboard" }));
      await screen.findByText(/Loaded \d+ precomputed action records/);
      window.history.replaceState({}, "", "#assessment");
      fireEvent(window, new HashChangeEvent("hashchange"));
      await waitFor(() => expect(screen.getByRole("link", { name: "Before & after" }).getAttribute("aria-current")).toBe("location"));
      const evidence = document.getElementById("episode-evidence");
      evidence?.removeAttribute("open");
      window.history.replaceState({}, "", "#episode-evidence");
      fireEvent(window, new HashChangeEvent("hashchange"));
      await waitFor(() => expect(evidence?.hasAttribute("open")).toBe(true));
    } finally {
      window.history.replaceState({}, "", previousUrl);
    }
  });

  it("opens the evidence section after loading a direct evidence link", async () => {
    const previousUrl = window.location.href;
    window.history.replaceState({}, "", "#episode-evidence");
    try {
      render(React.createElement(App, { page: "dashboard" }));
      await screen.findByText(/Loaded \d+ precomputed action records/);
      await waitFor(() => expect(document.getElementById("episode-evidence")?.hasAttribute("open")).toBe(true));
    } finally {
      window.history.replaceState({}, "", previousUrl);
    }
  });

  it("recovers from a temporary sample load failure when retried", async () => {
    vi.mocked(fetch).mockRejectedValueOnce(new Error("Connection interrupted"));
    render(React.createElement(App, { page: "dashboard" }));
    await screen.findByText(/Could not load the sample: Connection interrupted/);
    fireEvent.click(screen.getByRole("button", { name: "Retry sample" }));
    await screen.findByText(/Loaded \d+ precomputed action records/);
    expect(screen.queryByRole("button", { name: "Retry sample" })).toBeNull();
    expect(screen.getByRole("button", { name: "Next key moment" })).toBeTruthy();
  });

  it("restarts the completed walkthrough and exits presentation with Escape", async () => {
    vi.spyOn(window, "scrollTo").mockImplementation(() => {});
    render(React.createElement(App, { page: "dashboard" }));
    await screen.findByText(/Loaded \d+ precomputed action records/);
    const moments = within(screen.getByRole("group", { name: "Key moments in the exercise" })).getAllByRole("button");
    fireEvent.click(moments[5]);
    fireEvent.click(screen.getByRole("button", { name: /Restart walkthrough/ }));
    expect(screen.getByRole("region", { name: "Current moment explained" }).textContent).toContain("Record 1 / 39");
    expect((screen.getByRole("button", { name: "Previous key moment" }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "Present demo" }));
    fireEvent.keyDown(window, { key: "Escape" });
    expect(document.querySelector(".presentation-view")).toBeNull();
    expect(screen.getByRole("region", { name: "Current moment explained" }).textContent).toContain("Record 1 / 39");
  });

  it("keeps the selected record when entering and leaving presentation view", async () => {
    vi.spyOn(window, "scrollTo").mockImplementation(() => {});
    render(React.createElement(App, { page: "dashboard" }));
    await screen.findByText(/Loaded \d+ precomputed action records/);
    fireEvent.click(screen.getByRole("button", { name: "Next key moment" }));
    fireEvent.click(screen.getByRole("button", { name: "Present demo" }));
    expect(document.querySelector(".presentation-view")).toBeTruthy();
    expect(screen.getByRole("region", { name: "Current moment explained" }).textContent).toContain("Foothold established.");
    expect(screen.getByRole("button", { name: "Exit presentation" }).getAttribute("aria-pressed")).toBe("true");
    fireEvent.click(screen.getByRole("button", { name: "Exit presentation" }));
    expect(document.querySelector(".presentation-view")).toBeNull();
    expect(screen.getByRole("region", { name: "Current moment explained" }).textContent).toContain("Foothold established.");
  });

  it("walks through actual records with plain-language explanations and bounded controls", async () => {
    render(React.createElement(App, { page: "dashboard" }));
    await screen.findByText(/Loaded \d+ precomputed action records/);
    const moments = within(screen.getByRole("group", { name: "Key moments in the exercise" })).getAllByRole("button");
    expect(moments).toHaveLength(6);
    const previous = screen.getByRole("button", { name: "Previous key moment" }) as HTMLButtonElement;
    const next = screen.getByRole("button", { name: "Next key moment" }) as HTMLButtonElement;
    expect(previous.disabled).toBe(true);
    expect(screen.getByRole("region", { name: "Current moment explained" }).textContent).toContain("Record 1 / 39");
    fireEvent.click(next);
    expect(screen.getByRole("region", { name: "Current moment explained" }).textContent).toContain("Foothold established.");
    expect(previous.disabled).toBe(false);
    fireEvent.click(next);
    expect(screen.getByRole("region", { name: "Current moment explained" }).textContent).toContain("Defender's move");
    fireEvent.click(next);
    expect(screen.getByRole("region", { name: "Current moment explained" }).textContent).toContain("Credential rejected.");
    // A failed credential attempt was still authorized by the Controller.
    expect(screen.getByRole("region", { name: "Simplified exercise map" }).textContent).toContain("Allowed");
    expect(document.querySelector(".node-active")?.textContent).toContain("Workstation");
    fireEvent.click(moments[5]);
    expect(screen.getByRole("region", { name: "Current moment explained" }).textContent).toContain("Data exfiltrated.");
    expect(next.disabled).toBe(true);
    expect(document.querySelector(".node-active")?.textContent).toContain("Sample database");
    fireEvent.click(previous);
    expect(screen.getByRole("region", { name: "Current moment explained" }).textContent).toContain("Asset accessed.");
    const results = screen.getByRole("region", { name: "Full episode results" });
    expect(results.textContent).toContain("8 of 9");
    expect(results.textContent).toContain("0 of 6");
    expect(results.textContent).toContain("Reached");
  });

  it("accepts the published artifact with provenance and role-scoped evidence", () => {
    const parsed = parseEpisodeArtifact(JSON.stringify(validEpisode));
    expect(parsed.labels.synthetic).toBe(true);
    expect(parsed.labels.precomputed).toBe(true);
    expect(parsed.provenance.seed).toBe(1);
    expect(parsed.records.some((record) => record.role === "red")).toBe(true);
    expect(parsed.records.some((record) => record.role === "blue")).toBe(true);
    expect(parsed.metrics.every((metric) => metric.denominator > 0)).toBe(true);
    expect(parsed.records.every((record) => record.evidence.every((item) => item.source === `${record.role}_observation`))).toBe(true);
    expect(parsed.records.every((record) => !("state_changes" in record) && !("event_ids" in record))).toBe(true);
  });

  it("rejects malformed JSON, missing fields, and unsupported schema versions", () => {
    expect(() => parseEpisodeArtifact("{broken")).toThrow(/not valid JSON/);
    const missing = structuredClone(validEpisode) as unknown as Record<string, any>;
    delete missing.provenance.seed;
    expect(() => validateEpisodeArtifact(missing)).toThrow(/missing required provenance/);
    const unsupported = structuredClone(validEpisode) as unknown as Record<string, any>;
    unsupported.schema_version = "9.9";
    expect(() => validateEpisodeArtifact(unsupported)).toThrow(/unsupported type or schema version/);
  });

  it("rejects oversized JSON, duplicate metrics, invalid role scope, and out-of-range steps", () => {
    expect(() => parseEpisodeArtifact(" ".repeat(MAX_ARTIFACT_BYTES + 1))).toThrow(/1 MB size limit/);
    const duplicate = structuredClone(validEpisode) as unknown as Record<string, any>;
    duplicate.metrics[1].id = duplicate.metrics[0].id;
    expect(() => validateEpisodeArtifact(duplicate)).toThrow(/invalid metric or denominator/);
    const wrongRole = structuredClone(validEpisode) as unknown as Record<string, any>;
    wrongRole.records[0].evidence[0].source = "blue_observation";
    expect(() => validateEpisodeArtifact(wrongRole)).toThrow(/outside its role-specific observation/);
    const outOfRange = structuredClone(validEpisode) as unknown as Record<string, any>;
    outOfRange.records[0].step = outOfRange.provenance.recorded_steps;
    expect(() => validateEpisodeArtifact(outOfRange)).toThrow(/invalid action timeline entry/);
  });

  it("bounds streamed responses even when Content-Length is missing or false", async () => {
    await expect(readBoundedResponseText(streamedResponse([new Uint8Array(MAX_ARTIFACT_BYTES + 1)], "1"))).rejects.toThrow(/1 MB size limit/);
    const valid = new TextEncoder().encode("{\"ok\":true}");
    await expect(readBoundedResponseText(streamedResponse([valid]))).resolves.toBe("{\"ok\":true}");
    await expect(readBoundedResponseText({ headers: { get: () => null }, body: null } as unknown as Response)).rejects.toThrow(/bounded streaming/);
  });

  it("renders a selectable timeline and details only from the selected role observation", async () => {
    render(React.createElement(App, { page: "dashboard" }));
    await screen.findByText(/Loaded \d+ precomputed action records/);
    const blueButton = screen.getAllByRole("button", { name: /BLUE/ })[0];
    fireEvent.click(blueButton);
    expect(blueButton.getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByText(/BLUE OBSERVATION/)).toBeTruthy();
    expect(screen.getByText(/Controller authorization/)).toBeTruthy();
    expect(screen.getByText(/Role-visible evidence/)).toBeTruthy();
    expect(screen.getAllByText(/blue_observation/).length).toBeGreaterThan(0);
  });

  it("keeps the selected Red record scoped to Red observation evidence", async () => {
    render(React.createElement(App, { page: "dashboard" }));
    await screen.findByText(/Loaded \d+ precomputed action records/);
    const redButton = screen.getAllByRole("button", { name: /RED/ })[0];
    fireEvent.click(redButton);
    expect(screen.getByText(/RED OBSERVATION/)).toBeTruthy();
    expect(screen.getAllByText(/red_observation/).length).toBeGreaterThan(0);
    expect(screen.queryByText(/blue_observation/)).toBeNull();
  });

  it("shows metric denominators, provenance, and fixed sample download links", async () => {
    render(React.createElement(App, { page: "dashboard" }));
    await screen.findByText(/Loaded \d+ precomputed action records/);
    expect(screen.getByText(/credential_reuse_known_vuln:1 · seed 1/)).toBeTruthy();
    expect(screen.getByText(/Episode metrics/)).toBeTruthy();
    expect(screen.getByText(/8 \/ 9 alerts/)).toBeTruthy();
    const episodeDownload = screen.getByRole("link", { name: /Download sample report/ });
    expect(episodeDownload.getAttribute("download")).toBe("aegisai-synthetic-episode-v1.json");
    expect(episodeDownload.getAttribute("href")).toContain("public_demo_episode");
    expect(screen.getByRole("link", { name: "baseline JSON" }).getAttribute("download")).toBe("aegisai-assessment-baseline-sample.json");
    expect(screen.getByRole("link", { name: "hardened JSON" }).getAttribute("download")).toBe("aegisai-assessment-hardened-sample.json");
  });

  it("renders injected artifact strings as inert React text", async () => {
    const hostile = "<img src=x onerror=alert(1)><script>alert(2)</script>";
    const poisoned = structuredClone(validEpisode) as PublicEpisode;
    poisoned.records[0].action.type = hostile;
    vi.stubGlobal("fetch", vi.fn(async () => response(JSON.stringify(poisoned))));
    render(React.createElement(App, { page: "dashboard" }));
    expect(await screen.findByText(/Loaded \d+ precomputed action records/)).toBeTruthy();
    expect(document.querySelector("img, script")).toBeNull();
    expect(screen.getAllByRole("button").some((button) => button.textContent?.includes(hostile))).toBe(true);
  });

  it("shows an accessible bounded error for malformed episode data", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => response("{bad")));
    render(React.createElement(App, { page: "dashboard" }));
    expect((await screen.findByText(/Could not load the sample/)).textContent).toMatch(/not valid JSON/);
  });
});

describe("assessment comparison and imports", () => {
  it("validates the sanitized baseline and hardened samples", () => {
    expect(validateAssessmentReport(baseline).profile).toBe("baseline");
    expect(validateAssessmentReport(hardened).profile).toBe("hardened");
    expect(() => parseAssessmentReport("{oops")).toThrow(/not valid JSON/);
  });

  it("imports baseline and hardened files and calculates the comparison", async () => {
    render(React.createElement(App, { page: "dashboard" }));
    const input = screen.getByLabelText("Assessment JSON files");
    const base = new File([JSON.stringify(assessmentFixture("baseline", [finding()]))], "baseline.json", { type: "application/json" });
    const hard = new File([JSON.stringify(assessmentFixture("hardened"))], "hardened.json", { type: "application/json" });
    Object.defineProperty(base, "text", { value: async () => JSON.stringify(assessmentFixture("baseline", [finding()])) });
    Object.defineProperty(hard, "text", { value: async () => JSON.stringify(assessmentFixture("hardened")) });
    fireEvent.change(input, { target: { files: [base, hard] } });
    await screen.findByText(/2 report\(s\) loaded/);
    expect(screen.getByText(/1 finding\(s\) resolved/)).toBeTruthy();
    expect(screen.getByText("Missing CSP")).toBeTruthy();
  });

  it("rejects duplicate local profiles and clears the previous result", async () => {
    render(React.createElement(App, { page: "dashboard" }));
    const input = screen.getByLabelText("Assessment JSON files");
    const data = JSON.stringify(assessmentFixture("baseline", [finding()]));
    const files = ["one.json", "two.json"].map((name) => {
      const file = new File([data], name, { type: "application/json" });
      Object.defineProperty(file, "text", { value: async () => data });
      return file;
    });
    fireEvent.change(input, { target: { files } });
    await waitFor(() => expect(document.getElementById("assessment-status")?.textContent).toMatch(/one report per profile/));
    expect(document.getElementById("assessment-results")?.textContent).toBe("");
  });

  it("rejects oversized local files before reading their contents", async () => {
    render(React.createElement(App, { page: "dashboard" }));
    const input = screen.getByLabelText("Assessment JSON files");
    const large = new File([new Uint8Array(MAX_ARTIFACT_BYTES + 1)], "large.json", { type: "application/json" });
    const readText = vi.fn(async () => "{}");
    Object.defineProperty(large, "text", { value: readText });
    fireEvent.change(input, { target: { files: [large] } });
    await waitFor(() => expect(document.getElementById("assessment-status")?.textContent).toMatch(/maximum 1 MB/));
    expect(readText).not.toHaveBeenCalled();
  });

  it("renders hostile assessment strings as text and clears results after malformed input", async () => {
    render(React.createElement(App, { page: "dashboard" }));
    const input = screen.getByLabelText("Assessment JSON files");
    const hostile = "<img src=x onerror=alert(1)>";
    const good = assessmentFixture("baseline", [finding({ title: hostile })]);
    const file = new File([JSON.stringify(good)], "baseline.json", { type: "application/json" });
    Object.defineProperty(file, "text", { value: async () => JSON.stringify(good) });
    fireEvent.change(input, { target: { files: [file] } });
    await screen.findByText(/1 report\(s\) loaded/);
    expect(document.querySelector("img")).toBeNull();
    expect(screen.getByText(hostile)).toBeTruthy();
    const malformed = new File(["{oops"], "bad.json", { type: "application/json" });
    Object.defineProperty(malformed, "text", { value: async () => "{oops" });
    fireEvent.change(input, { target: { files: [malformed] } });
    await waitFor(() => expect(document.getElementById("assessment-status")?.textContent).toMatch(/not valid JSON/));
    expect(screen.queryByText(hostile)).toBeNull();
  });

  it("rejects unsupported profile, oversized reports, and duplicate findings", () => {
    expect(() => validateAssessmentReport({ ...assessmentFixture("baseline"), profile: "external" })).toThrow(/not a supported local header assessment/);
    expect(() => parseAssessmentReport(" ".repeat(MAX_ARTIFACT_BYTES + 1))).toThrow(/1 MB size limit/);
    const duplicate = assessmentFixture("baseline", [finding(), finding()]);
    expect(() => validateAssessmentReport(duplicate)).toThrow(/not a supported local header assessment/);
  });

  it("loads published samples only from fixed same-origin URLs and compares them", async () => {
    const requested: string[] = [];
    vi.stubGlobal("fetch", vi.fn(async (url: string | URL) => {
      const value = String(url).includes("baseline") ? baseline : hardened;
      requested.push(String(url));
      return response(JSON.stringify(value));
    }));
    render(React.createElement(App, { page: "dashboard" }));
    fireEvent.click(screen.getByRole("button", { name: /Load published baseline and hardened samples/ }));
    await screen.findByText(/2 published sample reports loaded/);
    expect(requested).toHaveLength(3);
    expect(requested.every((url) => url.startsWith(".") || url.startsWith("/"))).toBe(true);
    expect(screen.getByText(/4 finding\(s\) resolved/)).toBeTruthy();
  });

  it("rejects published samples whose declared size exceeds the bounded limit", async () => {
    vi.stubGlobal("fetch", vi.fn(async (url: string | URL) => String(url).includes("episode")
      ? response(JSON.stringify(validEpisode))
      : response("{}", { "content-length": String(MAX_ARTIFACT_BYTES + 1) })));
    render(React.createElement(App, { page: "dashboard" }));
    fireEvent.click(screen.getByRole("button", { name: /Load published baseline and hardened samples/ }));
    await waitFor(() => expect(document.getElementById("assessment-status")?.textContent).toMatch(/1 MB size limit/));
    expect(document.getElementById("assessment-results")?.textContent).toBe("");
  });
});
