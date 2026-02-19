import { describe, it, expect, beforeEach, vi } from "vitest";
import { screen } from "@testing-library/react";
import { Screening } from "../src/pages/Screening";
import { renderWithProviders, mockFetch } from "./helpers";

const mockStrategies = [
  { name: "ema_crossover", label: "EMA Crossover", description: "Fast/slow EMA crossover" },
  { name: "rsi_mean_reversion", label: "RSI Mean Reversion", description: "RSI oversold bounce" },
];

describe("Screening Page", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/screening/strategies": mockStrategies,
      }),
    );
  });

  it("renders the page heading", () => {
    renderWithProviders(<Screening />);
    expect(screen.getByText("Strategy Screening")).toBeInTheDocument();
  });

  it("renders configuration form", () => {
    renderWithProviders(<Screening />);
    expect(screen.getByText("Configuration")).toBeInTheDocument();
    expect(screen.getByText("Run Screen")).toBeInTheDocument();
  });

  it("renders symbol input with default value", () => {
    renderWithProviders(<Screening />);
    const input = screen.getByDisplayValue("BTC/USDT");
    expect(input).toBeInTheDocument();
  });

  it("renders timeframe selector", () => {
    renderWithProviders(<Screening />);
    expect(screen.getByDisplayValue("1h")).toBeInTheDocument();
  });

  it("renders exchange selector with Binance default", () => {
    renderWithProviders(<Screening />);
    expect(screen.getByDisplayValue("Binance")).toBeInTheDocument();
  });

  it("renders strategy list after data loads", async () => {
    renderWithProviders(<Screening />);
    expect(await screen.findByText("EMA Crossover")).toBeInTheDocument();
    expect(await screen.findByText("RSI Mean Reversion")).toBeInTheDocument();
  });

  it("shows placeholder when no job is active", () => {
    renderWithProviders(<Screening />);
    expect(
      screen.getByText("Configure parameters and run a screen to see results."),
    ).toBeInTheDocument();
  });
});
