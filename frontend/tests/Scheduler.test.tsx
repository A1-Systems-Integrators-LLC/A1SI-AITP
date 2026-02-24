import { describe, it, expect, beforeEach, vi } from "vitest";
import { screen } from "@testing-library/react";
import { Scheduler } from "../src/pages/Scheduler";
import { renderWithProviders, mockFetch } from "./helpers";

const mockStatus = {
  running: true,
  total_tasks: 5,
  active_tasks: 3,
  paused_tasks: 2,
};

const mockTasks = [
  {
    id: "data_refresh_crypto",
    name: "Data Refresh (Crypto)",
    description: "Refresh crypto OHLCV data",
    task_type: "data_refresh",
    status: "active",
    interval_seconds: 3600,
    params: { asset_class: "crypto" },
    last_run_at: "2026-02-24T10:00:00Z",
    last_run_status: "completed",
    last_run_job_id: "abc",
    next_run_at: "2026-02-24T11:00:00Z",
    run_count: 42,
    error_count: 1,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-02-24T10:00:00Z",
  },
  {
    id: "regime_detection",
    name: "Regime Detection",
    description: "Detect market regimes",
    task_type: "regime_detection",
    status: "paused",
    interval_seconds: 120,
    params: {},
    last_run_at: null,
    last_run_status: null,
    last_run_job_id: null,
    next_run_at: null,
    run_count: 0,
    error_count: 0,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  },
];

describe("Scheduler Page", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/scheduler/status": mockStatus,
        "/api/scheduler/tasks": mockTasks,
      }),
    );
  });

  it("renders the page heading", () => {
    renderWithProviders(<Scheduler />);
    expect(screen.getByText("Scheduler")).toBeInTheDocument();
  });

  it("renders status cards", async () => {
    renderWithProviders(<Scheduler />);
    expect(await screen.findByText("Running")).toBeInTheDocument();
  });

  it("renders task list", async () => {
    renderWithProviders(<Scheduler />);
    expect(await screen.findByText("Data Refresh (Crypto)")).toBeInTheDocument();
    expect(screen.getByText("Regime Detection")).toBeInTheDocument();
  });

  it("shows pause button for active tasks", async () => {
    renderWithProviders(<Scheduler />);
    await screen.findByText("Data Refresh (Crypto)");
    const pauseButtons = screen.getAllByText("Pause");
    expect(pauseButtons.length).toBeGreaterThan(0);
  });

  it("shows resume button for paused tasks", async () => {
    renderWithProviders(<Scheduler />);
    await screen.findByText("Regime Detection");
    const resumeButtons = screen.getAllByText("Resume");
    expect(resumeButtons.length).toBeGreaterThan(0);
  });
});

describe("Scheduler - Status Cards", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/scheduler/status": mockStatus,
        "/api/scheduler/tasks": mockTasks,
      }),
    );
  });

  it("shows total tasks count", async () => {
    renderWithProviders(<Scheduler />);
    expect(await screen.findByText("5")).toBeInTheDocument();
  });

  it("shows active tasks count", async () => {
    renderWithProviders(<Scheduler />);
    expect(await screen.findByText("3")).toBeInTheDocument();
  });

  it("shows paused tasks count", async () => {
    renderWithProviders(<Scheduler />);
    expect(await screen.findByText("2")).toBeInTheDocument();
  });

  it("shows stopped state when not running", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/scheduler/status": { ...mockStatus, running: false },
        "/api/scheduler/tasks": mockTasks,
      }),
    );
    renderWithProviders(<Scheduler />);
    expect(await screen.findByText("Stopped")).toBeInTheDocument();
  });

  it("shows trigger buttons for each task", async () => {
    renderWithProviders(<Scheduler />);
    await screen.findByText("Data Refresh (Crypto)");
    const triggerButtons = screen.getAllByText("Trigger");
    expect(triggerButtons.length).toBe(2);
  });

  it("shows empty state when no tasks", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/scheduler/status": { running: true, total_tasks: 0, active_tasks: 0, paused_tasks: 0 },
        "/api/scheduler/tasks": [],
      }),
    );
    renderWithProviders(<Scheduler />);
    expect(await screen.findByText("No scheduled tasks found.")).toBeInTheDocument();
  });

  it("shows error state when API fails", async () => {
    const failingFetch = (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input.toString();
      if (url.includes("scheduler/tasks")) {
        return Promise.resolve(new Response(JSON.stringify({ error: "fail" }), { status: 500 }));
      }
      return mockFetch({ "/api/scheduler/status": mockStatus })(input, init);
    };
    vi.stubGlobal("fetch", failingFetch);
    renderWithProviders(<Scheduler />);
    expect(await screen.findByText("Failed to load scheduler tasks")).toBeInTheDocument();
  });
});
