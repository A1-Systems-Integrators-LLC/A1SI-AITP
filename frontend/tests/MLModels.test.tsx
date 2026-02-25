import { describe, it, expect, beforeEach, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { MLModels } from "../src/pages/MLModels";
import { ErrorBoundary } from "../src/components/ErrorBoundary";
import { WidgetErrorFallback } from "../src/components/WidgetErrorFallback";
import { renderWithProviders, mockFetch } from "./helpers";

const mockModels = [
  {
    model_id: "model-001",
    symbol: "BTC/USDT",
    timeframe: "1h",
    exchange: "binance",
    created_at: "2024-06-01T12:00:00Z",
  },
];

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    mockFetch({
      "/api/ml/models/": mockModels,
    }),
  );
});

describe("MLModels", () => {
  it("renders the page title", () => {
    renderWithProviders(<MLModels />);
    expect(screen.getByText("ML Models")).toBeInTheDocument();
  });

  it("renders train form", () => {
    renderWithProviders(<MLModels />);
    expect(screen.getByRole("button", { name: "Train Model" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Train Model" })).toBeInTheDocument();
  });

  it("renders predict section", () => {
    renderWithProviders(<MLModels />);
    expect(screen.getByText("Predict")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Run Prediction" })).toBeInTheDocument();
  });

  it("renders model summary card", () => {
    renderWithProviders(<MLModels />);
    expect(screen.getByText("Model Summary")).toBeInTheDocument();
  });

  it("shows trained models table when data loads", async () => {
    renderWithProviders(<MLModels />);
    await waitFor(() => {
      expect(screen.getByText("model-001")).toBeInTheDocument();
    });
    expect(screen.getByText("BTC/USDT")).toBeInTheDocument();
  });

  it("shows empty state when no models", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({ "/api/ml/models/": [] }),
    );
    renderWithProviders(<MLModels />);
    await waitFor(() => {
      expect(
        screen.getByText("No trained models yet. Use the training form to create one."),
      ).toBeInTheDocument();
    });
  });

  it("predict button is disabled without model selected", () => {
    renderWithProviders(<MLModels />);
    expect(screen.getByRole("button", { name: "Run Prediction" })).toBeDisabled();
  });

  it("shows error state when API fails", async () => {
    const failingFetch = (input: RequestInfo | URL) => {
      const url = typeof input === "string" ? input : input.toString();
      if (url.includes("ml/models")) {
        return Promise.resolve(new Response(JSON.stringify({ error: "fail" }), { status: 500 }));
      }
      return Promise.resolve(new Response(JSON.stringify([]), { status: 200, headers: { "Content-Type": "application/json" } }));
    };
    vi.stubGlobal("fetch", failingFetch);
    renderWithProviders(<MLModels />);
    expect(await screen.findByText("Failed to load ML models")).toBeInTheDocument();
  });
});

describe("MLModels - ErrorBoundary", () => {
  beforeEach(() => {
    vi.spyOn(console, "error").mockImplementation(() => {});
  });

  it("catches render errors with named fallback", () => {
    function ThrowingChild() { throw new Error("render crash"); }
    renderWithProviders(
      <ErrorBoundary fallback={<WidgetErrorFallback name="ML Models" />}>
        <ThrowingChild />
      </ErrorBoundary>,
    );
    expect(screen.getByText("ML Models unavailable")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toBeInTheDocument();
  });
});

describe("MLModels - Train Form Details", () => {
  it("renders symbol input", () => {
    renderWithProviders(<MLModels />);
    const symbolInput = screen.getByDisplayValue("BTC/USDT");
    expect(symbolInput).toBeInTheDocument();
  });

  it("renders timeframe select with 1h default", () => {
    renderWithProviders(<MLModels />);
    const select = screen.getByDisplayValue("1h");
    expect(select).toBeInTheDocument();
  });

  it("renders exchange select", () => {
    renderWithProviders(<MLModels />);
    const select = screen.getByLabelText("Exchange");
    expect(select).toBeInTheDocument();
    expect((select as HTMLSelectElement).value).toBe("binance");
  });

  it("renders test ratio input", () => {
    renderWithProviders(<MLModels />);
    const input = screen.getByDisplayValue("0.2");
    expect(input).toBeInTheDocument();
  });

  it("Run Prediction button is disabled without model", () => {
    renderWithProviders(<MLModels />);
    const btn = screen.getByRole("button", { name: "Run Prediction" });
    expect(btn).toBeDisabled();
  });
});

describe("MLModels - Model Details Table", () => {
  it("shows model ID in table", async () => {
    renderWithProviders(<MLModels />);
    expect(await screen.findByText("model-001")).toBeInTheDocument();
  });

  it("shows symbol in table", async () => {
    renderWithProviders(<MLModels />);
    expect(await screen.findByText("BTC/USDT")).toBeInTheDocument();
  });

  it("shows timeframe in table", async () => {
    renderWithProviders(<MLModels />);
    expect(await screen.findByText("1h")).toBeInTheDocument();
  });

  it("shows exchange in table", async () => {
    renderWithProviders(<MLModels />);
    expect(await screen.findByText("binance")).toBeInTheDocument();
  });
});
