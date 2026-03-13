import { describe, it, expect, beforeEach, vi } from "vitest";
import { signalsApi } from "../src/api/signals";

let lastUrl: string;
let lastInit: RequestInit | undefined;

beforeEach(() => {
  lastUrl = "";
  lastInit = undefined;
  vi.stubGlobal("fetch", async (input: RequestInfo | URL, init?: RequestInit) => {
    lastUrl = typeof input === "string" ? input : input.toString();
    lastInit = init;
    return new Response(JSON.stringify({}), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  });
});

describe("signalsApi", () => {
  it("getSignal builds correct URL with symbol encoding", async () => {
    await signalsApi.getSignal("BTC/USDT");
    expect(lastUrl).toBe("/api/signals/BTC-USDT/");
  });

  it("getSignal includes asset_class and strategy params", async () => {
    await signalsApi.getSignal("ETH/USDT", "crypto", "CryptoInvestorV1");
    expect(lastUrl).toContain("asset_class=crypto");
    expect(lastUrl).toContain("strategy=CryptoInvestorV1");
  });

  it("batchSignals sends POST with symbols", async () => {
    await signalsApi.batchSignals(["BTC/USDT", "ETH/USDT"], "crypto");
    expect(lastUrl).toBe("/api/signals/batch/");
    expect(lastInit?.method).toBe("POST");
    const body = JSON.parse(lastInit?.body as string);
    expect(body.symbols).toEqual(["BTC/USDT", "ETH/USDT"]);
    expect(body.asset_class).toBe("crypto");
  });

  it("entryCheck sends POST with strategy", async () => {
    await signalsApi.entryCheck("BTC/USDT", "CryptoInvestorV1", "crypto");
    expect(lastUrl).toBe("/api/signals/BTC-USDT/entry-check/");
    expect(lastInit?.method).toBe("POST");
    const body = JSON.parse(lastInit?.body as string);
    expect(body.strategy).toBe("CryptoInvestorV1");
    expect(body.asset_class).toBe("crypto");
  });

  it("strategyStatus includes asset_class param", async () => {
    await signalsApi.strategyStatus("equity");
    expect(lastUrl).toBe("/api/signals/strategy-status/?asset_class=equity");
  });

  it("strategyStatus without params has no query string", async () => {
    await signalsApi.strategyStatus();
    expect(lastUrl).toBe("/api/signals/strategy-status/");
  });

  it("attributionList includes filters", async () => {
    await signalsApi.attributionList({ asset_class: "crypto", outcome: "win", limit: 10 });
    expect(lastUrl).toContain("asset_class=crypto");
    expect(lastUrl).toContain("outcome=win");
    expect(lastUrl).toContain("limit=10");
  });

  it("attributionDetail builds correct URL", async () => {
    await signalsApi.attributionDetail("ORD-123");
    expect(lastUrl).toBe("/api/signals/attribution/ORD-123/");
  });

  it("accuracy includes window_days param", async () => {
    await signalsApi.accuracy({ window_days: 60 });
    expect(lastUrl).toContain("window_days=60");
  });

  it("weights includes all params", async () => {
    await signalsApi.weights({ asset_class: "forex", strategy: "ForexTrend", window_days: 90 });
    expect(lastUrl).toContain("asset_class=forex");
    expect(lastUrl).toContain("strategy=ForexTrend");
    expect(lastUrl).toContain("window_days=90");
  });

  it("mlPredictions encodes symbol and includes limit", async () => {
    await signalsApi.mlPredictions("BTC/USDT", 20);
    expect(lastUrl).toBe("/api/ml/predictions/BTC-USDT/?limit=20");
  });

  it("mlModelPerformance builds correct URL", async () => {
    await signalsApi.mlModelPerformance("model_123");
    expect(lastUrl).toBe("/api/ml/models/model_123/performance/");
  });

  it("batchSignals defaults to crypto and CryptoInvestorV1", async () => {
    await signalsApi.batchSignals(["SOL/USDT"]);
    const body = JSON.parse(lastInit?.body as string);
    expect(body.asset_class).toBe("crypto");
    expect(body.strategy_name).toBe("CryptoInvestorV1");
  });

  it("entryCheck defaults to crypto", async () => {
    await signalsApi.entryCheck("ETH/USDT", "BMR");
    const body = JSON.parse(lastInit?.body as string);
    expect(body.asset_class).toBe("crypto");
  });

  it("accuracy with no params has no query string", async () => {
    await signalsApi.accuracy();
    expect(lastUrl).toBe("/api/signals/accuracy/");
  });

  it("weights with no params has no query string", async () => {
    await signalsApi.weights();
    expect(lastUrl).toBe("/api/signals/weights/");
  });

  it("attributionList with no params has no query string", async () => {
    await signalsApi.attributionList();
    expect(lastUrl).toBe("/api/signals/attribution/");
  });

  it("mlPredictions without limit has no query string", async () => {
    await signalsApi.mlPredictions("SOL/USDT");
    expect(lastUrl).toBe("/api/ml/predictions/SOL-USDT/");
  });
});
