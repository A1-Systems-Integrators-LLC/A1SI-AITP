import { describe, it, expect, vi, beforeEach } from "vitest";

// Mock the client module before importing API modules
vi.mock("../src/api/client", () => ({
  api: {
    get: vi.fn().mockResolvedValue({}),
    post: vi.fn().mockResolvedValue({}),
    put: vi.fn().mockResolvedValue({}),
    patch: vi.fn().mockResolvedValue({}),
    delete: vi.fn().mockResolvedValue(undefined),
  },
}));

import { api } from "../src/api/client";
import { portfoliosApi } from "../src/api/portfolios";
import { tradingApi } from "../src/api/trading";
import { riskApi } from "../src/api/risk";
import { marketApi } from "../src/api/market";
import { regimeApi } from "../src/api/regime";
import { backtestApi } from "../src/api/backtest";
import { screeningApi } from "../src/api/screening";
import { dataApi } from "../src/api/data";
import { mlApi } from "../src/api/ml";
import { paperTradingApi } from "../src/api/paperTrading";
import { exchangeConfigsApi, dataSourcesApi } from "../src/api/exchangeConfigs";
import { notificationsApi } from "../src/api/notifications";
import { exchangesApi } from "../src/api/exchanges";
import { indicatorsApi } from "../src/api/indicators";
import { platformApi } from "../src/api/platform";
import { jobsApi } from "../src/api/jobs";
import { auditApi } from "../src/api/audit";
import { newsApi } from "../src/api/news";
import { dashboardApi } from "../src/api/dashboard";
import { workflowsApi } from "../src/api/workflows";
import { schedulerApi } from "../src/api/scheduler";

const mockApi = api as {
  get: ReturnType<typeof vi.fn>;
  post: ReturnType<typeof vi.fn>;
  put: ReturnType<typeof vi.fn>;
  patch: ReturnType<typeof vi.fn>;
  delete: ReturnType<typeof vi.fn>;
};

beforeEach(() => {
  vi.clearAllMocks();
});

describe("portfoliosApi", () => {
  it("list calls GET /portfolios/", async () => {
    await portfoliosApi.list();
    expect(mockApi.get).toHaveBeenCalledWith("/portfolios/");
  });

  it("get calls GET /portfolios/:id/", async () => {
    await portfoliosApi.get(5);
    expect(mockApi.get).toHaveBeenCalledWith("/portfolios/5/");
  });

  it("create calls POST /portfolios/", async () => {
    await portfoliosApi.create({ name: "Test" });
    expect(mockApi.post).toHaveBeenCalledWith("/portfolios/", { name: "Test" });
  });

  it("update calls PUT /portfolios/:id/", async () => {
    await portfoliosApi.update(1, { name: "Updated" });
    expect(mockApi.put).toHaveBeenCalledWith("/portfolios/1/", {
      name: "Updated",
    });
  });

  it("patch calls PATCH /portfolios/:id/", async () => {
    await portfoliosApi.patch(1, { name: "Patched" });
    expect(mockApi.patch).toHaveBeenCalledWith("/portfolios/1/", {
      name: "Patched",
    });
  });

  it("delete calls DELETE /portfolios/:id/", async () => {
    await portfoliosApi.delete(1);
    expect(mockApi.delete).toHaveBeenCalledWith("/portfolios/1/");
  });

  it("addHolding calls POST with portfolio and holding data", async () => {
    await portfoliosApi.addHolding(1, {
      symbol: "BTC/USDT",
      amount: 0.5,
      avg_buy_price: 50000,
    });
    expect(mockApi.post).toHaveBeenCalledWith("/portfolios/1/holdings/", {
      symbol: "BTC/USDT",
      amount: 0.5,
      avg_buy_price: 50000,
    });
  });

  it("updateHolding calls PUT with correct path", async () => {
    await portfoliosApi.updateHolding(1, 3, { amount: 1.0 });
    expect(mockApi.put).toHaveBeenCalledWith("/portfolios/1/holdings/3/", {
      amount: 1.0,
    });
  });

  it("deleteHolding calls DELETE with correct path", async () => {
    await portfoliosApi.deleteHolding(1, 3);
    expect(mockApi.delete).toHaveBeenCalledWith("/portfolios/1/holdings/3/");
  });
});

describe("tradingApi", () => {
  it("listOrders builds query string with defaults", async () => {
    await tradingApi.listOrders();
    expect(mockApi.get).toHaveBeenCalledWith("/trading/orders/?limit=50");
  });

  it("listOrders includes mode filter", async () => {
    await tradingApi.listOrders(10, "paper");
    expect(mockApi.get).toHaveBeenCalledWith(
      "/trading/orders/?limit=10&mode=paper",
    );
  });

  it("getOrder calls GET with id", async () => {
    await tradingApi.getOrder(42);
    expect(mockApi.get).toHaveBeenCalledWith("/trading/orders/42/");
  });

  it("createOrder sends POST with order data", async () => {
    const order = {
      symbol: "BTC/USDT",
      side: "buy" as const,
      order_type: "market" as const,
      amount: 0.1,
      mode: "paper" as const,
    };
    await tradingApi.createOrder(order);
    expect(mockApi.post).toHaveBeenCalledWith("/trading/orders/", order);
  });

  it("cancelOrder sends POST to cancel endpoint", async () => {
    await tradingApi.cancelOrder(7);
    expect(mockApi.post).toHaveBeenCalledWith("/trading/orders/7/cancel/");
  });

  it("liveStatus calls GET", async () => {
    await tradingApi.liveStatus();
    expect(mockApi.get).toHaveBeenCalledWith("/live-trading/status/");
  });
});

describe("riskApi", () => {
  it("getStatus calls correct path", async () => {
    await riskApi.getStatus(1);
    expect(mockApi.get).toHaveBeenCalledWith("/risk/1/status/");
  });

  it("getLimits calls correct path", async () => {
    await riskApi.getLimits(1);
    expect(mockApi.get).toHaveBeenCalledWith("/risk/1/limits/");
  });

  it("updateLimits sends PUT with limits", async () => {
    await riskApi.updateLimits(1, { max_daily_loss: 0.03 });
    expect(mockApi.put).toHaveBeenCalledWith("/risk/1/limits/", {
      max_daily_loss: 0.03,
    });
  });

  it("updateEquity sends POST", async () => {
    await riskApi.updateEquity(1, 50000);
    expect(mockApi.post).toHaveBeenCalledWith("/risk/1/equity/", {
      equity: 50000,
    });
  });

  it("checkTrade sends POST with trade params", async () => {
    const params = {
      symbol: "BTC/USDT",
      side: "buy",
      size: 0.1,
      entry_price: 50000,
    };
    await riskApi.checkTrade(1, params);
    expect(mockApi.post).toHaveBeenCalledWith("/risk/1/check-trade/", params);
  });

  it("positionSize sends POST", async () => {
    await riskApi.positionSize(1, {
      entry_price: 50000,
      stop_loss_price: 48000,
    });
    expect(mockApi.post).toHaveBeenCalledWith("/risk/1/position-size/", {
      entry_price: 50000,
      stop_loss_price: 48000,
    });
  });

  it("getVaR uses default method", async () => {
    await riskApi.getVaR(1);
    expect(mockApi.get).toHaveBeenCalledWith("/risk/1/var/?method=parametric");
  });

  it("getVaR accepts custom method", async () => {
    await riskApi.getVaR(1, "historical");
    expect(mockApi.get).toHaveBeenCalledWith("/risk/1/var/?method=historical");
  });

  it("getHeatCheck calls correct path", async () => {
    await riskApi.getHeatCheck(1);
    expect(mockApi.get).toHaveBeenCalledWith("/risk/1/heat-check/");
  });

  it("haltTrading sends reason", async () => {
    await riskApi.haltTrading(1, "Manual halt");
    expect(mockApi.post).toHaveBeenCalledWith("/risk/1/halt/", {
      reason: "Manual halt",
    });
  });

  it("resumeTrading sends POST", async () => {
    await riskApi.resumeTrading(1);
    expect(mockApi.post).toHaveBeenCalledWith("/risk/1/resume/");
  });

  it("getAlerts uses default limit", async () => {
    await riskApi.getAlerts(1);
    expect(mockApi.get).toHaveBeenCalledWith("/risk/1/alerts/?limit=50");
  });

  it("getMetricHistory uses default hours", async () => {
    await riskApi.getMetricHistory(1);
    expect(mockApi.get).toHaveBeenCalledWith(
      "/risk/1/metric-history/?hours=168",
    );
  });

  it("resetDaily sends POST", async () => {
    await riskApi.resetDaily(1);
    expect(mockApi.post).toHaveBeenCalledWith("/risk/1/reset-daily/");
  });

  it("getTradeLog uses default limit", async () => {
    await riskApi.getTradeLog(1);
    expect(mockApi.get).toHaveBeenCalledWith("/risk/1/trade-log/?limit=50");
  });

  it("recordMetrics uses default method", async () => {
    await riskApi.recordMetrics(1);
    expect(mockApi.post).toHaveBeenCalledWith(
      "/risk/1/record-metrics/?method=parametric",
    );
  });
});

describe("marketApi", () => {
  it("ticker calls correct path", async () => {
    await marketApi.ticker("BTC/USDT");
    expect(mockApi.get).toHaveBeenCalledWith("/market/ticker/BTC/USDT/");
  });

  it("tickers calls without params", async () => {
    await marketApi.tickers();
    expect(mockApi.get).toHaveBeenCalledWith("/market/tickers/");
  });

  it("tickers passes symbol filter", async () => {
    await marketApi.tickers(["BTC/USDT", "ETH/USDT"]);
    expect(mockApi.get).toHaveBeenCalledWith(
      "/market/tickers/?symbols=BTC/USDT,ETH/USDT",
    );
  });

  it("ohlcv uses defaults", async () => {
    await marketApi.ohlcv("BTC/USDT");
    expect(mockApi.get).toHaveBeenCalledWith(
      "/market/ohlcv/BTC/USDT/?timeframe=1h&limit=100",
    );
  });

  it("ohlcv accepts custom params", async () => {
    await marketApi.ohlcv("ETH/USDT", "4h", 200);
    expect(mockApi.get).toHaveBeenCalledWith(
      "/market/ohlcv/ETH/USDT/?timeframe=4h&limit=200",
    );
  });
});

describe("regimeApi", () => {
  it("getCurrentAll calls correct path", async () => {
    await regimeApi.getCurrentAll();
    expect(mockApi.get).toHaveBeenCalledWith("/regime/current/");
  });

  it("getCurrent calls with symbol", async () => {
    await regimeApi.getCurrent("BTC/USDT");
    expect(mockApi.get).toHaveBeenCalledWith("/regime/current/BTC/USDT/");
  });

  it("getHistory includes limit", async () => {
    await regimeApi.getHistory("BTC/USDT", 50);
    expect(mockApi.get).toHaveBeenCalledWith(
      "/regime/history/BTC/USDT/?limit=50",
    );
  });

  it("getRecommendation calls correct path", async () => {
    await regimeApi.getRecommendation("BTC/USDT");
    expect(mockApi.get).toHaveBeenCalledWith(
      "/regime/recommendation/BTC/USDT/",
    );
  });

  it("getAllRecommendations calls correct path", async () => {
    await regimeApi.getAllRecommendations();
    expect(mockApi.get).toHaveBeenCalledWith("/regime/recommendations/");
  });

  it("getPositionSize sends POST", async () => {
    const params = {
      symbol: "BTC/USDT",
      entry_price: 50000,
      stop_loss_price: 48000,
    };
    await regimeApi.getPositionSize(params);
    expect(mockApi.post).toHaveBeenCalledWith("/regime/position-size/", params);
  });
});

describe("backtestApi", () => {
  it("run sends POST with params", async () => {
    const params = {
      framework: "freqtrade",
      strategy: "CryptoInvestorV1",
      symbol: "BTC/USDT",
      timeframe: "1h",
    };
    await backtestApi.run(params);
    expect(mockApi.post).toHaveBeenCalledWith("/backtest/run/", params);
  });

  it("results calls GET without limit", async () => {
    await backtestApi.results();
    expect(mockApi.get).toHaveBeenCalledWith("/backtest/results/");
  });

  it("results calls GET with limit", async () => {
    await backtestApi.results(10);
    expect(mockApi.get).toHaveBeenCalledWith("/backtest/results/?limit=10");
  });

  it("result calls GET with id", async () => {
    await backtestApi.result(5);
    expect(mockApi.get).toHaveBeenCalledWith("/backtest/results/5/");
  });

  it("strategies calls GET", async () => {
    await backtestApi.strategies();
    expect(mockApi.get).toHaveBeenCalledWith("/backtest/strategies/");
  });

  it("compare sends ids as query param", async () => {
    await backtestApi.compare([1, 2, 3]);
    expect(mockApi.get).toHaveBeenCalledWith("/backtest/compare/?ids=1,2,3");
  });
});

describe("screeningApi", () => {
  it("run sends POST with params", async () => {
    const params = {
      symbol: "BTC/USDT",
      timeframe: "1h",
      exchange: "binance",
      fees: 0.001,
    };
    await screeningApi.run(params);
    expect(mockApi.post).toHaveBeenCalledWith("/screening/run/", params);
  });

  it("results calls GET", async () => {
    await screeningApi.results();
    expect(mockApi.get).toHaveBeenCalledWith("/screening/results/");
  });

  it("strategies calls GET", async () => {
    await screeningApi.strategies();
    expect(mockApi.get).toHaveBeenCalledWith("/screening/strategies/");
  });
});

describe("dataApi", () => {
  it("list calls GET /data/", async () => {
    await dataApi.list();
    expect(mockApi.get).toHaveBeenCalledWith("/data/");
  });

  it("getInfo replaces / in symbol", async () => {
    await dataApi.getInfo("binance", "BTC/USDT", "1h");
    expect(mockApi.get).toHaveBeenCalledWith("/data/binance/BTC_USDT/1h/");
  });

  it("download sends POST", async () => {
    const params = {
      symbols: ["BTC/USDT"],
      timeframes: ["1h"],
      exchange: "binance",
      since_days: 30,
    };
    await dataApi.download(params);
    expect(mockApi.post).toHaveBeenCalledWith("/data/download/", params);
  });

  it("generateSample sends POST", async () => {
    const params = {
      symbols: ["BTC/USDT"],
      timeframes: ["1h"],
      days: 365,
    };
    await dataApi.generateSample(params);
    expect(mockApi.post).toHaveBeenCalledWith("/data/generate-sample/", params);
  });
});

describe("mlApi", () => {
  it("train sends POST", async () => {
    await mlApi.train({ symbol: "BTC/USDT" });
    expect(mockApi.post).toHaveBeenCalledWith("/ml/train/", {
      symbol: "BTC/USDT",
    });
  });

  it("listModels calls GET", async () => {
    await mlApi.listModels();
    expect(mockApi.get).toHaveBeenCalledWith("/ml/models/");
  });

  it("getModel calls GET with id", async () => {
    await mlApi.getModel("model-123");
    expect(mockApi.get).toHaveBeenCalledWith("/ml/models/model-123/");
  });

  it("predict sends POST", async () => {
    await mlApi.predict({ model_id: "model-123", bars: 50 });
    expect(mockApi.post).toHaveBeenCalledWith("/ml/predict/", {
      model_id: "model-123",
      bars: 50,
    });
  });
});

describe("paperTradingApi", () => {
  it("status calls GET", async () => {
    await paperTradingApi.status();
    expect(mockApi.get).toHaveBeenCalledWith("/paper-trading/status/");
  });

  it("start sends POST with strategy", async () => {
    await paperTradingApi.start("CryptoInvestorV1");
    expect(mockApi.post).toHaveBeenCalledWith("/paper-trading/start/", {
      strategy: "CryptoInvestorV1",
    });
  });

  it("stop sends POST", async () => {
    await paperTradingApi.stop();
    expect(mockApi.post).toHaveBeenCalledWith("/paper-trading/stop/");
  });

  it("openTrades calls GET", async () => {
    await paperTradingApi.openTrades();
    expect(mockApi.get).toHaveBeenCalledWith("/paper-trading/trades/");
  });

  it("history uses default limit", async () => {
    await paperTradingApi.history();
    expect(mockApi.get).toHaveBeenCalledWith(
      "/paper-trading/history/?limit=50",
    );
  });

  it("profit calls GET", async () => {
    await paperTradingApi.profit();
    expect(mockApi.get).toHaveBeenCalledWith("/paper-trading/profit/");
  });

  it("performance calls GET", async () => {
    await paperTradingApi.performance();
    expect(mockApi.get).toHaveBeenCalledWith("/paper-trading/performance/");
  });

  it("balance calls GET", async () => {
    await paperTradingApi.balance();
    expect(mockApi.get).toHaveBeenCalledWith("/paper-trading/balance/");
  });

  it("log uses default limit", async () => {
    await paperTradingApi.log();
    expect(mockApi.get).toHaveBeenCalledWith("/paper-trading/log/?limit=100");
  });
});

describe("exchangeConfigsApi", () => {
  it("list calls GET", async () => {
    await exchangeConfigsApi.list();
    expect(mockApi.get).toHaveBeenCalledWith("/exchange-configs/");
  });

  it("get calls GET with id", async () => {
    await exchangeConfigsApi.get(1);
    expect(mockApi.get).toHaveBeenCalledWith("/exchange-configs/1/");
  });

  it("create sends POST", async () => {
    const data = {
      name: "Binance",
      exchange_id: "binance",
      is_sandbox: true,
      is_default: false,
    };
    await exchangeConfigsApi.create(data);
    expect(mockApi.post).toHaveBeenCalledWith("/exchange-configs/", data);
  });

  it("update sends PUT", async () => {
    await exchangeConfigsApi.update(1, { name: "Updated" });
    expect(mockApi.put).toHaveBeenCalledWith("/exchange-configs/1/", {
      name: "Updated",
    });
  });

  it("delete sends DELETE", async () => {
    await exchangeConfigsApi.delete(1);
    expect(mockApi.delete).toHaveBeenCalledWith("/exchange-configs/1/");
  });

  it("test sends POST", async () => {
    await exchangeConfigsApi.test(1);
    expect(mockApi.post).toHaveBeenCalledWith("/exchange-configs/1/test/");
  });
});

describe("dataSourcesApi", () => {
  it("list calls GET", async () => {
    await dataSourcesApi.list();
    expect(mockApi.get).toHaveBeenCalledWith("/data-sources/");
  });

  it("create sends POST", async () => {
    const data = {
      exchange_config: 1,
      symbols: ["BTC/USDT"],
      timeframes: ["1h"],
    };
    await dataSourcesApi.create(data);
    expect(mockApi.post).toHaveBeenCalledWith("/data-sources/", data);
  });

  it("delete sends DELETE", async () => {
    await dataSourcesApi.delete(1);
    expect(mockApi.delete).toHaveBeenCalledWith("/data-sources/1/");
  });
});

describe("notificationsApi", () => {
  it("getPreferences calls GET with portfolio id", async () => {
    await notificationsApi.getPreferences(1);
    expect(mockApi.get).toHaveBeenCalledWith(
      "/notifications/1/preferences/",
    );
  });

  it("updatePreferences sends PUT", async () => {
    await notificationsApi.updatePreferences(1, { telegram_enabled: true });
    expect(mockApi.put).toHaveBeenCalledWith("/notifications/1/preferences/", {
      telegram_enabled: true,
    });
  });
});

describe("exchangesApi", () => {
  it("list calls GET /exchanges/", async () => {
    await exchangesApi.list();
    expect(mockApi.get).toHaveBeenCalledWith("/exchanges/");
  });
});

describe("indicatorsApi", () => {
  it("list calls GET /indicators/", async () => {
    await indicatorsApi.list();
    expect(mockApi.get).toHaveBeenCalledWith("/indicators/");
  });

  it("get replaces / in symbol and builds query string", async () => {
    await indicatorsApi.get("binance", "BTC/USDT", "1h", ["rsi", "macd"], 50);
    expect(mockApi.get).toHaveBeenCalledWith(
      "/indicators/binance/BTC_USDT/1h/?indicators=rsi%2Cmacd&limit=50",
    );
  });

  it("get works without optional params", async () => {
    await indicatorsApi.get("binance", "ETH/USDT", "4h");
    expect(mockApi.get).toHaveBeenCalledWith(
      "/indicators/binance/ETH_USDT/4h/",
    );
  });
});

describe("platformApi", () => {
  it("status calls GET", async () => {
    await platformApi.status();
    expect(mockApi.get).toHaveBeenCalledWith("/platform/status/");
  });

  it("config calls GET", async () => {
    await platformApi.config();
    expect(mockApi.get).toHaveBeenCalledWith("/platform/config/");
  });
});

describe("jobsApi", () => {
  it("list calls GET without params", async () => {
    await jobsApi.list();
    expect(mockApi.get).toHaveBeenCalledWith("/jobs/");
  });

  it("list includes type filter", async () => {
    await jobsApi.list("backtest");
    expect(mockApi.get).toHaveBeenCalledWith("/jobs/?job_type=backtest");
  });

  it("list includes type and limit", async () => {
    await jobsApi.list("screening", 10);
    expect(mockApi.get).toHaveBeenCalledWith(
      "/jobs/?job_type=screening&limit=10",
    );
  });

  it("get calls GET with id", async () => {
    await jobsApi.get("abc-123");
    expect(mockApi.get).toHaveBeenCalledWith("/jobs/abc-123/");
  });

  it("cancel sends POST", async () => {
    await jobsApi.cancel("abc-123");
    expect(mockApi.post).toHaveBeenCalledWith("/jobs/abc-123/cancel/");
  });
});

// ── P7-4: New API module tests ─────────────────────────────

describe("auditApi", () => {
  it("list calls GET /audit-log/ without params", async () => {
    await auditApi.list();
    expect(mockApi.get).toHaveBeenCalledWith("/audit-log/");
  });

  it("list includes filter params", async () => {
    await auditApi.list({ user: "admin", limit: 10 });
    expect(mockApi.get).toHaveBeenCalledWith(
      "/audit-log/?user=admin&limit=10",
    );
  });
});

describe("newsApi", () => {
  it("list calls GET /market/news/ without params", async () => {
    await newsApi.list();
    expect(mockApi.get).toHaveBeenCalledWith("/market/news/");
  });

  it("list includes asset_class and limit", async () => {
    await newsApi.list("crypto", undefined, 10);
    expect(mockApi.get).toHaveBeenCalledWith(
      "/market/news/?asset_class=crypto&limit=10",
    );
  });

  it("sentiment calls GET /market/news/sentiment/", async () => {
    await newsApi.sentiment("equity", 48);
    expect(mockApi.get).toHaveBeenCalledWith(
      "/market/news/sentiment/?asset_class=equity&hours=48",
    );
  });

  it("signal calls GET /market/news/signal/", async () => {
    await newsApi.signal("forex");
    expect(mockApi.get).toHaveBeenCalledWith(
      "/market/news/signal/?asset_class=forex",
    );
  });

  it("fetch calls POST /market/news/fetch/", async () => {
    await newsApi.fetch("crypto");
    expect(mockApi.post).toHaveBeenCalledWith("/market/news/fetch/", {
      asset_class: "crypto",
    });
  });
});

describe("dashboardApi", () => {
  it("kpis calls GET /dashboard/kpis/ without params", async () => {
    await dashboardApi.kpis();
    expect(mockApi.get).toHaveBeenCalledWith("/dashboard/kpis/");
  });

  it("kpis includes asset_class param", async () => {
    await dashboardApi.kpis("equity");
    expect(mockApi.get).toHaveBeenCalledWith(
      "/dashboard/kpis/?asset_class=equity",
    );
  });
});

describe("workflowsApi", () => {
  it("list calls GET /workflows/", async () => {
    await workflowsApi.list();
    expect(mockApi.get).toHaveBeenCalledWith("/workflows/");
  });

  it("list includes asset_class", async () => {
    await workflowsApi.list("crypto");
    expect(mockApi.get).toHaveBeenCalledWith(
      "/workflows/?asset_class=crypto",
    );
  });

  it("get calls GET /workflows/:id/", async () => {
    await workflowsApi.get("wf-1");
    expect(mockApi.get).toHaveBeenCalledWith("/workflows/wf-1/");
  });

  it("create calls POST /workflows/", async () => {
    await workflowsApi.create({ name: "test" });
    expect(mockApi.post).toHaveBeenCalledWith("/workflows/", { name: "test" });
  });

  it("trigger calls POST /workflows/:id/trigger/", async () => {
    await workflowsApi.trigger("wf-1");
    expect(mockApi.post).toHaveBeenCalledWith(
      "/workflows/wf-1/trigger/",
      undefined,
    );
  });

  it("enable calls POST /workflows/:id/enable/", async () => {
    await workflowsApi.enable("wf-1");
    expect(mockApi.post).toHaveBeenCalledWith("/workflows/wf-1/enable/");
  });

  it("disable calls POST /workflows/:id/disable/", async () => {
    await workflowsApi.disable("wf-1");
    expect(mockApi.post).toHaveBeenCalledWith("/workflows/wf-1/disable/");
  });

  it("runs calls GET /workflows/:id/runs/", async () => {
    await workflowsApi.runs("wf-1");
    expect(mockApi.get).toHaveBeenCalledWith("/workflows/wf-1/runs/");
  });

  it("stepTypes calls GET /workflow-steps/", async () => {
    await workflowsApi.stepTypes();
    expect(mockApi.get).toHaveBeenCalledWith("/workflow-steps/");
  });
});

describe("schedulerApi", () => {
  it("status calls GET /scheduler/status/", async () => {
    await schedulerApi.status();
    expect(mockApi.get).toHaveBeenCalledWith("/scheduler/status/");
  });

  it("tasks calls GET /scheduler/tasks/", async () => {
    await schedulerApi.tasks();
    expect(mockApi.get).toHaveBeenCalledWith("/scheduler/tasks/");
  });

  it("pause calls POST /scheduler/tasks/:id/pause/", async () => {
    await schedulerApi.pause("task-1");
    expect(mockApi.post).toHaveBeenCalledWith(
      "/scheduler/tasks/task-1/pause/",
    );
  });

  it("resume calls POST /scheduler/tasks/:id/resume/", async () => {
    await schedulerApi.resume("task-1");
    expect(mockApi.post).toHaveBeenCalledWith(
      "/scheduler/tasks/task-1/resume/",
    );
  });

  it("trigger calls POST /scheduler/tasks/:id/trigger/", async () => {
    await schedulerApi.trigger("task-1");
    expect(mockApi.post).toHaveBeenCalledWith(
      "/scheduler/tasks/task-1/trigger/",
    );
  });
});

describe("tradingApi (P7 additions)", () => {
  it("performanceSummary calls GET /trading/performance/summary/", async () => {
    await tradingApi.performanceSummary();
    expect(mockApi.get).toHaveBeenCalledWith(
      "/trading/performance/summary/",
    );
  });

  it("performanceBySymbol calls GET /trading/performance/by-symbol/", async () => {
    await tradingApi.performanceBySymbol();
    expect(mockApi.get).toHaveBeenCalledWith(
      "/trading/performance/by-symbol/",
    );
  });

  it("cancelAll calls POST /trading/cancel-all/", async () => {
    await tradingApi.cancelAll(2);
    expect(mockApi.post).toHaveBeenCalledWith("/trading/cancel-all/", {
      portfolio_id: 2,
    });
  });

  it("exchangeHealth calls GET /trading/exchange-health/", async () => {
    await tradingApi.exchangeHealth("binance");
    expect(mockApi.get).toHaveBeenCalledWith(
      "/trading/exchange-health/?exchange_id=binance",
    );
  });

  it("exchangeHealth without param calls base URL", async () => {
    await tradingApi.exchangeHealth();
    expect(mockApi.get).toHaveBeenCalledWith("/trading/exchange-health/");
  });
});
