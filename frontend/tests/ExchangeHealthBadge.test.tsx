import { describe, it, expect, vi } from "vitest";
import { screen } from "@testing-library/react";
import { ExchangeHealthBadge } from "../src/components/ExchangeHealthBadge";
import { renderWithProviders, mockFetch } from "./helpers";

describe("ExchangeHealthBadge", () => {
  it("shows loading state initially", () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({}), // empty handlers — will return [] for unmatched
    );
    renderWithProviders(<ExchangeHealthBadge />);
    expect(screen.getByText("Checking...")).toBeInTheDocument();
  });

  it("shows connected state with exchange name and latency", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/trading/exchange-health": {
          connected: true,
          exchange: "Binance",
          latency_ms: 120,
        },
      }),
    );
    renderWithProviders(<ExchangeHealthBadge />);
    expect(await screen.findByText("Binance")).toBeInTheDocument();
    expect(screen.getByText("120ms")).toBeInTheDocument();
  });

  it("shows disconnected state", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/trading/exchange-health": {
          connected: false,
          exchange: "Binance",
          latency_ms: 0,
          error: "Connection timeout",
        },
      }),
    );
    renderWithProviders(<ExchangeHealthBadge />);
    expect(await screen.findByText("Disconnected")).toBeInTheDocument();
  });

  it("shows error tooltip on disconnected state", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/trading/exchange-health": {
          connected: false,
          exchange: "Binance",
          latency_ms: 0,
          error: "Connection timeout",
        },
      }),
    );
    renderWithProviders(<ExchangeHealthBadge />);
    const badge = await screen.findByText("Disconnected");
    expect(badge.closest("span")).toHaveAttribute("title", "Connection timeout");
  });

  it("uses default exchangeId when none provided", () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/trading/exchange-health": {
          connected: true,
          exchange: "Binance",
          latency_ms: 50,
        },
      }),
    );
    renderWithProviders(<ExchangeHealthBadge />);
    // No errors thrown, component renders
    expect(screen.getByText("Checking...")).toBeInTheDocument();
  });

  it("passes custom exchangeId", () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ connected: true, exchange: "Kraken", latency_ms: 200 }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);
    renderWithProviders(<ExchangeHealthBadge exchangeId="kraken" />);
    // Verify the fetch was called with the exchange_id param
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("exchange_id=kraken"),
      expect.anything(),
    );
  });

  it("shows green dot when connected", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/trading/exchange-health": {
          connected: true,
          exchange: "Binance",
          latency_ms: 100,
        },
      }),
    );
    renderWithProviders(<ExchangeHealthBadge />);
    const dot = await screen.findByTestId("health-dot-connected");
    expect(dot.className).toContain("bg-green-500");
  });

  it("shows red dot when disconnected", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/trading/exchange-health": {
          connected: false,
          exchange: "Binance",
          latency_ms: 0,
        },
      }),
    );
    renderWithProviders(<ExchangeHealthBadge />);
    const dot = await screen.findByTestId("health-dot-disconnected");
    expect(dot.className).toContain("bg-red-500");
  });
});
