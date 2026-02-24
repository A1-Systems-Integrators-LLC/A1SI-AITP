import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { MarketStatusBadge } from "../src/components/MarketStatusBadge";

describe("MarketStatusBadge", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it("returns null for crypto", () => {
    const { container } = render(<MarketStatusBadge assetClass="crypto" />);
    expect(container.innerHTML).toBe("");
  });

  it("shows Market Open for equity during NYSE hours", () => {
    // Wednesday 2:00 PM ET = 19:00 UTC
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-02-25T19:00:00Z")); // Wednesday 2pm ET
    render(<MarketStatusBadge assetClass="equity" />);
    expect(screen.getByText("Market Open")).toBeInTheDocument();
  });

  it("shows Market Closed for equity on weekend", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-02-28T19:00:00Z")); // Saturday
    render(<MarketStatusBadge assetClass="equity" />);
    expect(screen.getByText("Market Closed")).toBeInTheDocument();
  });

  it("shows Session Active for forex on weekday", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-02-25T14:00:00Z")); // Wednesday
    render(<MarketStatusBadge assetClass="forex" />);
    expect(screen.getByText("Session Active")).toBeInTheDocument();
  });
});
