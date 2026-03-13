import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { useSystemEvents } from "../src/hooks/useSystemEvents";
import { ToastProvider } from "../src/components/Toast";

// Track the most recent useWebSocket callback
let lastWebSocketResult = {
  isConnected: false,
  lastMessage: null as unknown,
  send: vi.fn(),
};

vi.mock("../src/hooks/useWebSocket", () => ({
  useWebSocket: () => lastWebSocketResult,
}));

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
    },
  });

  // Spy on invalidateQueries
  vi.spyOn(queryClient, "invalidateQueries");

  return {
    queryClient,
    Wrapper({ children }: { children: ReactNode }) {
      return (
        <QueryClientProvider client={queryClient}>
          <ToastProvider>
            {children}
          </ToastProvider>
        </QueryClientProvider>
      );
    },
  };
}

describe("useSystemEvents", () => {
  beforeEach(() => {
    lastWebSocketResult = {
      isConnected: false,
      lastMessage: null,
      send: vi.fn(),
    };
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("returns initial state", () => {
    const { Wrapper } = createWrapper();
    const { result } = renderHook(() => useSystemEvents(), {
      wrapper: Wrapper,
    });

    expect(result.current.isConnected).toBe(false);
    expect(result.current.isHalted).toBeNull();
    expect(result.current.haltReason).toBe("");
    expect(result.current.lastOrderUpdate).toBeNull();
    expect(result.current.lastRiskAlert).toBeNull();
  });

  it("reflects WebSocket connection status", () => {
    lastWebSocketResult.isConnected = true;

    const { Wrapper } = createWrapper();
    const { result } = renderHook(() => useSystemEvents(), {
      wrapper: Wrapper,
    });

    expect(result.current.isConnected).toBe(true);
  });

  it("processes halt_status event", () => {
    const { Wrapper, queryClient } = createWrapper();

    lastWebSocketResult.lastMessage = {
      type: "halt_status",
      data: { is_halted: true, halt_reason: "Drawdown exceeded" },
    };

    const { result } = renderHook(() => useSystemEvents(), {
      wrapper: Wrapper,
    });

    // useEffect will run and process the message
    expect(result.current.isHalted).toBe(true);
    expect(result.current.haltReason).toBe("Drawdown exceeded");
    expect(queryClient.invalidateQueries).toHaveBeenCalledWith({
      queryKey: ["risk-status"],
    });
  });

  it("processes halt_status with is_halted=false", () => {
    const { Wrapper } = createWrapper();

    lastWebSocketResult.lastMessage = {
      type: "halt_status",
      data: { is_halted: false, halt_reason: "" },
    };

    const { result } = renderHook(() => useSystemEvents(), {
      wrapper: Wrapper,
    });

    expect(result.current.isHalted).toBe(false);
    expect(result.current.haltReason).toBe("");
  });

  it("processes order_update event", () => {
    const { Wrapper, queryClient } = createWrapper();

    const orderData = {
      order_id: 42,
      status: "filled",
      symbol: "BTC/USDT",
    };

    lastWebSocketResult.lastMessage = {
      type: "order_update",
      data: orderData,
    };

    const { result } = renderHook(() => useSystemEvents(), {
      wrapper: Wrapper,
    });

    expect(result.current.lastOrderUpdate).toEqual(orderData);
    expect(queryClient.invalidateQueries).toHaveBeenCalledWith({
      queryKey: ["orders"],
    });
  });

  it("processes risk_alert event", () => {
    const { Wrapper, queryClient } = createWrapper();

    const alertData = {
      severity: "warning",
      message: "Position concentration high",
    };

    lastWebSocketResult.lastMessage = {
      type: "risk_alert",
      data: alertData,
    };

    const { result } = renderHook(() => useSystemEvents(), {
      wrapper: Wrapper,
    });

    expect(result.current.lastRiskAlert).toEqual(alertData);
    expect(queryClient.invalidateQueries).toHaveBeenCalledWith({
      queryKey: ["risk-alerts"],
    });
  });

  it("processes news_update event with articles", () => {
    const { Wrapper, queryClient } = createWrapper();

    lastWebSocketResult.lastMessage = {
      type: "news_update",
      data: { articles_fetched: 5, asset_class: "crypto" },
    };

    renderHook(() => useSystemEvents(), { wrapper: Wrapper });

    expect(queryClient.invalidateQueries).toHaveBeenCalledWith({
      queryKey: ["news-articles"],
    });
  });

  it("processes news_update event with zero articles (no toast)", () => {
    const { Wrapper, queryClient } = createWrapper();

    lastWebSocketResult.lastMessage = {
      type: "news_update",
      data: { articles_fetched: 0, asset_class: "crypto" },
    };

    renderHook(() => useSystemEvents(), { wrapper: Wrapper });

    expect(queryClient.invalidateQueries).toHaveBeenCalledWith({
      queryKey: ["news-articles"],
    });
  });

  it("processes sentiment_update event", () => {
    const { Wrapper, queryClient } = createWrapper();

    lastWebSocketResult.lastMessage = {
      type: "sentiment_update",
      data: {},
    };

    renderHook(() => useSystemEvents(), { wrapper: Wrapper });

    expect(queryClient.invalidateQueries).toHaveBeenCalledWith({
      queryKey: ["news-sentiment"],
    });
    expect(queryClient.invalidateQueries).toHaveBeenCalledWith({
      queryKey: ["sentiment-signal"],
    });
  });

  it("processes scheduler_event completed", () => {
    const { Wrapper, queryClient } = createWrapper();

    const schedulerData = { task_name: "data_refresh", status: "completed" };

    lastWebSocketResult.lastMessage = {
      type: "scheduler_event",
      data: schedulerData,
    };

    const { result } = renderHook(() => useSystemEvents(), { wrapper: Wrapper });

    expect(result.current.lastSchedulerEvent).toEqual(schedulerData);
    expect(queryClient.invalidateQueries).toHaveBeenCalledWith({
      queryKey: ["recent-jobs"],
    });
    expect(queryClient.invalidateQueries).toHaveBeenCalledWith({
      queryKey: ["scheduler-tasks"],
    });
  });

  it("processes scheduler_event failed", () => {
    const { Wrapper } = createWrapper();

    lastWebSocketResult.lastMessage = {
      type: "scheduler_event",
      data: { task_name: "ml_training", status: "failed" },
    };

    const { result } = renderHook(() => useSystemEvents(), { wrapper: Wrapper });

    expect(result.current.lastSchedulerEvent).toEqual({
      task_name: "ml_training",
      status: "failed",
    });
  });

  it("processes regime_change event", () => {
    const { Wrapper, queryClient } = createWrapper();

    const regimeData = {
      symbol: "BTC/USDT",
      previous_regime: "TRENDING_UP",
      new_regime: "HIGH_VOLATILITY",
    };

    lastWebSocketResult.lastMessage = {
      type: "regime_change",
      data: regimeData,
    };

    const { result } = renderHook(() => useSystemEvents(), { wrapper: Wrapper });

    expect(result.current.lastRegimeChange).toEqual(regimeData);
    expect(queryClient.invalidateQueries).toHaveBeenCalledWith({
      queryKey: ["regime-overview"],
    });
  });

  it("processes opportunity_alert event", () => {
    const { Wrapper, queryClient } = createWrapper();

    lastWebSocketResult.lastMessage = {
      type: "opportunity_alert",
      data: {
        symbol: "ETH/USDT",
        opportunity_type: "volume_surge",
        score: 85,
      },
    };

    renderHook(() => useSystemEvents(), { wrapper: Wrapper });

    expect(queryClient.invalidateQueries).toHaveBeenCalledWith({
      queryKey: ["opportunities"],
    });
    expect(queryClient.invalidateQueries).toHaveBeenCalledWith({
      queryKey: ["opportunity-summary"],
    });
  });

  it("updates state when message changes", () => {
    const { Wrapper } = createWrapper();

    lastWebSocketResult.lastMessage = {
      type: "halt_status",
      data: { is_halted: true, halt_reason: "Manual" },
    };

    const { result, rerender } = renderHook(() => useSystemEvents(), {
      wrapper: Wrapper,
    });

    expect(result.current.isHalted).toBe(true);

    // Simulate new message by re-rendering with updated mock
    act(() => {
      lastWebSocketResult.lastMessage = {
        type: "halt_status",
        data: { is_halted: false, halt_reason: "" },
      };
    });

    rerender();

    expect(result.current.isHalted).toBe(false);
  });
});
