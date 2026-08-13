import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "../src/App";

const themes = { themes: [
  { theme_id: "semiconductors", display_name: "Semiconductors", tracker_etf: "SMH", benchmark: "SPY", constituents: ["NVDA"], status: "data_rehearsal" },
  { theme_id: "cloud_computing", display_name: "Cloud Computing", tracker_etf: "SKYY", benchmark: "SPY", constituents: ["MSFT"], status: "data_rehearsal" },
] };

const certificate = (theme_id: string) => ({
  certificate_id: `${theme_id}-cert`, theme_id, as_of_utc: "2026-08-10T19:45:00Z", evidence_grade: "synthetic_demo",
  facts: [{ kind: "boundary", text: "Data readiness is not signed Direction." }],
  direction: { state: "unresolved", eligible: false, data_ready: true, model_estimated: false, decision_eligible: false, uncertainty: null, evidence_refs: ["safe:source"], metrics: {}, invalidation: "Next legal observation." },
  transmission: { state: "not_estimable", eligible: false, data_ready: true, model_estimated: false, decision_eligible: false, uncertainty: null, evidence_refs: [], metrics: {}, invalidation: "Missing sequence." },
  episode: { state: "not_estimable", eligible: false, data_ready: false, model_estimated: false, decision_eligible: false, uncertainty: null, evidence_refs: [], metrics: {}, invalidation: "Missing sequence." },
  structural_attention: { state: "not_available", eligible: true, data_ready: true, model_estimated: true, decision_eligible: false, uncertainty: .2, evidence_refs: [], metrics: {}, invalidation: "Isolated." },
  fragility: { state: "unknown", eligible: false, data_ready: false, model_estimated: false, decision_eligible: false, uncertainty: null, evidence_refs: [], metrics: {}, invalidation: "Not estimated." },
  observer_agreement: { score: 1, estimated_observers: 1, conflict_count: 0, state: "no_conflict" }, observer_conflicts: [], uncertainty: .2,
  invalidation: ["Next legal observation."], next_probe: { acquire: "Capture next legal point.", reason: "Not decision sufficient.", deadline_utc: "2026-08-11T19:45:00Z", expected_information_value: "high" },
  eligible_playbooks: ["D_wait_unresolved"], vehicle_eligibility: { Theme_ETF: false }, decision_status: "DATA_BLOCKED_NO_DECISION",
});

const status = { updated_at: "2026-08-10T20:00:00Z", mode: "ALPACA_SIP_DATA_REHEARSAL_COMPLETE", data_ready: true, model_estimated: false, decision_eligible: false, formal_data_shadow_started: false, model_shadow_started: false, data_shadow_gate: { valid_days: 0, required_days: 20 }, paper_positions: 0, real_orders: 0, next_milestone: "Full-day rehearsal", day0b: {} };

beforeEach(() => {
  window.location.hash = "#/today";
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
    const path = String(input);
    const payload = path.endsWith("status.json") ? status : path.endsWith("themes.json") ? themes : path.endsWith("experiments.json") ? [] : certificate(path.includes("cloud_computing") ? "cloud_computing" : "semiconductors");
    return { ok: true, json: async () => payload } as Response;
  }));
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("Market State Observatory product boundary", () => {
  it("renders Today as the first operational view", async () => {
    render(<App />);
    expect(await screen.findByRole("heading", { name: "Today" })).toBeInTheDocument();
    expect(screen.getByText("DATA SHADOW 0 / 20")).toBeInTheDocument();
    expect(screen.getByText("NO BUY / SELL OUTPUT")).toBeInTheDocument();
  });

  it("does not confuse data readiness with positive Direction", async () => {
    render(<App />);
    await screen.findByRole("heading", { name: "Semiconductors", level: 3 });
    expect(screen.getAllByText("Not estimated").length).toBeGreaterThan(0);
    expect(screen.queryByText("Direction positive")).not.toBeInTheDocument();
    expect(screen.getAllByText(/Input readiness is not a positive Direction estimate/).length).toBeGreaterThan(0);
  });

  it("switches theme detail and opens evidence drawer", async () => {
    const user = userEvent.setup();
    render(<App />);
    await screen.findByRole("heading", { name: "Cloud Computing", level: 3 });
    const openButtons = screen.getAllByRole("button", { name: /Open theme/ });
    await user.click(openButtons[1]);
    await waitFor(() => expect(window.location.hash).toContain("cloud_computing"));
    expect(await screen.findByRole("heading", { name: "Cloud Computing" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Open evidence/ }));
    expect(screen.getByRole("dialog", { name: "cloud_computing" })).toBeInTheDocument();
  });
});
