import { describe, it, expect, beforeEach, vi } from "vitest";
import { screen, waitFor, fireEvent } from "@testing-library/react";
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

describe("MLModels - Model Count Display", () => {
  it("shows model count in summary card", async () => {
    renderWithProviders(<MLModels />);
    await waitFor(() => {
      expect(screen.getByText("1")).toBeInTheDocument();
    });
    expect(screen.getByText("Trained models available")).toBeInTheDocument();
  });

  it("shows 0 count when no models", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({ "/api/ml/models/": [] }),
    );
    renderWithProviders(<MLModels />);
    await waitFor(() => {
      expect(screen.getByText("0")).toBeInTheDocument();
    });
    expect(screen.getByText("Trained models available")).toBeInTheDocument();
  });
});

describe("MLModels - Train Mutation", () => {
  it("clicking Train Model fires trainMutation and sets activeJobId", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/ml/models/": mockModels,
        "/api/ml/train": { job_id: "train-job-1", status: "pending" },
        "/api/jobs/train-job-1": { id: "train-job-1", job_type: "ml_training", status: "running", progress: 50, progress_message: "Training...", error: null, result: null },
      }),
    );
    renderWithProviders(<MLModels />);
    const trainBtn = screen.getByRole("button", { name: "Train Model" });
    fireEvent.click(trainBtn);
    // After mutation succeeds, it sets activeJobId which triggers job polling
    await waitFor(() => {
      expect(screen.getByText("Training: ml training")).toBeInTheDocument();
    });
  });

  it("shows job progress bar when job is running", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/ml/models/": mockModels,
        "/api/ml/train": { job_id: "train-job-2", status: "pending" },
        "/api/jobs/train-job-2": { id: "train-job-2", job_type: "ml_training", status: "running", progress: 50, progress_message: "Training step 5/10", error: null, result: null },
      }),
    );
    renderWithProviders(<MLModels />);
    fireEvent.click(screen.getByRole("button", { name: "Train Model" }));
    await waitFor(() => {
      expect(screen.getByText("running")).toBeInTheDocument();
    });
  });

  it("shows completed status when job finishes", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/ml/models/": mockModels,
        "/api/ml/train": { job_id: "train-job-3", status: "pending" },
        "/api/jobs/train-job-3": { id: "train-job-3", job_type: "ml_training", status: "completed", progress: 100, progress_message: "Done", error: null, result: null },
      }),
    );
    renderWithProviders(<MLModels />);
    fireEvent.click(screen.getByRole("button", { name: "Train Model" }));
    await waitFor(() => {
      expect(screen.getByText("completed")).toBeInTheDocument();
    });
  });

  it("shows failed status and error message when job fails", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/ml/models/": mockModels,
        "/api/ml/train": { job_id: "train-job-4", status: "pending" },
        "/api/jobs/train-job-4": { id: "train-job-4", job_type: "ml_training", status: "failed", progress: 0, progress_message: null, error: "Insufficient data", result: null },
      }),
    );
    renderWithProviders(<MLModels />);
    fireEvent.click(screen.getByRole("button", { name: "Train Model" }));
    await waitFor(() => {
      expect(screen.getByText("failed")).toBeInTheDocument();
    });
    expect(screen.getByText("Insufficient data")).toBeInTheDocument();
  });

  it("train mutation error shows toast", async () => {
    const failFetch = (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input.toString();
      if (url.includes("/ml/train") && init?.method === "POST") {
        return Promise.resolve(new Response(JSON.stringify({ error: "fail" }), { status: 500 }));
      }
      return mockFetch({ "/api/ml/models/": mockModels })(input, init);
    };
    vi.stubGlobal("fetch", failFetch);
    renderWithProviders(<MLModels />);
    fireEvent.click(screen.getByRole("button", { name: "Train Model" }));
    await waitFor(() => {
      expect(screen.getByText(/Failed to start training|fail/)).toBeInTheDocument();
    });
  });
});

describe("MLModels - Predict Mutation", () => {
  it("selecting a model and clicking Run Prediction shows result", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/ml/models/": mockModels,
        "/api/ml/predict": {
          model_id: "model-001",
          symbol: "BTC/USDT",
          predictions: [
            { timestamp: "2026-01-01T00:00:00Z", prediction: 1, probability: 0.85 },
            { timestamp: "2026-01-01T01:00:00Z", prediction: 0, probability: 0.65 },
          ],
        },
      }),
    );
    renderWithProviders(<MLModels />);
    // Wait for models to load
    await waitFor(() => {
      expect(screen.getByText("model-001")).toBeInTheDocument();
    });
    // Select the model in the predict dropdown
    const predictSelect = screen.getByLabelText("Model ID");
    fireEvent.change(predictSelect, { target: { value: "model-001" } });
    // Click Run Prediction
    const predictBtn = screen.getByRole("button", { name: "Run Prediction" });
    expect(predictBtn).not.toBeDisabled();
    fireEvent.click(predictBtn);
    // Wait for prediction result to display in <pre>
    await waitFor(() => {
      expect(screen.getByText(/prediction/)).toBeInTheDocument();
    });
  });

  it("predict mutation error sets error in result", async () => {
    const failFetch = (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input.toString();
      if (url.includes("/ml/predict") && init?.method === "POST") {
        return Promise.resolve(new Response(JSON.stringify({ error: "model not found" }), { status: 404 }));
      }
      return mockFetch({ "/api/ml/models/": mockModels })(input, init);
    };
    vi.stubGlobal("fetch", failFetch);
    renderWithProviders(<MLModels />);
    await waitFor(() => {
      expect(screen.getByText("model-001")).toBeInTheDocument();
    });
    const predictSelect = screen.getByLabelText("Model ID");
    fireEvent.change(predictSelect, { target: { value: "model-001" } });
    const predictBtn = screen.getByRole("button", { name: "Run Prediction" });
    fireEvent.click(predictBtn);
    await waitFor(() => {
      expect(screen.getByText(/Error:/)).toBeInTheDocument();
    });
  });
});

describe("MLModels - Form Interactions", () => {
  it("changing symbol input updates value", () => {
    renderWithProviders(<MLModels />);
    const input = screen.getByDisplayValue("BTC/USDT");
    fireEvent.change(input, { target: { value: "ETH/USDT" } });
    expect(screen.getByDisplayValue("ETH/USDT")).toBeInTheDocument();
  });

  it("changing timeframe select updates value", () => {
    renderWithProviders(<MLModels />);
    const select = screen.getByDisplayValue("1h");
    fireEvent.change(select, { target: { value: "4h" } });
    expect(screen.getByDisplayValue("4h")).toBeInTheDocument();
  });

  it("changing exchange select updates value", () => {
    renderWithProviders(<MLModels />);
    const select = screen.getByLabelText("Exchange");
    fireEvent.change(select, { target: { value: "bybit" } });
    expect((select as HTMLSelectElement).value).toBe("bybit");
  });

  it("changing test ratio updates value", () => {
    renderWithProviders(<MLModels />);
    const input = screen.getByDisplayValue("0.2");
    fireEvent.change(input, { target: { value: "0.3" } });
    expect(screen.getByDisplayValue("0.3")).toBeInTheDocument();
  });

  it("model dropdown shows options from loaded models", async () => {
    renderWithProviders(<MLModels />);
    await waitFor(() => {
      expect(screen.getByText("model-001")).toBeInTheDocument();
    });
    // The predict model select should include model-001
    const options = screen.getAllByText(/model-001/);
    expect(options.length).toBeGreaterThanOrEqual(1);
  });

  it("model table shows dash for missing created_at", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/ml/models/": [{ ...mockModels[0], created_at: null }],
      }),
    );
    renderWithProviders(<MLModels />);
    await waitFor(() => {
      expect(screen.getByText("model-001")).toBeInTheDocument();
    });
    expect(screen.getByText("\u2014")).toBeInTheDocument();
  });
});
