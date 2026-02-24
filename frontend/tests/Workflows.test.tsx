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

describe("Workflows - Interaction", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/workflows/": mockWorkflows,
        "/api/workflow-steps": mockStepTypes,
      }),
    );
  });

  it("shows Details button for each workflow", async () => {
    renderWithProviders(<Workflows />);
    await screen.findByText("Research Pipeline");
    const detailButtons = screen.getAllByText("Details");
    expect(detailButtons.length).toBe(2);
  });

  it("shows scheduled badge for scheduled workflows", async () => {
    renderWithProviders(<Workflows />);
    await screen.findByText("Research Pipeline");
    const scheduledBadges = screen.getAllByText("scheduled");
    expect(scheduledBadges.length).toBeGreaterThanOrEqual(1);
  });

  it("shows Disable button for scheduled workflows", async () => {
    renderWithProviders(<Workflows />);
    await screen.findByText("Research Pipeline");
    // Research Pipeline has schedule_enabled=true → "Disable"
    expect(screen.getByText("Disable")).toBeInTheDocument();
  });

  it("shows Enable button for unscheduled workflows", async () => {
    renderWithProviders(<Workflows />);
    await screen.findByText("Signal Pipeline");
    // Signal Pipeline has schedule_enabled=false → "Enable"
    expect(screen.getByText("Enable")).toBeInTheDocument();
  });

  it("shows step count and run count", async () => {
    renderWithProviders(<Workflows />);
    await screen.findByText("Research Pipeline");
    expect(screen.getByText(/4 steps/)).toBeInTheDocument();
    expect(screen.getByText(/5 runs/)).toBeInTheDocument();
  });

  it("shows empty state when no workflows", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/workflows/": [],
        "/api/workflow-steps": mockStepTypes,
      }),
    );
    renderWithProviders(<Workflows />);
    // Should render page heading even with no workflows
    expect(screen.getByText("Workflows")).toBeInTheDocument();
  });

  it("shows error state when API fails", async () => {
    const failingFetch = (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input.toString();
      if (url.includes("workflows")) {
        return Promise.resolve(new Response(JSON.stringify({ error: "fail" }), { status: 500 }));
      }
      return mockFetch({ "/api/workflow-steps": mockStepTypes })(input, init);
    };
    vi.stubGlobal("fetch", failingFetch);
    renderWithProviders(<Workflows />);
    expect(await screen.findByText("Failed to load workflows")).toBeInTheDocument();
  });
});
