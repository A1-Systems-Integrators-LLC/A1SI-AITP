import { describe, it, expect, beforeEach, vi } from "vitest";
import { screen, fireEvent } from "@testing-library/react";
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
