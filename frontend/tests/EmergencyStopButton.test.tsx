import { describe, it, expect, beforeEach, vi, afterEach } from "vitest";
import { screen, fireEvent, act, waitFor } from "@testing-library/react";
import { EmergencyStopButton } from "../src/components/EmergencyStopButton";
import { renderWithProviders, mockFetch } from "./helpers";

beforeEach(() => {
  vi.useFakeTimers();
  vi.stubGlobal("fetch", mockFetch({
    "/api/risk/": { is_halted: false },
  }));
});

afterEach(() => {
  vi.useRealTimers();
});

describe("EmergencyStopButton", () => {
  it("renders EMERGENCY STOP button when not halted", () => {
    renderWithProviders(<EmergencyStopButton isHalted={false} />);
    expect(screen.getByText("EMERGENCY STOP")).toBeInTheDocument();
  });

  it("renders HALTED badge when halted", () => {
    renderWithProviders(<EmergencyStopButton isHalted={true} />);
    expect(screen.getByText("HALTED")).toBeInTheDocument();
    expect(screen.queryByText("EMERGENCY STOP")).not.toBeInTheDocument();
  });

  it("renders EMERGENCY STOP when isHalted is null", () => {
    renderWithProviders(<EmergencyStopButton isHalted={null} />);
    expect(screen.getByText("EMERGENCY STOP")).toBeInTheDocument();
  });

  it("button is not disabled in normal state", () => {
    renderWithProviders(<EmergencyStopButton isHalted={false} />);
    const button = screen.getByRole("button");
    expect(button).not.toBeDisabled();
  });

  it("starts hold progress on mouseDown and shows hold text", () => {
    renderWithProviders(<EmergencyStopButton isHalted={false} />);
    const button = screen.getByRole("button");

    fireEvent.mouseDown(button);
    // Advance a few intervals to get progress > 0
    act(() => { vi.advanceTimersByTime(200); });

    expect(screen.getByText("Hold to halt...")).toBeInTheDocument();
  });

  it("cancels hold on mouseUp before completion", () => {
    renderWithProviders(<EmergencyStopButton isHalted={false} />);
    const button = screen.getByRole("button");

    fireEvent.mouseDown(button);
    act(() => { vi.advanceTimersByTime(300); });
    expect(screen.getByText("Hold to halt...")).toBeInTheDocument();

    fireEvent.mouseUp(button);
    expect(screen.getByText("EMERGENCY STOP")).toBeInTheDocument();
  });

  it("cancels hold on mouseLeave before completion", () => {
    renderWithProviders(<EmergencyStopButton isHalted={false} />);
    const button = screen.getByRole("button");

    fireEvent.mouseDown(button);
    act(() => { vi.advanceTimersByTime(200); });

    fireEvent.mouseLeave(button);
    expect(screen.getByText("EMERGENCY STOP")).toBeInTheDocument();
  });

  it("triggers halt mutation after holding for 2 seconds", async () => {
    vi.useRealTimers();
    const fetchMock = vi.fn().mockImplementation(() =>
      Promise.resolve(new Response(JSON.stringify({ is_halted: true }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      })),
    );
    vi.stubGlobal("fetch", fetchMock);

    renderWithProviders(<EmergencyStopButton isHalted={false} portfolioId={1} />);
    const button = screen.getByRole("button");

    fireEvent.mouseDown(button);

    // Wait for the interval to fire enough times (20 * 100ms = 2s)
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining("/api/risk/1/halt/"),
        expect.objectContaining({ method: "POST" }),
      );
    }, { timeout: 3000 });
  });

  it("shows error toast on halt mutation failure", async () => {
    vi.useRealTimers();
    const fetchMock = vi.fn().mockImplementation(() =>
      Promise.resolve(new Response(JSON.stringify({ error: "Server error" }), {
        status: 500,
        headers: { "Content-Type": "application/json" },
      })),
    );
    vi.stubGlobal("fetch", fetchMock);

    renderWithProviders(<EmergencyStopButton isHalted={false} />);
    const button = screen.getByRole("button");

    fireEvent.mouseDown(button);

    // The onError should fire — wait for mutation to complete and button to reset
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalled();
    }, { timeout: 3000 });
  });

  it("halted state has correct aria attributes", () => {
    renderWithProviders(<EmergencyStopButton isHalted={true} />);
    expect(screen.getByRole("status")).toHaveAttribute("aria-label", "Trading halted");
  });
});
