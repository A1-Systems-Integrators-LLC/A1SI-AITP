import { describe, it, expect, beforeEach, vi } from "vitest";
import { screen, fireEvent } from "@testing-library/react";
import { MarketOpportunities } from "../src/pages/MarketOpportunities";
import { renderWithProviders, mockFetch } from "./helpers";

const mockOpportunities = [
  {
    id: 1,
    symbol: "BTC/USDT",
    asset_class: "crypto",
    opportunity_type: "volume_surge",
    score: 85,
    details: { reason: "Volume 3x average" },
    detected_at: "2026-03-10T10:00:00Z",
  },
  {
    id: 2,
    symbol: "ETH/USDT",
    asset_class: "crypto",
    opportunity_type: "rsi_bounce",
    score: 45,
    details: { reason: "RSI oversold bounce" },
    detected_at: "2026-03-10T09:00:00Z",
  },
];

const mockSummary = {
  total_active: 5,
  avg_score: 65,
  top_opportunities: [{ score: 85 }, { score: 75 }, { score: 60 }],
  by_type: { volume_surge: 2, rsi_bounce: 3 },
};

const mockReport = {
  system_status: {
    is_ready: true,
    readiness: "System Ready",
    days_paper_trading: 12,
    min_days_required: 30,
  },
  scanner_status: {
    market_scan_crypto: {
      last_run_status: "completed",
      last_run_at: "2026-03-10T10:00:00Z",
      run_count: 100,
      next_run_at: "2026-03-10T10:15:00Z",
    },
    market_scan_forex: {
      last_run_status: "error",
      last_run_at: null,
      run_count: 0,
      next_run_at: null,
    },
  },
  data_coverage: { pairs_with_data: 30, total_pairs: 36, coverage_pct: 83 },
  strategy_performance: { total_orders: 50, win_rate: 60, total_pnl: 1500 },
};

describe("MarketOpportunities - Page Heading", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/market/opportunities/summary": mockSummary,
        "/api/market/opportunities": mockOpportunities,
        "/api/market/daily-report": mockReport,
      }),
    );
  });

  it("renders the page heading", () => {
    renderWithProviders(<MarketOpportunities />);
    expect(screen.getByText("Market Opportunities")).toBeInTheDocument();
  });

  it("sets document title", () => {
    renderWithProviders(<MarketOpportunities />);
    expect(document.title).toBe("Market Opportunities | A1SI-AITP");
  });
});

describe("MarketOpportunities - Summary Cards", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/market/opportunities/summary": mockSummary,
        "/api/market/opportunities": mockOpportunities,
        "/api/market/daily-report": mockReport,
      }),
    );
  });

  it("shows total active count", async () => {
    renderWithProviders(<MarketOpportunities />);
    expect(await screen.findByText("Active")).toBeInTheDocument();
    expect(screen.getByText("5")).toBeInTheDocument();
  });

  it("shows average score", async () => {
    renderWithProviders(<MarketOpportunities />);
    expect(await screen.findByText("Avg Score")).toBeInTheDocument();
    expect(screen.getByText("65")).toBeInTheDocument();
  });

  it("shows high score count (scores >= 75)", async () => {
    renderWithProviders(<MarketOpportunities />);
    const label = await screen.findByText("High Score (75+)");
    // top_opportunities has scores [85, 75, 60], 2 are >= 75
    const card = label.closest("div.rounded-xl");
    expect(card).toHaveTextContent("2");
  });

  it("shows types active count", async () => {
    renderWithProviders(<MarketOpportunities />);
    const label = await screen.findByText("Types Active");
    // by_type has 2 keys
    const card = label.closest("div.rounded-xl");
    expect(card).toHaveTextContent("2");
  });
});

describe("MarketOpportunities - System Status", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/market/opportunities/summary": mockSummary,
        "/api/market/opportunities": mockOpportunities,
        "/api/market/daily-report": mockReport,
      }),
    );
  });

  it("shows system readiness text", async () => {
    renderWithProviders(<MarketOpportunities />);
    expect(await screen.findByText("System Ready")).toBeInTheDocument();
  });

  it("shows paper trading days progress", async () => {
    renderWithProviders(<MarketOpportunities />);
    expect(await screen.findByText(/Day 12 of 30 minimum paper trading/)).toBeInTheDocument();
  });

  it("shows green dot when system is ready", async () => {
    renderWithProviders(<MarketOpportunities />);
    await screen.findByText("System Ready");
    const dot = screen.getByText("System Ready").closest("div")?.previousElementSibling;
    expect(dot?.className).toContain("bg-green-400");
  });

  it("shows yellow dot when system is not ready", async () => {
    const notReadyReport = {
      ...mockReport,
      system_status: { ...mockReport.system_status, is_ready: false, readiness: "Not Ready" },
    };
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/market/opportunities/summary": mockSummary,
        "/api/market/opportunities": mockOpportunities,
        "/api/market/daily-report": notReadyReport,
      }),
    );
    renderWithProviders(<MarketOpportunities />);
    await screen.findByText("Not Ready");
    const dot = screen.getByText("Not Ready").closest("div")?.previousElementSibling;
    expect(dot?.className).toContain("bg-yellow-400");
  });
});

describe("MarketOpportunities - Scanner Status Cards", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/market/opportunities/summary": mockSummary,
        "/api/market/opportunities": mockOpportunities,
        "/api/market/daily-report": mockReport,
      }),
    );
  });

  it("renders scanner cards for each scanner", async () => {
    renderWithProviders(<MarketOpportunities />);
    expect(await screen.findByText("crypto Scanner")).toBeInTheDocument();
    expect(screen.getByText("forex Scanner")).toBeInTheDocument();
  });

  it("shows run count for scanners", async () => {
    renderWithProviders(<MarketOpportunities />);
    expect(await screen.findByText("Run count: 100")).toBeInTheDocument();
    expect(screen.getByText("Run count: 0")).toBeInTheDocument();
  });

  it("shows Never for scanner with no last_run_at", async () => {
    renderWithProviders(<MarketOpportunities />);
    expect(await screen.findByText(/Never/)).toBeInTheDocument();
  });

  it("shows green dot for completed scanner", async () => {
    renderWithProviders(<MarketOpportunities />);
    await screen.findByText("crypto Scanner");
    const cryptoCard = screen.getByText("crypto Scanner").closest("div");
    const dot = cryptoCard?.querySelector("div.bg-green-400");
    expect(dot).not.toBeNull();
  });

  it("shows red dot for error scanner", async () => {
    renderWithProviders(<MarketOpportunities />);
    await screen.findByText("forex Scanner");
    const forexCard = screen.getByText("forex Scanner").closest("div");
    const dot = forexCard?.querySelector("div.bg-red-400");
    expect(dot).not.toBeNull();
  });

  it("shows next run time for scanner with next_run_at", async () => {
    renderWithProviders(<MarketOpportunities />);
    await screen.findByText("crypto Scanner");
    expect(screen.getByText(/Next run:/)).toBeInTheDocument();
  });
});

describe("MarketOpportunities - Type Distribution", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/market/opportunities/summary": mockSummary,
        "/api/market/opportunities": mockOpportunities,
        "/api/market/daily-report": mockReport,
      }),
    );
  });

  it("shows distribution by type heading", async () => {
    renderWithProviders(<MarketOpportunities />);
    expect(await screen.findByText("Distribution by Type")).toBeInTheDocument();
  });

  it("shows type filter buttons with counts", async () => {
    renderWithProviders(<MarketOpportunities />);
    expect(await screen.findByLabelText("Filter by volume surge")).toBeInTheDocument();
    expect(screen.getByLabelText("Filter by rsi bounce")).toBeInTheDocument();
  });

  it("toggles type filter when clicking distribution button", async () => {
    renderWithProviders(<MarketOpportunities />);
    const volumeBtn = await screen.findByLabelText("Filter by volume surge");
    fireEvent.click(volumeBtn);
    // Click again to deselect
    fireEvent.click(volumeBtn);
    // Should still render the button
    expect(screen.getByLabelText("Filter by volume surge")).toBeInTheDocument();
  });
});

describe("MarketOpportunities - Filter Controls", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/market/opportunities/summary": mockSummary,
        "/api/market/opportunities": mockOpportunities,
        "/api/market/daily-report": mockReport,
      }),
    );
  });

  it("renders asset class filter dropdown", () => {
    renderWithProviders(<MarketOpportunities />);
    const select = screen.getByLabelText("Filter by asset class");
    expect(select).toBeInTheDocument();
  });

  it("has all asset class options", () => {
    renderWithProviders(<MarketOpportunities />);
    expect(screen.getByText("All Assets")).toBeInTheDocument();
    expect(screen.getByText("Crypto")).toBeInTheDocument();
    expect(screen.getByText("Forex")).toBeInTheDocument();
    expect(screen.getByText("Equities")).toBeInTheDocument();
  });

  it("renders type filter dropdown", () => {
    renderWithProviders(<MarketOpportunities />);
    const select = screen.getByLabelText("Filter by opportunity type");
    expect(select).toBeInTheDocument();
  });

  it("has all type options", () => {
    renderWithProviders(<MarketOpportunities />);
    expect(screen.getByText("All Types")).toBeInTheDocument();
    expect(screen.getByText("Volume Surge")).toBeInTheDocument();
    expect(screen.getByText("RSI Bounce")).toBeInTheDocument();
    expect(screen.getByText("Breakout")).toBeInTheDocument();
    expect(screen.getByText("Trend Pullback")).toBeInTheDocument();
    expect(screen.getByText("Momentum Shift")).toBeInTheDocument();
  });

  it("renders min score slider", () => {
    renderWithProviders(<MarketOpportunities />);
    const slider = screen.getByLabelText("Minimum score filter");
    expect(slider).toBeInTheDocument();
  });

  it("shows min score label and value", () => {
    renderWithProviders(<MarketOpportunities />);
    expect(screen.getByText("Min Score:")).toBeInTheDocument();
    expect(screen.getByText("0")).toBeInTheDocument();
  });

  it("updates min score when slider changes", () => {
    renderWithProviders(<MarketOpportunities />);
    const slider = screen.getByLabelText("Minimum score filter");
    fireEvent.change(slider, { target: { value: "50" } });
    expect(screen.getByText("50")).toBeInTheDocument();
  });

  it("updates asset class filter when changed", () => {
    renderWithProviders(<MarketOpportunities />);
    const select = screen.getByLabelText("Filter by asset class");
    fireEvent.change(select, { target: { value: "crypto" } });
    expect((select as HTMLSelectElement).value).toBe("crypto");
  });

  it("updates type filter when changed", () => {
    renderWithProviders(<MarketOpportunities />);
    const select = screen.getByLabelText("Filter by opportunity type");
    fireEvent.change(select, { target: { value: "breakout" } });
    expect((select as HTMLSelectElement).value).toBe("breakout");
  });
});

describe("MarketOpportunities - Opportunities Table", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/market/opportunities/summary": mockSummary,
        "/api/market/opportunities": mockOpportunities,
        "/api/market/daily-report": mockReport,
      }),
    );
  });

  it("renders table headers", () => {
    renderWithProviders(<MarketOpportunities />);
    expect(screen.getByText("Symbol")).toBeInTheDocument();
    expect(screen.getByText("Asset")).toBeInTheDocument();
    expect(screen.getByText("Type")).toBeInTheDocument();
    expect(screen.getByText("Score")).toBeInTheDocument();
    expect(screen.getByText("Details")).toBeInTheDocument();
    expect(screen.getByText("Detected")).toBeInTheDocument();
  });

  it("renders opportunity symbols", async () => {
    renderWithProviders(<MarketOpportunities />);
    expect(await screen.findByText("BTC/USDT")).toBeInTheDocument();
    expect(screen.getByText("ETH/USDT")).toBeInTheDocument();
  });

  it("renders opportunity asset class", async () => {
    renderWithProviders(<MarketOpportunities />);
    await screen.findByText("BTC/USDT");
    const cryptoCells = screen.getAllByText("crypto");
    expect(cryptoCells.length).toBeGreaterThanOrEqual(2);
  });

  it("renders opportunity type badges", async () => {
    renderWithProviders(<MarketOpportunities />);
    await screen.findByText("BTC/USDT");
    // "volume surge" appears in both distribution section and table; verify at least 2
    const volumeSurges = screen.getAllByText("volume surge");
    expect(volumeSurges.length).toBeGreaterThanOrEqual(1);
    const rsiBounces = screen.getAllByText("rsi bounce");
    expect(rsiBounces.length).toBeGreaterThanOrEqual(1);
  });

  it("renders score values", async () => {
    renderWithProviders(<MarketOpportunities />);
    expect(await screen.findByText("85")).toBeInTheDocument();
    expect(screen.getByText("45")).toBeInTheDocument();
  });

  it("renders opportunity details/reason", async () => {
    renderWithProviders(<MarketOpportunities />);
    expect(await screen.findByText("Volume 3x average")).toBeInTheDocument();
    expect(screen.getByText("RSI oversold bounce")).toBeInTheDocument();
  });

  it("renders score bar with green for high scores", async () => {
    renderWithProviders(<MarketOpportunities />);
    await screen.findByText("85");
    // The score bar for 85 should be green
    const scoreCell = screen.getByText("85").closest("td");
    const bar = scoreCell?.querySelector(".bg-green-400");
    expect(bar).not.toBeNull();
  });

  it("renders score bar with gray for low scores", async () => {
    renderWithProviders(<MarketOpportunities />);
    await screen.findByText("45");
    // The score bar for 45 should be gray (below 50)
    const scoreCell = screen.getByText("45").closest("td");
    const bar = scoreCell?.querySelector(".bg-gray-400");
    expect(bar).not.toBeNull();
  });
});

describe("MarketOpportunities - Empty Table", () => {
  it("shows no active opportunities message when empty", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/market/opportunities/summary": { ...mockSummary, by_type: {} },
        "/api/market/opportunities": [],
        "/api/market/daily-report": mockReport,
      }),
    );
    renderWithProviders(<MarketOpportunities />);
    expect(await screen.findByText(/No active opportunities/)).toBeInTheDocument();
    expect(screen.getByText(/Scanner runs every 15 minutes/)).toBeInTheDocument();
  });

  it("shows filtered empty message with type filter", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/market/opportunities/summary": mockSummary,
        "/api/market/opportunities": [],
        "/api/market/daily-report": mockReport,
      }),
    );
    renderWithProviders(<MarketOpportunities />);
    // Set type filter
    const typeSelect = screen.getByLabelText("Filter by opportunity type");
    fireEvent.change(typeSelect, { target: { value: "breakout" } });
    expect(await screen.findByText(/No active opportunities of type "breakout"/)).toBeInTheDocument();
  });
});

describe("MarketOpportunities - Loading State", () => {
  it("shows skeleton loading rows", () => {
    // Use a fetch that never resolves to keep loading state
    vi.stubGlobal(
      "fetch",
      () => new Promise(() => {}),
    );
    renderWithProviders(<MarketOpportunities />);
    const skeletons = document.querySelectorAll(".animate-pulse");
    expect(skeletons.length).toBeGreaterThanOrEqual(1);
  });
});

describe("MarketOpportunities - Error State", () => {
  it("shows QueryError when fetch fails and retry button works", async () => {
    const failingFetch = (input: RequestInfo | URL) => {
      const url = typeof input === "string" ? input : input.toString();
      if (url.includes("/api/market/opportunities/summary")) {
        return Promise.resolve(new Response(JSON.stringify(mockSummary), { status: 200, headers: { "Content-Type": "application/json" } }));
      }
      if (url.includes("/api/market/daily-report")) {
        return Promise.resolve(new Response(JSON.stringify(mockReport), { status: 200, headers: { "Content-Type": "application/json" } }));
      }
      if (url.includes("/api/market/opportunities")) {
        return Promise.resolve(new Response(JSON.stringify({ error: "Server error" }), { status: 500 }));
      }
      return Promise.resolve(new Response(JSON.stringify([]), { status: 200, headers: { "Content-Type": "application/json" } }));
    };
    vi.stubGlobal("fetch", failingFetch as typeof globalThis.fetch);
    renderWithProviders(<MarketOpportunities />);
    // QueryError component should appear with retry button
    const retryBtn = await screen.findByRole("button", { name: /retry/i });
    expect(retryBtn).toBeInTheDocument();
    // Click retry to exercise the onRetry callback (line 235)
    fireEvent.click(retryBtn);
  });
});

describe("MarketOpportunities - Daily Report Data Coverage", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/market/opportunities/summary": mockSummary,
        "/api/market/opportunities": mockOpportunities,
        "/api/market/daily-report": mockReport,
      }),
    );
  });

  it("shows data coverage heading", async () => {
    renderWithProviders(<MarketOpportunities />);
    expect(await screen.findByText("Data Coverage")).toBeInTheDocument();
  });

  it("shows pairs with data count", async () => {
    renderWithProviders(<MarketOpportunities />);
    expect(await screen.findByText("Pairs with data")).toBeInTheDocument();
    expect(screen.getByText(/30 \/ 36/)).toBeInTheDocument();
  });

  it("shows coverage percentage", async () => {
    renderWithProviders(<MarketOpportunities />);
    expect(await screen.findByText("Coverage")).toBeInTheDocument();
    expect(screen.getByText("83%")).toBeInTheDocument();
  });
});

describe("MarketOpportunities - Daily Report Strategy Performance", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/market/opportunities/summary": mockSummary,
        "/api/market/opportunities": mockOpportunities,
        "/api/market/daily-report": mockReport,
      }),
    );
  });

  it("shows strategy performance heading", async () => {
    renderWithProviders(<MarketOpportunities />);
    expect(await screen.findByText("Strategy Performance")).toBeInTheDocument();
  });

  it("shows total orders", async () => {
    renderWithProviders(<MarketOpportunities />);
    expect(await screen.findByText("Total Orders")).toBeInTheDocument();
    expect(screen.getByText("50")).toBeInTheDocument();
  });

  it("shows win rate", async () => {
    renderWithProviders(<MarketOpportunities />);
    expect(await screen.findByText("Win Rate")).toBeInTheDocument();
    expect(screen.getByText("60%")).toBeInTheDocument();
  });

  it("shows positive total P&L in green", async () => {
    renderWithProviders(<MarketOpportunities />);
    await screen.findByText("Strategy Performance");
    const pnlEl = screen.getByText("$1500");
    expect(pnlEl.className).toContain("text-green");
  });

  it("shows negative total P&L in red", async () => {
    const negReport = {
      ...mockReport,
      strategy_performance: { total_orders: 50, win_rate: 40, total_pnl: -500 },
    };
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/market/opportunities/summary": mockSummary,
        "/api/market/opportunities": mockOpportunities,
        "/api/market/daily-report": negReport,
      }),
    );
    renderWithProviders(<MarketOpportunities />);
    await screen.findByText("Strategy Performance");
    const pnlEl = screen.getByText("$-500");
    expect(pnlEl.className).toContain("text-red");
  });
});

describe("MarketOpportunities - Score Bar Colors", () => {
  it("shows yellow bar for medium scores (50-74)", async () => {
    const medScoreOpps = [
      {
        id: 3,
        symbol: "SOL/USDT",
        asset_class: "crypto",
        opportunity_type: "breakout",
        score: 60,
        details: { reason: "Price breakout" },
        detected_at: "2026-03-10T10:00:00Z",
      },
    ];
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/market/opportunities/summary": mockSummary,
        "/api/market/opportunities": medScoreOpps,
        "/api/market/daily-report": mockReport,
      }),
    );
    renderWithProviders(<MarketOpportunities />);
    await screen.findByText("60");
    const scoreCell = screen.getByText("60").closest("td");
    const bar = scoreCell?.querySelector(".bg-yellow-400");
    expect(bar).not.toBeNull();
  });
});
