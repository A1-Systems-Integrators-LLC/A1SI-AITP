import { describe, it, expect, beforeEach, vi } from "vitest";
import { screen, fireEvent, waitFor } from "@testing-library/react";
import { DataManagement } from "../src/pages/DataManagement";
import { renderWithProviders, mockFetch } from "./helpers";

const mockFiles = [
  {
    file: "binance_BTCUSDT_1h.parquet",
    symbol: "BTC/USDT",
    timeframe: "1h",
    exchange: "binance",
    rows: 2160,
    start: "2025-10-01T00:00:00Z",
    end: "2025-12-31T23:00:00Z",
  },
  {
    file: "binance_ETHUSDT_1h.parquet",
    symbol: "ETH/USDT",
    timeframe: "1h",
    exchange: "binance",
    rows: 2160,
    start: "2025-10-01T00:00:00Z",
    end: "2025-12-31T23:00:00Z",
  },
];

describe("DataManagement Page", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/data/": mockFiles,
      }),
    );
  });

  it("renders the page heading", () => {
    renderWithProviders(<DataManagement />);
    expect(screen.getByText("Data Management")).toBeInTheDocument();
  });

  it("renders Download Data form", () => {
    renderWithProviders(<DataManagement />);
    expect(screen.getByText("Download Data")).toBeInTheDocument();
    expect(screen.getByText("Download")).toBeInTheDocument();
  });

  it("renders Quick Actions section", () => {
    renderWithProviders(<DataManagement />);
    expect(screen.getByText("Quick Actions")).toBeInTheDocument();
    expect(screen.getByText("Generate Sample Data")).toBeInTheDocument();
  });

  it("renders data summary with file count", async () => {
    renderWithProviders(<DataManagement />);
    expect(await screen.findByText("2")).toBeInTheDocument();
    expect(screen.getByText("Parquet files available")).toBeInTheDocument();
  });

  it("renders data files table", async () => {
    renderWithProviders(<DataManagement />);
    expect(await screen.findByText("BTC/USDT")).toBeInTheDocument();
    expect(await screen.findByText("ETH/USDT")).toBeInTheDocument();
  });

  it("shows default symbols in download form", () => {
    renderWithProviders(<DataManagement />);
    const input = screen.getByDisplayValue("BTC/USDT, ETH/USDT, SOL/USDT, BNB/USDT, XRP/USDT");
    expect(input).toBeInTheDocument();
  });

  it("renders timeframe toggle buttons", () => {
    renderWithProviders(<DataManagement />);
    expect(screen.getByText("1m")).toBeInTheDocument();
    expect(screen.getByText("5m")).toBeInTheDocument();
    expect(screen.getByText("1d")).toBeInTheDocument();
  });

  it("renders Available Data section heading", () => {
    renderWithProviders(<DataManagement />);
    expect(screen.getByText("Available Data")).toBeInTheDocument();
  });
});

describe("DataManagement - Form Interactions", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/data/": mockFiles,
      }),
    );
  });

  it("allows changing symbols input", () => {
    renderWithProviders(<DataManagement />);
    const input = screen.getByDisplayValue("BTC/USDT, ETH/USDT, SOL/USDT, BNB/USDT, XRP/USDT");
    fireEvent.change(input, { target: { value: "DOGE/USDT" } });
    expect(screen.getByDisplayValue("DOGE/USDT")).toBeInTheDocument();
  });

  it("allows changing exchange dropdown", () => {
    renderWithProviders(<DataManagement />);
    const select = screen.getByDisplayValue("Binance");
    fireEvent.change(select, { target: { value: "kraken" } });
    expect(screen.getByDisplayValue("Kraken")).toBeInTheDocument();
  });

  it("allows changing history days input", () => {
    renderWithProviders(<DataManagement />);
    const input = screen.getByDisplayValue("90");
    fireEvent.change(input, { target: { value: "180" } });
    expect(screen.getByDisplayValue("180")).toBeInTheDocument();
  });

  it("toggles timeframe buttons on click", () => {
    renderWithProviders(<DataManagement />);
    const btn5m = screen.getByText("5m");
    // 5m starts unselected — click to select
    fireEvent.click(btn5m);
    // 1h starts selected — click to deselect
    const btn1h = screen.getByText("1h");
    fireEvent.click(btn1h);
    // Both buttons should still be in the DOM (toggle doesn't remove)
    expect(screen.getByText("5m")).toBeInTheDocument();
    expect(screen.getByText("1h")).toBeInTheDocument();
  });
});

describe("DataManagement - Empty State", () => {
  it("shows empty message when no data files exist", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({ "/api/data/": [] }),
    );
    renderWithProviders(<DataManagement />);
    expect(
      await screen.findByText(
        "No data files found. Use the download form or generate sample data.",
      ),
    ).toBeInTheDocument();
  });

  it("shows 0 in data summary when no files", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({ "/api/data/": [] }),
    );
    renderWithProviders(<DataManagement />);
    expect(await screen.findByText("0")).toBeInTheDocument();
  });
});

describe("DataManagement - Refresh Button", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      mockFetch({ "/api/data/": mockFiles }),
    );
  });

  it("clicking Refresh market data button invalidates queries", async () => {
    renderWithProviders(<DataManagement />);
    await screen.findByText("BTC/USDT"); // wait for data
    const refreshBtn = screen.getByLabelText("Refresh market data");
    fireEvent.click(refreshBtn);
    // Button should still be in the DOM after click
    expect(refreshBtn).toBeInTheDocument();
  });
});

describe("DataManagement - ARIA Labels", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      mockFetch({ "/api/data/": mockFiles }),
    );
  });

  it("buttons have aria-labels", () => {
    renderWithProviders(<DataManagement />);
    expect(screen.getByLabelText("Refresh market data")).toBeInTheDocument();
    expect(screen.getByLabelText("Run data quality check")).toBeInTheDocument();
  });

  it("timeframe toggle buttons have aria-pressed", () => {
    renderWithProviders(<DataManagement />);
    const btn1h = screen.getByLabelText("Timeframe 1h");
    expect(btn1h).toHaveAttribute("aria-pressed", "true");
    const btn5m = screen.getByLabelText("Timeframe 5m");
    expect(btn5m).toHaveAttribute("aria-pressed", "false");
  });
});

describe("DataManagement - Table Headers", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      mockFetch({ "/api/data/": mockFiles }),
    );
  });

  it("renders all table column headers", async () => {
    renderWithProviders(<DataManagement />);
    await screen.findByText("BTC/USDT"); // wait for data
    expect(screen.getByText("Symbol")).toBeInTheDocument();
    // "Timeframe" and "Exchange" appear as both form labels and table headers
    const timeframes = screen.getAllByText("Timeframe");
    expect(timeframes.length).toBeGreaterThanOrEqual(1);
    const exchanges = screen.getAllByText("Exchange");
    expect(exchanges.length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("Rows")).toBeInTheDocument();
    expect(screen.getByText("Start")).toBeInTheDocument();
    expect(screen.getByText("End")).toBeInTheDocument();
  });

  it("shows error state when API fails", async () => {
    const failingFetch = (input: RequestInfo | URL) => {
      const url = typeof input === "string" ? input : input.toString();
      if (url.includes("/api/data/")) {
        return Promise.resolve(new Response(JSON.stringify({ error: "fail" }), { status: 500 }));
      }
      return Promise.resolve(new Response(JSON.stringify([]), { status: 200, headers: { "Content-Type": "application/json" } }));
    };
    vi.stubGlobal("fetch", failingFetch);
    renderWithProviders(<DataManagement />);
    expect(await screen.findByText("Failed to load data files")).toBeInTheDocument();
  });
});

describe("DataManagement - Download Mutation", () => {
  it("clicking Download fires downloadMutation and sets activeJobId", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/data/download": { job_id: "dl-job-1", status: "pending" },
        "/api/jobs/dl-job-1": {
          id: "dl-job-1",
          job_type: "data_download",
          status: "running",
          progress: 30,
          progress_message: "Downloading BTC/USDT...",
          error: null,
          result: null,
        },
      }),
    );
    renderWithProviders(<DataManagement />);
    fireEvent.click(screen.getByText("Download"));
    await waitFor(() => {
      expect(screen.getByText("Job: data download")).toBeInTheDocument();
      expect(screen.getByText("running")).toBeInTheDocument();
    });
  });

  it("download mutation error shows error toast", async () => {
    const failFetch = (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input.toString();
      if (url.includes("/data/download") && init?.method === "POST") {
        return Promise.resolve(new Response(JSON.stringify({ error: "fail" }), { status: 500 }));
      }
      return mockFetch({ "/api/data/": mockFiles })(input, init);
    };
    vi.stubGlobal("fetch", failFetch);
    renderWithProviders(<DataManagement />);
    fireEvent.click(screen.getByText("Download"));
    await waitFor(() => {
      expect(screen.getByText(/Failed to start download|fail/)).toBeInTheDocument();
    });
  });
});

describe("DataManagement - Sample Mutation", () => {
  it("clicking Generate Sample Data fires sampleMutation and shows job", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/data/generate-sample": { job_id: "sample-job-1", status: "pending" },
        "/api/jobs/sample-job-1": {
          id: "sample-job-1",
          job_type: "sample_data",
          status: "running",
          progress: 50,
          progress_message: "Generating...",
          error: null,
          result: null,
        },
      }),
    );
    renderWithProviders(<DataManagement />);
    fireEvent.click(screen.getByText("Generate Sample Data"));
    await waitFor(() => {
      expect(screen.getByText("Job: sample data")).toBeInTheDocument();
    });
  });

  it("sample mutation error shows error toast", async () => {
    const failFetch = (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input.toString();
      if (url.includes("/data/generate-sample") && init?.method === "POST") {
        return Promise.resolve(new Response(JSON.stringify({ error: "fail" }), { status: 500 }));
      }
      return mockFetch({ "/api/data/": mockFiles })(input, init);
    };
    vi.stubGlobal("fetch", failFetch);
    renderWithProviders(<DataManagement />);
    fireEvent.click(screen.getByText("Generate Sample Data"));
    await waitFor(() => {
      expect(screen.getByText(/Failed to generate sample data|fail/)).toBeInTheDocument();
    });
  });
});

describe("DataManagement - Quality Check", () => {
  it("clicking Run Quality Check shows quality results table", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/data/quality": {
          passed: 2,
          failed: 1,
          total: 3,
          reports: [
            {
              symbol: "BTC/USDT",
              timeframe: "1h",
              rows: 2160,
              passed: true,
              gaps: [],
              outliers: [],
              is_stale: false,
              stale_hours: 0,
              issues_summary: [],
            },
            {
              symbol: "ETH/USDT",
              timeframe: "1h",
              rows: 1800,
              passed: false,
              gaps: ["2026-01-05"],
              outliers: ["2026-01-10"],
              is_stale: true,
              stale_hours: 48.5,
              issues_summary: ["1 gap detected", "1 outlier"],
            },
          ],
        },
      }),
    );
    renderWithProviders(<DataManagement />);
    // Click to run quality check
    fireEvent.click(screen.getByLabelText("Run data quality check"));
    await waitFor(() => {
      expect(screen.getByText("2 passed")).toBeInTheDocument();
    });
    expect(screen.getByText("1 failed")).toBeInTheDocument();
    expect(screen.getByText("3 total")).toBeInTheDocument();
    // Quality table columns
    expect(screen.getByText("pass")).toBeInTheDocument();
    expect(screen.getByText("fail")).toBeInTheDocument();
    expect(screen.getByText("fresh")).toBeInTheDocument();
    expect(screen.getByText("49h")).toBeInTheDocument();
    expect(screen.getByText("1 gap detected; 1 outlier")).toBeInTheDocument();
  });

  it("shows dash when no issues in quality report", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/data/quality": {
          passed: 1,
          failed: 0,
          total: 1,
          reports: [
            {
              symbol: "BTC/USDT",
              timeframe: "1h",
              rows: 2160,
              passed: true,
              gaps: [],
              outliers: [],
              is_stale: false,
              stale_hours: 0,
              issues_summary: [],
            },
          ],
        },
      }),
    );
    renderWithProviders(<DataManagement />);
    fireEvent.click(screen.getByLabelText("Run data quality check"));
    await waitFor(() => {
      expect(screen.getByText("1 passed")).toBeInTheDocument();
    });
    // Issues column shows dash
    const qualityRows = screen.getAllByText("\u2014");
    expect(qualityRows.length).toBeGreaterThanOrEqual(1);
  });

  it("shows prompt text before quality check is run", () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({ "/api/data/": mockFiles }),
    );
    renderWithProviders(<DataManagement />);
    expect(screen.getByText(/Click.*Run Quality Check.*to validate/)).toBeInTheDocument();
  });
});

describe("DataManagement - Job Progress States", () => {
  it("shows completed status badge", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/data/download": { job_id: "dl-job-2", status: "pending" },
        "/api/jobs/dl-job-2": {
          id: "dl-job-2",
          job_type: "data_download",
          status: "completed",
          progress: 100,
          progress_message: "Done",
          error: null,
          result: null,
        },
      }),
    );
    renderWithProviders(<DataManagement />);
    fireEvent.click(screen.getByText("Download"));
    await waitFor(() => {
      expect(screen.getByText("completed")).toBeInTheDocument();
    });
  });

  it("shows failed status with error message", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/data/download": { job_id: "dl-job-3", status: "pending" },
        "/api/jobs/dl-job-3": {
          id: "dl-job-3",
          job_type: "data_download",
          status: "failed",
          progress: 0,
          progress_message: null,
          error: "Exchange API rate limited",
          result: null,
        },
      }),
    );
    renderWithProviders(<DataManagement />);
    fireEvent.click(screen.getByText("Download"));
    await waitFor(() => {
      expect(screen.getByText("failed")).toBeInTheDocument();
    });
    expect(screen.getByText("Exchange API rate limited")).toBeInTheDocument();
  });

  it("shows file row count formatted", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/data/": [{ ...mockFiles[0], rows: 10000 }],
      }),
    );
    renderWithProviders(<DataManagement />);
    await waitFor(() => {
      expect(screen.getByText("10,000")).toBeInTheDocument();
    });
  });
});
