import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen } from "@testing-library/react";
import { render } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Layout } from "../src/components/Layout";
import { ToastProvider } from "../src/components/Toast";

// Mock useSystemEvents to control halt/connection state
const mockSystemEvents = {
  isConnected: true,
  isReconnecting: false,
  reconnectAttempt: 0,
  reconnect: vi.fn(),
  isHalted: false,
  haltReason: "",
  lastOrderUpdate: null,
  lastRiskAlert: null,
};

vi.mock("../src/hooks/useSystemEvents", () => ({
  useSystemEvents: () => mockSystemEvents,
}));

function renderLayout(props?: { isHalted?: boolean; isReconnecting?: boolean; reconnectAttempt?: number; username?: string }) {
  if (props?.isHalted !== undefined) mockSystemEvents.isHalted = props.isHalted;
  if (props?.isReconnecting !== undefined) mockSystemEvents.isReconnecting = props.isReconnecting;
  if (props?.reconnectAttempt !== undefined) mockSystemEvents.reconnectAttempt = props.reconnectAttempt;

  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <ToastProvider>
          <Routes>
            <Route element={<Layout onLogout={async () => {}} username={props?.username ?? "testuser"} />}>
              <Route index element={<div>Page Content</div>} />
            </Route>
          </Routes>
        </ToastProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("Layout", () => {
  beforeEach(() => {
    mockSystemEvents.isHalted = false;
    mockSystemEvents.isReconnecting = false;
    mockSystemEvents.reconnectAttempt = 0;
  });

  it("renders the app title", () => {
    renderLayout();
    expect(screen.getByText("A1SI-AITP")).toBeInTheDocument();
  });

  it("renders navigation items", () => {
    renderLayout();
    expect(screen.getByText("Dashboard")).toBeInTheDocument();
    expect(screen.getByText("Portfolio")).toBeInTheDocument();
    expect(screen.getByText("Trading")).toBeInTheDocument();
    expect(screen.getByText("Risk")).toBeInTheDocument();
    expect(screen.getByText("Settings")).toBeInTheDocument();
  });

  it("renders asset class selector", () => {
    renderLayout();
    expect(screen.getByText("Crypto")).toBeInTheDocument();
    expect(screen.getByText("Equities")).toBeInTheDocument();
    expect(screen.getByText("Forex")).toBeInTheDocument();
  });

  it("shows username in sidebar", () => {
    renderLayout({ username: "admin" });
    expect(screen.getByText("admin")).toBeInTheDocument();
  });

  it("renders sign out button", () => {
    renderLayout();
    expect(screen.getByText("Sign Out")).toBeInTheDocument();
  });

  it("shows halt banner when halted", () => {
    renderLayout({ isHalted: true });
    expect(screen.getByText(/TRADING HALTED/)).toBeInTheDocument();
  });

  it("shows reconnecting banner", () => {
    renderLayout({ isReconnecting: true, reconnectAttempt: 3 });
    expect(screen.getByText(/reconnecting/i)).toBeInTheDocument();
    expect(screen.getByText(/attempt 3/i)).toBeInTheDocument();
  });
});
