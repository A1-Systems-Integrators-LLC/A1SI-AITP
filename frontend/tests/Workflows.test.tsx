import { describe, it, expect, beforeEach, vi } from "vitest";
import { screen, fireEvent } from "@testing-library/react";
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

describe("Workflows - Expanded Detail", () => {
  const mockDetail = {
    id: "research_pipeline",
    name: "Research Pipeline",
    description: "Full research workflow",
    asset_class: "crypto",
    is_template: true,
    is_active: true,
    schedule_interval_seconds: 86400,
    schedule_enabled: true,
    steps: [
      { id: "s1", name: "Refresh Data", step_type: "data_refresh", order: 1, condition: null, params: {} },
      { id: "s2", name: "Screen Strategies", step_type: "vbt_screen", order: 2, condition: "prev_success", params: {} },
    ],
  };

  const mockRuns = [
    {
      id: "run-1",
      workflow_id: "research_pipeline",
      status: "completed",
      trigger: "manual",
      current_step: 2,
      total_steps: 2,
      started_at: "2026-02-24T10:00:00Z",
      completed_at: "2026-02-24T10:05:00Z",
      error: null,
    },
    {
      id: "run-2",
      workflow_id: "research_pipeline",
      status: "failed",
      trigger: "scheduled",
      current_step: 1,
      total_steps: 2,
      started_at: "2026-02-23T10:00:00Z",
      completed_at: "2026-02-23T10:01:00Z",
      error: "Data fetch timeout",
    },
  ];

  const mockRunDetail = {
    id: "run-1",
    workflow_id: "research_pipeline",
    status: "completed",
    trigger: "manual",
    current_step: 2,
    total_steps: 2,
    started_at: "2026-02-24T10:00:00Z",
    completed_at: "2026-02-24T10:05:00Z",
    error: null,
    step_runs: [
      { id: "sr1", step_name: "Refresh Data", step_type: "data_refresh", order: 1, status: "completed", duration_seconds: 120.5, error: null, condition_met: true },
      { id: "sr2", step_name: "Screen Strategies", step_type: "vbt_screen", order: 2, status: "completed", duration_seconds: 180.3, error: null, condition_met: true },
    ],
  };

  function jsonResponse(data: unknown, status = 200): Response {
    return new Response(JSON.stringify(data), {
      status,
      headers: { "Content-Type": "application/json" },
    });
  }

  function detailFetch(input: RequestInfo | URL) {
    const url = typeof input === "string" ? input : input.toString();
    // Order matters: match most specific patterns first
    if (url.includes("/api/workflow-runs/run-1")) return Promise.resolve(jsonResponse(mockRunDetail));
    if (url.includes("/api/workflow-steps")) return Promise.resolve(jsonResponse(mockStepTypes));
    if (url.includes("/runs/")) return Promise.resolve(jsonResponse(mockRuns));
    if (url.includes("/api/workflows/research_pipeline")) return Promise.resolve(jsonResponse(mockDetail));
    if (url.includes("/api/workflows/signal_pipeline")) return Promise.resolve(jsonResponse(mockDetail));
    if (url.includes("/api/workflows/")) return Promise.resolve(jsonResponse(mockWorkflows));
    if (url.startsWith("/api/")) return Promise.resolve(jsonResponse([]));
    return Promise.reject(new Error(`Unhandled fetch: ${url}`));
  }

  beforeEach(() => {
    vi.stubGlobal("fetch", detailFetch as typeof globalThis.fetch);
  });

  it("expands workflow detail when Details is clicked", async () => {
    renderWithProviders(<Workflows />);
    await screen.findByText("Research Pipeline");
    const detailButtons = screen.getAllByText("Details");
    fireEvent.click(detailButtons[0]);
    expect(await screen.findByText("Steps")).toBeInTheDocument();
  });

  it("shows workflow steps in expanded detail", async () => {
    renderWithProviders(<Workflows />);
    await screen.findByText("Research Pipeline");
    const detailButtons = screen.getAllByText("Details");
    fireEvent.click(detailButtons[0]);
    expect(await screen.findByText("Refresh Data")).toBeInTheDocument();
    expect(await screen.findByText("Screen Strategies")).toBeInTheDocument();
  });

  it("shows step condition when present", async () => {
    renderWithProviders(<Workflows />);
    await screen.findByText("Research Pipeline");
    const detailButtons = screen.getAllByText("Details");
    fireEvent.click(detailButtons[0]);
    expect(await screen.findByText("if: prev_success")).toBeInTheDocument();
  });

  it("shows run history in expanded detail", async () => {
    renderWithProviders(<Workflows />);
    await screen.findByText("Research Pipeline");
    const detailButtons = screen.getAllByText("Details");
    fireEvent.click(detailButtons[0]);
    expect(await screen.findByText("Run History")).toBeInTheDocument();
  });

  it("shows run status badges", async () => {
    renderWithProviders(<Workflows />);
    await screen.findByText("Research Pipeline");
    const detailButtons = screen.getAllByText("Details");
    fireEvent.click(detailButtons[0]);
    expect(await screen.findByText("completed")).toBeInTheDocument();
    expect(await screen.findByText("failed")).toBeInTheDocument();
  });

  it("shows run trigger type", async () => {
    renderWithProviders(<Workflows />);
    await screen.findByText("Research Pipeline");
    const detailButtons = screen.getAllByText("Details");
    fireEvent.click(detailButtons[0]);
    expect(await screen.findByText("manual")).toBeInTheDocument();
  });

  it("expands run detail when run is clicked", async () => {
    renderWithProviders(<Workflows />);
    await screen.findByText("Research Pipeline");
    const detailButtons = screen.getAllByText("Details");
    fireEvent.click(detailButtons[0]);
    // Wait for runs to load, then click the completed run row
    const completedBadge = await screen.findByText("completed");
    const runButton = completedBadge.closest("button");
    if (runButton) fireEvent.click(runButton);
    // Should show step run details with duration
    expect(await screen.findByText("120.5s")).toBeInTheDocument();
    expect(await screen.findByText("180.3s")).toBeInTheDocument();
  });

  it("collapses expanded detail when Collapse is clicked", async () => {
    renderWithProviders(<Workflows />);
    await screen.findByText("Research Pipeline");
    const detailButtons = screen.getAllByText("Details");
    fireEvent.click(detailButtons[0]);
    expect(await screen.findByText("Steps")).toBeInTheDocument();
    // Button should now show "Collapse"
    fireEvent.click(screen.getByText("Collapse"));
    // Steps section should be gone
    expect(screen.queryByText("Steps")).not.toBeInTheDocument();
  });
});

describe("Workflows - Step Types Panel", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/workflows/": mockWorkflows,
        "/api/workflow-steps": mockStepTypes,
      }),
    );
  });

  it("shows step types when toggle is clicked", async () => {
    renderWithProviders(<Workflows />);
    fireEvent.click(screen.getByText("Show Available Step Types"));
    expect(await screen.findByText("data_refresh")).toBeInTheDocument();
    expect(await screen.findByText("vbt_screen")).toBeInTheDocument();
    expect(await screen.findByText("sentiment_aggregate")).toBeInTheDocument();
  });

  it("shows step type descriptions", async () => {
    renderWithProviders(<Workflows />);
    fireEvent.click(screen.getByText("Show Available Step Types"));
    expect(await screen.findByText("Refresh OHLCV data")).toBeInTheDocument();
    expect(await screen.findByText("Run VectorBT screening")).toBeInTheDocument();
  });

  it("hides step types when toggle is clicked again", async () => {
    renderWithProviders(<Workflows />);
    fireEvent.click(screen.getByText("Show Available Step Types"));
    expect(await screen.findByText("data_refresh")).toBeInTheDocument();
    fireEvent.click(screen.getByText("Hide Available Step Types"));
    expect(screen.queryByText("data_refresh")).not.toBeInTheDocument();
  });
});

describe("Workflows - Mutation Errors", () => {
  it("shows error toast when enable mutation fails", async () => {
    const enableFetch = (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input.toString();
      if (url.includes("/enable") && init?.method === "POST") {
        return Promise.reject(new TypeError("Network error"));
      }
      if (url.includes("/api/workflows/")) return Promise.resolve(new Response(JSON.stringify(mockWorkflows), { status: 200, headers: { "Content-Type": "application/json" } }));
      if (url.includes("/api/workflow-steps")) return Promise.resolve(new Response(JSON.stringify(mockStepTypes), { status: 200, headers: { "Content-Type": "application/json" } }));
      return Promise.resolve(new Response(JSON.stringify([]), { status: 200, headers: { "Content-Type": "application/json" } }));
    };
    vi.stubGlobal("fetch", enableFetch as typeof globalThis.fetch);
    renderWithProviders(<Workflows />);
    // Signal Pipeline has schedule_enabled=false → "Enable" button
    const enableBtn = await screen.findByText("Enable");
    fireEvent.click(enableBtn);
    expect(await screen.findByText(/Network error|Failed to enable/)).toBeInTheDocument();
  });
});

describe("Workflows - Empty State Text", () => {
  it("shows no workflows found message", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/workflows/": [],
        "/api/workflow-steps": mockStepTypes,
      }),
    );
    renderWithProviders(<Workflows />);
    expect(
      await screen.findByText("No workflows found for this asset class."),
    ).toBeInTheDocument();
  });
});
