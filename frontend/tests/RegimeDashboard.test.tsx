import { describe, it, expect, beforeEach, vi } from "vitest";
import { screen } from "@testing-library/react";
import { RegimeDashboard } from "../src/pages/RegimeDashboard";
import { renderWithProviders, mockFetch } from "./helpers";

const mockRegimeState = {
  symbol: "BTC/USDT",
  regime: "strong_trend_up",
  confidence: 0.85,
  adx_value: 45.0,
  bb_width_percentile: 60,
  ema_slope: 0.002,
  trend_alignment: 0.8,
  price_structure_score: 0.7,
  transition_probabilities: {
    strong_trend_up: 0.6,
    weak_trend_up: 0.2,
    ranging: 0.15,
    weak_trend_down: 0.05,
  },
};

const mockRecommendation = {
  symbol: "BTC/USDT",
  regime: "strong_trend_up",
  confidence: 0.85,
  primary_strategy: "CryptoInvestorV1",
  weights: [
    { strategy_name: "CryptoInvestorV1", weight: 0.7, position_size_factor: 1.0 },
    { strategy_name: "VolatilityBreakout", weight: 0.3, position_size_factor: 0.8 },
  ],
  position_size_modifier: 0.9,
  reasoning: "Strong uptrend favors trend-following strategies",
};

const mockHistory = [
  {
    timestamp: "2026-02-15T10:00:00Z",
    regime: "strong_trend_up",
    confidence: 0.85,
    adx_value: 45.0,
    bb_width_percentile: 60,
  },
  {
    timestamp: "2026-02-15T09:00:00Z",
    regime: "weak_trend_up",
    confidence: 0.72,
    adx_value: 32.0,
    bb_width_percentile: 48,
  },
];

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    mockFetch({
      "/api/regime/current/BTC": mockRegimeState,
      "/api/regime/recommendation/BTC": mockRecommendation,
      "/api/regime/history/BTC": mockHistory,
    }),
  );
});

describe("RegimeDashboard", () => {
  it("renders the page heading", () => {
    renderWithProviders(<RegimeDashboard />);
    expect(screen.getByText("Regime Dashboard")).toBeInTheDocument();
  });

  it("renders the symbol selector", () => {
    renderWithProviders(<RegimeDashboard />);
    const select = screen.getByRole("combobox");
    expect(select).toBeInTheDocument();
    expect(select).toHaveValue("BTC/USDT");
  });

  it("renders status cards", async () => {
    renderWithProviders(<RegimeDashboard />);
    expect(await screen.findByText("Current Regime")).toBeInTheDocument();
    expect(screen.getByText("Confidence")).toBeInTheDocument();
    expect(screen.getByText("Primary Strategy")).toBeInTheDocument();
    expect(screen.getByText("Position Modifier")).toBeInTheDocument();
  });

  it("renders sub-indicators section", async () => {
    renderWithProviders(<RegimeDashboard />);
    expect(await screen.findByText("Sub-Indicators")).toBeInTheDocument();
    expect(screen.getByText("ADX")).toBeInTheDocument();
    expect(screen.getByText("BB Width Pct")).toBeInTheDocument();
    expect(screen.getByText("EMA Slope")).toBeInTheDocument();
  });

  it("renders strategy recommendation", async () => {
    renderWithProviders(<RegimeDashboard />);
    expect(await screen.findByText("Strategy Recommendation")).toBeInTheDocument();
    const matches = await screen.findAllByText("CryptoInvestorV1");
    expect(matches.length).toBeGreaterThanOrEqual(1);
  });

  it("renders regime history table", async () => {
    renderWithProviders(<RegimeDashboard />);
    expect(await screen.findByText("Regime History")).toBeInTheDocument();
  });

  it("shows error state when API fails", async () => {
    const failingFetch = (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input.toString();
      if (url.includes("regime/current")) {
        return Promise.resolve(new Response(JSON.stringify({ error: "fail" }), { status: 500 }));
      }
      return mockFetch({
        "/api/regime/recommendation/BTC": mockRecommendation,
        "/api/regime/history/BTC": mockHistory,
      })(input, init);
    };
    vi.stubGlobal("fetch", failingFetch);
    renderWithProviders(<RegimeDashboard />);
    expect(await screen.findByText("Failed to load regime data")).toBeInTheDocument();
  });
});
