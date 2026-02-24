import { describe, it, expect, beforeEach, vi } from "vitest";
import { screen } from "@testing-library/react";
import { Workflows } from "../src/pages/Workflows";
import { renderWithProviders, mockFetch } from "./helpers";

const mockWorkflows = [
  {
    id: "research_pipeline",
    name: "Research Pipeline",
    description: "Full research workflow",
    asset_class: "crypto",
    is_template: true,
    is_active: true,
    schedule_interval_seconds: 86400,
    schedule_enabled: true,
    last_run_at: "2026-02-24T10:00:00Z",
    run_count: 5,
    step_count: 4,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-02-24T10:00:00Z",
  },
  {
    id: "signal_pipeline",
    name: "Signal Pipeline",
    description: "News + sentiment signal",
    asset_class: "crypto",
    is_template: true,
    is_active: true,
    schedule_interval_seconds: 3600,
    schedule_enabled: false,
    last_run_at: null,
    run_count: 0,
    step_count: 3,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  },
];

const mockStepTypes = [
  { step_type: "data_refresh", description: "Refresh OHLCV data" },
  { step_type: "vbt_screen", description: "Run VectorBT screening" },
  { step_type: "sentiment_aggregate", description: "Aggregate sentiment" },
];

describe("Workflows Page", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/workflows/": mockWorkflows,
        "/api/workflow-steps": mockStepTypes,
      }),
    );
  });

  it("renders the page heading", () => {
    renderWithProviders(<Workflows />);
    expect(screen.getByText("Workflows")).toBeInTheDocument();
  });

  it("renders workflow list", async () => {
    renderWithProviders(<Workflows />);
    expect(await screen.findByText("Research Pipeline")).toBeInTheDocument();
    expect(screen.getByText("Signal Pipeline")).toBeInTheDocument();
  });

  it("shows template badge", async () => {
    renderWithProviders(<Workflows />);
    await screen.findByText("Research Pipeline");
    const templateBadges = screen.getAllByText("template");
    expect(templateBadges.length).toBe(2);
  });

  it("shows trigger buttons", async () => {
    renderWithProviders(<Workflows />);
    await screen.findByText("Research Pipeline");
    const triggerButtons = screen.getAllByText("Trigger");
    expect(triggerButtons.length).toBe(2);
  });

  it("shows step types toggle", () => {
    renderWithProviders(<Workflows />);
    expect(screen.getByText("Show Available Step Types")).toBeInTheDocument();
  });
});
