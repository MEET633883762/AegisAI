import React from "react";
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { App } from "../src/App";

afterEach(cleanup);

describe("public page shell", () => {
  it("renders the research landing page with a clear demo path and safety boundaries", () => {
    render(React.createElement(App, { page: "landing" }));
    expect(screen.getByRole("link", { name: "Skip to content" }).getAttribute("href")).toBe("#main");
    expect(screen.getByRole("heading", { name: /Practice the attack/ })).toBeTruthy();
    expect(screen.getAllByRole("link", { name: /Explore the demo/ })[0].getAttribute("href")).toBe("dashboard.html");
    expect(screen.getByText(/No public simulation runs, uploads, or user-submitted targets/)).toBeTruthy();
    expect(screen.getByText(/does not execute simulations or contact websites/)).toBeTruthy();
    expect(screen.getByText(/Sample content is synthetic/)).toBeTruthy();
  });

  it("renders the dashboard with its sample labels and preserved features", () => {
    render(React.createElement(App, { page: "dashboard" }));
    expect(screen.getByRole("navigation", { name: "Main navigation" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "One attack. Every decision visible." })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Small changes. Visible protection." })).toBeTruthy();
    expect(screen.getByLabelText("Assessment JSON files")).toBeTruthy();
    expect(screen.getByText(/four response headers only/)).toBeTruthy();
    expect(screen.getByRole("region", { name: "Meet the three roles" })).toBeTruthy();
    expect(screen.getByRole("region", { name: "Published website protection comparison" }).textContent).toContain("4 missing settings corrected");
    expect(screen.queryByText(/Illustrative metrics/)).toBeNull();
    expect(screen.getByRole("link", { name: /Privacy & data handling/ }).getAttribute("href")).toBe("privacy.html");
  });

  it("keeps the privacy page honest about the missing contact channel", () => {
    render(React.createElement(App, { page: "privacy" }));
    expect(screen.getByRole("heading", { name: "Privacy and data handling" })).toBeTruthy();
    expect(screen.getByText(/project owner must designate a public contact channel before launch/)).toBeTruthy();
    expect(screen.getByText(/your browser reads it locally/)).toBeTruthy();
  });
});
