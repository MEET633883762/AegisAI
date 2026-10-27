import { act } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { WebsiteAssessment } from "../src/WebsiteAssessment";
import baseline from "../data/public_demo_assessment_baseline.json";
import hardened from "../data/public_demo_assessment_hardened.json";

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((accept) => { resolve = accept; });
  return { promise, resolve };
}

function localFile(text: () => Promise<string>) {
  const file = new File(["local report"], "local-baseline.json", { type: "application/json" });
  Object.defineProperty(file, "text", { value: text });
  return file;
}

const localReport = () => JSON.stringify({
  ...baseline,
  findings: baseline.findings.map((finding, index) => index === 0
    ? { ...finding, title: "Local selection remains active" } : finding),
});

describe("assessment loading selection", () => {
  it("rejects more than two selected files before reading any contents", async () => {
    render(<WebsiteAssessment />);
    const readText = vi.fn(async () => localReport());
    fireEvent.change(screen.getByLabelText("Assessment JSON files"), {
      target: { files: [localFile(readText), localFile(readText), localFile(readText)] },
    });
    await screen.findByText(/at most two files/);
    expect(readText).not.toHaveBeenCalled();
    expect(document.getElementById("assessment-results")?.textContent).toBe("");
  });

  it("keeps a newer local selection when older published requests finish", async () => {
    const pending = [deferred<Response>(), deferred<Response>()];
    let index = 0;
    vi.stubGlobal("fetch", vi.fn(() => pending[index++].promise));
    render(<WebsiteAssessment />);
    fireEvent.click(screen.getByRole("button", { name: /Load published baseline and hardened samples/ }));
    fireEvent.change(screen.getByLabelText("Assessment JSON files"), {
      target: { files: [localFile(async () => localReport())] },
    });
    await screen.findByText(/1 report\(s\) loaded/);

    await act(async () => {
      pending[0].resolve(new Response(JSON.stringify(baseline)));
      pending[1].resolve(new Response(JSON.stringify(hardened)));
      await Promise.all(pending.map((item) => item.promise));
    });

    expect(screen.getByText("Local selection remains active")).toBeTruthy();
    expect(document.getElementById("assessment-status")?.textContent).toContain("1 report(s) loaded");
    expect((screen.getByRole("button", { name: /Load published baseline and hardened samples/ }) as HTMLButtonElement).disabled).toBe(false);
    expect(screen.queryByText(/2 published sample reports loaded/)).toBeNull();
  });

  it("keeps newer published results when an older local file finishes reading", async () => {
    const pending = deferred<string>();
    vi.stubGlobal("fetch", vi.fn(async (url: string | URL) => new Response(JSON.stringify(
      String(url).includes("baseline") ? baseline : hardened,
    ))));
    render(<WebsiteAssessment />);
    fireEvent.change(screen.getByLabelText("Assessment JSON files"), {
      target: { files: [localFile(() => pending.promise)] },
    });
    fireEvent.click(screen.getByRole("button", { name: /Load published baseline and hardened samples/ }));
    await screen.findByText(/2 published sample reports loaded/);

    await act(async () => { pending.resolve(localReport()); await pending.promise; });

    await waitFor(() => expect(document.getElementById("assessment-status")?.textContent).toContain("2 published sample reports loaded"));
    expect(screen.queryByText("Local selection remains active")).toBeNull();
    expect(screen.getByText(/4 finding\(s\) resolved/)).toBeTruthy();
  });

  it("associates comparison values with row and column headers", () => {
    render(<WebsiteAssessment />);
    const table = screen.getByRole("table", { name: "Browser protection settings before and after hardening" });
    expect(within(table).getAllByRole("columnheader")).toHaveLength(3);
    expect(within(table).getAllByRole("rowheader")).toHaveLength(4);
    expect(within(table).getAllByRole("cell")).toHaveLength(8);
    expect(within(table).getAllByRole("row")).toHaveLength(5);
  });
});
