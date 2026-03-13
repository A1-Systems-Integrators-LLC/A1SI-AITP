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

  it("shows Weekend for forex on Saturday", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-02-28T12:00:00Z")); // Saturday
    render(<MarketStatusBadge assetClass="forex" />);
    expect(screen.getByText("Weekend")).toBeInTheDocument();
  });

  it("shows Weekend for forex on Friday after 22:00 UTC", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-02-27T23:00:00Z")); // Friday 23:00 UTC
    render(<MarketStatusBadge assetClass="forex" />);
    expect(screen.getByText("Weekend")).toBeInTheDocument();
  });

  it("shows Session Active for forex on Friday before 22:00 UTC", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-02-27T21:00:00Z")); // Friday 21:00 UTC
    render(<MarketStatusBadge assetClass="forex" />);
    expect(screen.getByText("Session Active")).toBeInTheDocument();
  });

  it("shows Weekend for forex on Sunday before 22:00 UTC", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-03-01T10:00:00Z")); // Sunday 10:00 UTC
    render(<MarketStatusBadge assetClass="forex" />);
    expect(screen.getByText("Weekend")).toBeInTheDocument();
  });

  it("shows Session Active for forex on Sunday after 22:00 UTC", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-03-01T22:30:00Z")); // Sunday 22:30 UTC
    render(<MarketStatusBadge assetClass="forex" />);
    expect(screen.getByText("Session Active")).toBeInTheDocument();
  });

  it("shows Market Closed for equity after hours", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-02-25T22:00:00Z")); // Wednesday 5pm ET (after close)
    render(<MarketStatusBadge assetClass="equity" />);
    expect(screen.getByText("Market Closed")).toBeInTheDocument();
  });
});
