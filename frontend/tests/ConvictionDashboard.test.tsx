import { describe, it, expect, beforeEach, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ConvictionDashboard } from "../src/pages/ConvictionDashboard";
import { renderWithProviders, mockFetch } from "./helpers";

const mockBatchSignals = [
  {
    symbol: "BTC/USDT",
    asset_class: "crypto",
    timestamp: "2026-03-10T14:00:00Z",
    composite_score: 78.5,
    signal_label: "strong_buy",
    entry_approved: true,
    position_modifier: 1.2,
    hard_disabled: false,
    components: { technical: 80, regime: 75, ml: 85, sentiment: 65, scanner: 72, win_rate: 70 },
    confidences: { ml: 0.92, sentiment: 0.75, regime: 0.88 },
    sources_available: ["technical", "regime", "ml", "sentiment", "scanner"],
    reasoning: ["Strong uptrend", "ML bullish"],
  },
  {
    symbol: "ETH/USDT",
    asset_class: "crypto",
    timestamp: "2026-03-10T14:00:00Z",
    composite_score: 42.0,
    signal_label: "weak_sell",
    entry_approved: false,
    position_modifier: 0.8,
    hard_disabled: false,
    components: { technical: 40, regime: 35, ml: 50, sentiment: 45, scanner: 38, win_rate: 42 },
    confidences: { ml: 0.6, sentiment: 0.5, regime: 0.55 },
    sources_available: ["technical", "regime"],
    reasoning: ["Weak trend"],
  },
];

const mockStrategyStatus = [
  { strategy_name: "CryptoInvestorV1", asset_class: "crypto", regime: "strong_trend_up", alignment_score: 85, recommended_action: "active" },
  { strategy_name: "BollingerMeanReversion", asset_class: "crypto", regime: "strong_trend_up", alignment_score: 25, recommended_action: "reduce_size" },
  { strategy_name: "VolatilityBreakout", asset_class: "crypto", regime: "strong_trend_up", alignment_score: 8, recommended_action: "pause" },
];

const mockAccuracy = {
  total_trades: 156,
  wins: 98,
  overall_win_rate: 0.628,
  window_days: 30,
  asset_class: "crypto",
  strategy: null,
  sources: {
    ml: { win_avg: 78.5, loss_avg: 62.3, accuracy: 0.72, accuracy_difference: 16.2 },
    regime: { win_avg: 82.1, loss_avg: 58.9, accuracy: 0.82, accuracy_difference: 23.2 },
    sentiment: { win_avg: 68.2, loss_avg: 55.1, accuracy: 0.58, accuracy_difference: 13.1 },
  },
};

const mockWeights = {
  current_weights: { ml: 0.25, sentiment: 0.15, regime: 0.30, scanner: 0.20, screen: 0.10 },
  recommended_weights: { ml: 0.30, sentiment: 0.10, regime: 0.35, scanner: 0.15, screen: 0.10 },
  adjustments: { ml: 0.05, sentiment: -0.05, regime: 0.05, scanner: -0.05, screen: 0.0 },
  source_accuracy: { ml: 0.72, sentiment: 0.58, regime: 0.82, scanner: 0.65, screen: 0.64 },
  total_trades: 156,
  win_rate: 0.628,
  threshold_adjustment: 5,
  reasoning: ["Regime model highest accuracy", "Reduce sentiment weight"],
};

const mockDetail = {
  ...mockBatchSignals[0],
};

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    mockFetch({
      "/api/signals/batch": mockBatchSignals,
      "/api/signals/strategy-status": mockStrategyStatus,
      "/api/signals/accuracy": mockAccuracy,
      "/api/signals/weights": mockWeights,
      "/api/signals/BTC-USDT/": mockDetail,
    }),
  );
});

describe("ConvictionDashboard", () => {
  it("renders the page heading", () => {
    renderWithProviders(<ConvictionDashboard />);
    expect(screen.getByText("Conviction Dashboard")).toBeInTheDocument();
  });

  it("sets document title", () => {
    renderWithProviders(<ConvictionDashboard />);
    expect(document.title).toBe("Conviction | A1SI-AITP");
  });

  it("renders heatmap with signal scores", async () => {
    renderWithProviders(<ConvictionDashboard />);
    expect(await screen.findByText("BTC/USDT")).toBeInTheDocument();
    expect(screen.getByText("79")).toBeInTheDocument(); // 78.5 rounded
    expect(screen.getByText("ETH/USDT")).toBeInTheDocument();
    expect(screen.getByText("42")).toBeInTheDocument();
  });

  it("renders signal labels in heatmap", async () => {
    renderWithProviders(<ConvictionDashboard />);
    expect(await screen.findByText("strong buy")).toBeInTheDocument();
    expect(screen.getByText("weak sell")).toBeInTheDocument();
  });

  it("shows heatmap skeleton while loading", () => {
    vi.stubGlobal("fetch", mockFetch({}));
    renderWithProviders(<ConvictionDashboard />);
    expect(screen.getByTestId("heatmap-skeleton")).toBeInTheDocument();
  });

  it("clicking a symbol opens signal detail panel", async () => {
    const user = userEvent.setup();
    renderWithProviders(<ConvictionDashboard />);
    await screen.findByText("BTC/USDT");
    await user.click(screen.getByLabelText("View signal for BTC/USDT"));
    expect(await screen.findByText("Signal Detail: BTC/USDT")).toBeInTheDocument();
  });

  it("signal detail shows component breakdown", async () => {
    const user = userEvent.setup();
    renderWithProviders(<ConvictionDashboard />);
    await screen.findByText("BTC/USDT");
    await user.click(screen.getByLabelText("View signal for BTC/USDT"));
    expect(await screen.findByText("Signal Components")).toBeInTheDocument();
    expect(screen.getByText("Technical")).toBeInTheDocument();
    // "Regime" may appear in both component breakdown and strategy status
    expect(screen.getAllByText("Regime").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("Sentiment").length).toBeGreaterThanOrEqual(1);
  });

  it("signal detail shows entry approval status", async () => {
    const user = userEvent.setup();
    renderWithProviders(<ConvictionDashboard />);
    await screen.findByText("BTC/USDT");
    await user.click(screen.getByLabelText("View signal for BTC/USDT"));
    expect(await screen.findByText("Approved")).toBeInTheDocument();
  });

  it("signal detail shows position modifier", async () => {
    const user = userEvent.setup();
    renderWithProviders(<ConvictionDashboard />);
    await screen.findByText("BTC/USDT");
    await user.click(screen.getByLabelText("View signal for BTC/USDT"));
    expect(await screen.findByText("1.20x")).toBeInTheDocument();
  });

  it("signal detail shows reasoning", async () => {
    const user = userEvent.setup();
    renderWithProviders(<ConvictionDashboard />);
    await screen.findByText("BTC/USDT");
    await user.click(screen.getByLabelText("View signal for BTC/USDT"));
    expect(await screen.findByText("Strong uptrend")).toBeInTheDocument();
    expect(screen.getByText("ML bullish")).toBeInTheDocument();
  });

  it("close button hides detail panel", async () => {
    const user = userEvent.setup();
    renderWithProviders(<ConvictionDashboard />);
    await screen.findByText("BTC/USDT");
    await user.click(screen.getByLabelText("View signal for BTC/USDT"));
    expect(await screen.findByText("Signal Detail: BTC/USDT")).toBeInTheDocument();
    await user.click(screen.getByLabelText("Close signal detail"));
    expect(screen.queryByText("Signal Detail: BTC/USDT")).not.toBeInTheDocument();
  });

  it("renders strategy status section", async () => {
    renderWithProviders(<ConvictionDashboard />);
    expect(await screen.findByText("Strategy Status")).toBeInTheDocument();
    expect(await screen.findByText("CryptoInvestorV1")).toBeInTheDocument();
    expect(screen.getByText("BollingerMeanReversion")).toBeInTheDocument();
    expect(screen.getByText("VolatilityBreakout")).toBeInTheDocument();
  });

  it("displays strategy recommended actions", async () => {
    renderWithProviders(<ConvictionDashboard />);
    expect(await screen.findByText("active")).toBeInTheDocument();
    expect(screen.getByText("reduce size")).toBeInTheDocument();
    expect(screen.getByText("pause")).toBeInTheDocument();
  });

  it("displays strategy alignment scores", async () => {
    renderWithProviders(<ConvictionDashboard />);
    expect(await screen.findByText(/Alignment: 85/)).toBeInTheDocument();
    expect(screen.getByText(/Alignment: 25/)).toBeInTheDocument();
  });

  it("renders source accuracy section", async () => {
    renderWithProviders(<ConvictionDashboard />);
    expect(await screen.findByText("Signal Source Accuracy")).toBeInTheDocument();
    expect(await screen.findByText("156")).toBeInTheDocument(); // total trades
    expect(screen.getByText("62.8%")).toBeInTheDocument(); // win rate
    expect(screen.getByText("30d")).toBeInTheDocument(); // window
  });

  it("renders accuracy table with sources", async () => {
    renderWithProviders(<ConvictionDashboard />);
    // Wait for accuracy data to load
    expect(await screen.findByText("72%")).toBeInTheDocument(); // ML accuracy
    expect(screen.getByText("82%")).toBeInTheDocument(); // regime accuracy
    expect(screen.getByText("58%")).toBeInTheDocument(); // sentiment accuracy
  });

  it("renders weight recommendations section", async () => {
    renderWithProviders(<ConvictionDashboard />);
    expect(await screen.findByText("Weight Recommendations")).toBeInTheDocument();
    expect(screen.getByText("Regime model highest accuracy")).toBeInTheDocument();
    expect(screen.getByText("Reduce sentiment weight")).toBeInTheDocument();
  });

  it("displays current and recommended weights", async () => {
    renderWithProviders(<ConvictionDashboard />);
    // current ml weight 25%, recommended 30% — multiple values may match, check existence
    expect(await screen.findByText("25%")).toBeInTheDocument();
    const thirties = screen.getAllByText("30%");
    expect(thirties.length).toBeGreaterThanOrEqual(1);
  });

  it("shows weight adjustments with colors", async () => {
    renderWithProviders(<ConvictionDashboard />);
    // ml and regime both have +5%, sentiment and scanner both have -5%, screen has +0%
    const plusFives = await screen.findAllByText("+5%");
    expect(plusFives.length).toBeGreaterThanOrEqual(1);
    const minusFives = screen.getAllByText("-5%");
    expect(minusFives.length).toBeGreaterThanOrEqual(1);
  });

  it("shows empty message when batch returns empty", async () => {
    vi.stubGlobal("fetch", mockFetch({
      "/api/signals/batch": [],
      "/api/signals/strategy-status": mockStrategyStatus,
      "/api/signals/accuracy": mockAccuracy,
      "/api/signals/weights": mockWeights,
    }));
    renderWithProviders(<ConvictionDashboard />);
    expect(await screen.findByText(/No signal data available/)).toBeInTheDocument();
  });

  it("shows empty strategy message when no strategies", async () => {
    vi.stubGlobal("fetch", mockFetch({
      "/api/signals/batch": mockBatchSignals,
      "/api/signals/strategy-status": [],
      "/api/signals/accuracy": mockAccuracy,
      "/api/signals/weights": mockWeights,
    }));
    renderWithProviders(<ConvictionDashboard />);
    expect(await screen.findByText("No strategy data available.")).toBeInTheDocument();
  });

  it("shows empty accuracy message when no sources", async () => {
    vi.stubGlobal("fetch", mockFetch({
      "/api/signals/batch": mockBatchSignals,
      "/api/signals/strategy-status": mockStrategyStatus,
      "/api/signals/accuracy": { ...mockAccuracy, sources: {} },
      "/api/signals/weights": mockWeights,
    }));
    renderWithProviders(<ConvictionDashboard />);
    expect(await screen.findByText(/No accuracy data yet/)).toBeInTheDocument();
  });

  it("renders heatmap error when batch fails", async () => {
    vi.stubGlobal("fetch", async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input.toString();
      if (url.includes("/api/signals/batch")) {
        return new Response(JSON.stringify({ error: "fail" }), {
          status: 500,
          headers: { "Content-Type": "application/json" },
        });
      }
      // Other endpoints return sensible defaults
      if (url.includes("strategy-status")) return new Response(JSON.stringify([]), { status: 200, headers: { "Content-Type": "application/json" } });
      if (url.includes("accuracy")) return new Response(JSON.stringify({ total_trades: 0, wins: 0, overall_win_rate: 0, window_days: 30, asset_class: null, strategy: null, sources: {} }), { status: 200, headers: { "Content-Type": "application/json" } });
      if (url.includes("weights")) return new Response(JSON.stringify(mockWeights), { status: 200, headers: { "Content-Type": "application/json" } });
      return new Response(JSON.stringify([]), { status: 200, headers: { "Content-Type": "application/json" } });
    });
    renderWithProviders(<ConvictionDashboard />);
    // QueryError shows a Retry button
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /retry/i })).toBeInTheDocument();
    });
  });

  it("renders with equity asset class", async () => {
    vi.stubGlobal("fetch", mockFetch({
      "/api/signals/batch": [],
      "/api/signals/strategy-status": [],
      "/api/signals/accuracy": { total_trades: 0, wins: 0, overall_win_rate: 0, window_days: 30, asset_class: "equity", strategy: null, sources: {} },
      "/api/signals/weights": { ...mockWeights, total_trades: 0 },
    }));
    renderWithProviders(<ConvictionDashboard />, { assetClass: "equity" });
    expect(screen.getByText("Conviction Dashboard")).toBeInTheDocument();
  });

  it("signal detail shows hard disabled state", async () => {
    const disabledSignal = { ...mockDetail, hard_disabled: true, entry_approved: false };
    vi.stubGlobal("fetch", mockFetch({
      "/api/signals/batch": mockBatchSignals,
      "/api/signals/strategy-status": mockStrategyStatus,
      "/api/signals/accuracy": mockAccuracy,
      "/api/signals/weights": mockWeights,
      "/api/signals/BTC-USDT/": disabledSignal,
    }));
    const user = userEvent.setup();
    renderWithProviders(<ConvictionDashboard />);
    await screen.findByText("BTC/USDT");
    await user.click(screen.getByLabelText("View signal for BTC/USDT"));
    expect(await screen.findByText("Hard Disabled")).toBeInTheDocument();
    expect(screen.getByText("Blocked")).toBeInTheDocument();
  });
});
