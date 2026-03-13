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

  it("renders transition probabilities table when data is present", async () => {
    renderWithProviders(<RegimeDashboard />);
    expect(await screen.findByText("Transition Probabilities")).toBeInTheDocument();
    // "Strong Trend Up" appears in multiple places (status card, history, transitions)
    const strongTrendUps = screen.getAllByText("Strong Trend Up");
    expect(strongTrendUps.length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText("60.0%")).toBeInTheDocument();
  });

  it("shows no recommendation message when recommendation is absent", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/regime/current/BTC": mockRegimeState,
        "/api/regime/history/BTC": mockHistory,
      }),
    );
    renderWithProviders(<RegimeDashboard />);
    expect(await screen.findByText("No recommendation available")).toBeInTheDocument();
  });

  it("shows no history message when history is empty", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/regime/current/BTC": mockRegimeState,
        "/api/regime/recommendation/BTC": mockRecommendation,
        "/api/regime/history/BTC": [],
      }),
    );
    renderWithProviders(<RegimeDashboard />);
    expect(await screen.findByText("No history available")).toBeInTheDocument();
  });

  it("renders regime timeline when history has multiple entries", async () => {
    const longHistory = [
      { timestamp: "2026-02-15T08:00:00Z", regime: "ranging", confidence: 0.6, adx_value: 20.0, bb_width_percentile: 45 },
      { timestamp: "2026-02-15T09:00:00Z", regime: "weak_trend_up", confidence: 0.72, adx_value: 32.0, bb_width_percentile: 48 },
      { timestamp: "2026-02-15T10:00:00Z", regime: "strong_trend_up", confidence: 0.85, adx_value: 45.0, bb_width_percentile: 60 },
    ];
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/regime/current/BTC": mockRegimeState,
        "/api/regime/recommendation/BTC": mockRecommendation,
        "/api/regime/history/BTC": longHistory,
      }),
    );
    renderWithProviders(<RegimeDashboard />);
    expect(await screen.findByText("Regime Timeline")).toBeInTheDocument();
  });

  it("renders strategy weights table with details", async () => {
    renderWithProviders(<RegimeDashboard />);
    expect(await screen.findByText("Strategy Weights")).toBeInTheDocument();
    expect(screen.getByText("VolatilityBreakout")).toBeInTheDocument();
    expect(screen.getByText("70%")).toBeInTheDocument();
    expect(screen.getByText("30%")).toBeInTheDocument();
    expect(screen.getByText("0.8x")).toBeInTheDocument();
  });

  it("shows reasoning text from recommendation", async () => {
    renderWithProviders(<RegimeDashboard />);
    expect(await screen.findByText("Strong uptrend favors trend-following strategies")).toBeInTheDocument();
  });

  it("renders low confidence status card in red", async () => {
    const lowConfidenceState = {
      ...mockRegimeState,
      confidence: 0.3,
    };
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/regime/current/BTC": lowConfidenceState,
        "/api/regime/recommendation/BTC": mockRecommendation,
        "/api/regime/history/BTC": mockHistory,
      }),
    );
    renderWithProviders(<RegimeDashboard />);
    expect(await screen.findByText("30.0%")).toBeInTheDocument();
  });

  it("renders medium confidence status card in yellow", async () => {
    const medConfidenceState = {
      ...mockRegimeState,
      confidence: 0.55,
    };
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/regime/current/BTC": medConfidenceState,
        "/api/regime/recommendation/BTC": mockRecommendation,
        "/api/regime/history/BTC": mockHistory,
      }),
    );
    renderWithProviders(<RegimeDashboard />);
    expect(await screen.findByText("55.0%")).toBeInTheDocument();
  });

  it("renders low position modifier in red", async () => {
    const lowModRec = {
      ...mockRecommendation,
      position_size_modifier: 0.3,
    };
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/regime/current/BTC": mockRegimeState,
        "/api/regime/recommendation/BTC": lowModRec,
        "/api/regime/history/BTC": mockHistory,
      }),
    );
    renderWithProviders(<RegimeDashboard />);
    // Position Modifier card should show 30%
    expect(await screen.findByText("Strategy Recommendation")).toBeInTheDocument();
  });

  it("renders gauge with bipolar negative value", async () => {
    const negativeState = {
      ...mockRegimeState,
      ema_slope: -0.003,
      trend_alignment: -0.5,
      price_structure_score: -0.4,
    };
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/regime/current/BTC": negativeState,
        "/api/regime/recommendation/BTC": mockRecommendation,
        "/api/regime/history/BTC": mockHistory,
      }),
    );
    renderWithProviders(<RegimeDashboard />);
    expect(await screen.findByText("-0.00300")).toBeInTheDocument();
    expect(screen.getByText("-0.500")).toBeInTheDocument();
    expect(screen.getByText("-0.400")).toBeInTheDocument();
  });

  it("renders gauge with zero bipolar value", async () => {
    const zeroState = {
      ...mockRegimeState,
      ema_slope: 0,
    };
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/regime/current/BTC": zeroState,
        "/api/regime/recommendation/BTC": mockRecommendation,
        "/api/regime/history/BTC": mockHistory,
      }),
    );
    renderWithProviders(<RegimeDashboard />);
    expect(await screen.findByText("0.00000")).toBeInTheDocument();
  });

  it("renders unknown regime when regimeState is absent", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/regime/recommendation/BTC": mockRecommendation,
        "/api/regime/history/BTC": mockHistory,
      }),
    );
    renderWithProviders(<RegimeDashboard />);
    expect(await screen.findByText("Unknown")).toBeInTheDocument();
  });

  it("changes symbol via selector", async () => {
    const { fireEvent } = await import("@testing-library/react");
    renderWithProviders(<RegimeDashboard />);
    const select = screen.getByRole("combobox");
    fireEvent.change(select, { target: { value: "ETH/USDT" } });
    expect(select).toHaveValue("ETH/USDT");
  });

  it("handles history pagination", async () => {
    // Create > 15 history entries to trigger pagination
    const manyHistory = Array.from({ length: 20 }, (_, i) => ({
      timestamp: new Date(2026, 1, 15, 10, i).toISOString(),
      regime: i % 2 === 0 ? "strong_trend_up" : "ranging",
      confidence: 0.8,
      adx_value: 40.0,
      bb_width_percentile: 55,
    }));
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/regime/current/BTC": mockRegimeState,
        "/api/regime/recommendation/BTC": mockRecommendation,
        "/api/regime/history/BTC": manyHistory,
      }),
    );
    renderWithProviders(<RegimeDashboard />);
    expect(await screen.findByText("Regime History")).toBeInTheDocument();
  });
});
