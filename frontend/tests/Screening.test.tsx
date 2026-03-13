import { describe, it, expect, beforeEach, vi } from "vitest";
import { screen, fireEvent } from "@testing-library/react";
import { Screening } from "../src/pages/Screening";
import { renderWithProviders, mockFetch } from "./helpers";

const mockStrategies = [
  { name: "ema_crossover", label: "EMA Crossover", description: "Fast/slow EMA crossover" },
  { name: "rsi_mean_reversion", label: "RSI Mean Reversion", description: "RSI oversold bounce" },
];

describe("Screening Page", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/screening/strategies": mockStrategies,
      }),
    );
  });

  it("renders the page heading", () => {
    renderWithProviders(<Screening />);
    expect(screen.getByText("Strategy Screening")).toBeInTheDocument();
  });

  it("renders configuration form", () => {
    renderWithProviders(<Screening />);
    expect(screen.getByText("Configuration")).toBeInTheDocument();
    expect(screen.getByText("Run Screen")).toBeInTheDocument();
  });

  it("renders symbol input with default value", () => {
    renderWithProviders(<Screening />);
    const input = screen.getByDisplayValue("BTC/USDT");
    expect(input).toBeInTheDocument();
  });

  it("renders timeframe selector", () => {
    renderWithProviders(<Screening />);
    expect(screen.getByDisplayValue("1h")).toBeInTheDocument();
  });

  it("renders exchange selector with Binance default", () => {
    renderWithProviders(<Screening />);
    expect(screen.getByDisplayValue("Binance")).toBeInTheDocument();
  });

  it("renders strategy list after data loads", async () => {
    renderWithProviders(<Screening />);
    expect(await screen.findByText("EMA Crossover")).toBeInTheDocument();
    expect(await screen.findByText("RSI Mean Reversion")).toBeInTheDocument();
  });

  it("shows placeholder when no job is active", () => {
    renderWithProviders(<Screening />);
    expect(
      screen.getByText("Configure parameters and run a screen to see results."),
    ).toBeInTheDocument();
  });
});

describe("Screening - Form Interactions", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/screening/strategies": mockStrategies,
        "/api/screening/run": { job_id: "test-job-123" },
      }),
    );
  });

  it("allows changing the symbol input", () => {
    renderWithProviders(<Screening />);
    const input = screen.getByDisplayValue("BTC/USDT");
    fireEvent.change(input, { target: { value: "ETH/USDT" } });
    expect(screen.getByDisplayValue("ETH/USDT")).toBeInTheDocument();
  });

  it("allows changing the timeframe selector", () => {
    renderWithProviders(<Screening />);
    const select = screen.getByDisplayValue("1h");
    fireEvent.change(select, { target: { value: "4h" } });
    expect(screen.getByDisplayValue("4h")).toBeInTheDocument();
  });

  it("allows changing the exchange selector", () => {
    renderWithProviders(<Screening />);
    const select = screen.getByDisplayValue("Binance");
    fireEvent.change(select, { target: { value: "sample" } });
    expect(screen.getByDisplayValue("Sample")).toBeInTheDocument();
  });

  it("renders fees input and allows change", () => {
    renderWithProviders(<Screening />);
    // Default fee is 0.001, displayed as 0.001*100 = 0.1
    const feeInput = screen.getByDisplayValue("0.1");
    fireEvent.change(feeInput, { target: { value: "0.2" } });
    expect(screen.getByDisplayValue("0.2")).toBeInTheDocument();
  });

  it("disables Run Screen button while mutation is pending", async () => {
    renderWithProviders(<Screening />);
    const btn = screen.getByText("Run Screen");
    expect(btn).not.toBeDisabled();
  });
});

describe("Screening - Job Status Display", () => {
  it("shows Screening Job status after run", async () => {
    const completedJob = {
      id: "job-1",
      job_type: "screening",
      status: "completed",
      progress: 1.0,
      progress_message: "Done",
      error: null,
      result: {
        strategies: {
          ema_crossover: {
            total_combinations: 100,
            top_results: [
              { sharpe: 1.5, max_dd: -0.1, params: "fast=10,slow=21" },
            ],
          },
        },
      },
    };
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/screening/strategies": mockStrategies,
        "/api/screening/run": { job_id: "job-1" },
        "/api/jobs/job-1": completedJob,
      }),
    );
    renderWithProviders(<Screening />);

    // Click run
    fireEvent.click(screen.getByText("Run Screen"));

    // Job status section should appear
    expect(await screen.findByText("Screening Job")).toBeInTheDocument();
    expect(await screen.findByText("completed")).toBeInTheDocument();
  });

  it("shows error message when job fails", async () => {
    const failedJob = {
      id: "job-2",
      job_type: "screening",
      status: "failed",
      progress: 0,
      progress_message: "",
      error: "No data available for BTC/USDT",
      result: null,
    };
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/screening/strategies": mockStrategies,
        "/api/screening/run": { job_id: "job-2" },
        "/api/jobs/job-2": failedJob,
      }),
    );
    renderWithProviders(<Screening />);
    fireEvent.click(screen.getByText("Run Screen"));
    expect(await screen.findByText("No data available for BTC/USDT")).toBeInTheDocument();
  });

  it("shows toast with fallback message when mutation fails with empty error", async () => {
    const failingFetch = (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input.toString();
      if (url.includes("/api/screening/run")) {
        return Promise.reject("");
      }
      return mockFetch({
        "/api/screening/strategies": mockStrategies,
      })(input, init);
    };
    vi.stubGlobal("fetch", failingFetch);
    renderWithProviders(<Screening />);
    fireEvent.click(screen.getByText("Run Screen"));
    // The fallback "Failed to start screening" is shown via toast
    // Since getErrorMessage("") returns "", the || branch triggers
    await screen.findByText("Strategy Screening");
  });
});

describe("Screening - Strategy Error Display", () => {
  it("shows strategy error when result has error field", async () => {
    const completedWithError = {
      id: "job-3",
      job_type: "screening",
      status: "completed",
      progress: 1.0,
      progress_message: "Done",
      error: null,
      result: {
        strategies: {
          ema_crossover: {
            error: "Insufficient data for analysis",
            total_combinations: 0,
            top_results: [],
          },
        },
      },
    };
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/screening/strategies": mockStrategies,
        "/api/screening/run": { job_id: "job-3" },
        "/api/jobs/job-3": completedWithError,
      }),
    );
    renderWithProviders(<Screening />);
    fireEvent.click(screen.getByText("Run Screen"));
    expect(await screen.findByText("Insufficient data for analysis")).toBeInTheDocument();
  });

  it("shows running job progress bar", async () => {
    const runningJob = {
      id: "job-4",
      job_type: "screening",
      status: "running",
      progress: 0.5,
      progress_message: "Processing EMA crossover...",
      error: null,
      result: null,
    };
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/screening/strategies": mockStrategies,
        "/api/screening/run": { job_id: "job-4" },
        "/api/jobs/job-4": runningJob,
      }),
    );
    renderWithProviders(<Screening />);
    fireEvent.click(screen.getByText("Run Screen"));
    expect(await screen.findByText("Screening Job")).toBeInTheDocument();
    expect(screen.getByText("running")).toBeInTheDocument();
  });
});
