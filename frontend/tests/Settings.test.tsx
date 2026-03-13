import { describe, it, expect, beforeEach, vi } from "vitest";
import { screen, fireEvent, waitFor } from "@testing-library/react";
import { Settings } from "../src/pages/Settings";
import { ErrorBoundary } from "../src/components/ErrorBoundary";
import { WidgetErrorFallback } from "../src/components/WidgetErrorFallback";
import { renderWithProviders, mockFetch } from "./helpers";

const mockConfigs = [
  {
    id: 1,
    name: "Binance Main",
    exchange_id: "binance",
    is_sandbox: true,
    is_default: true,
    api_key_masked: "abc...xyz",
    has_api_secret: true,
    has_passphrase: false,
    last_test_success: true,
    last_test_error: null,
    created_at: "2026-01-01T00:00:00Z",
  },
];

const mockDataSources = [
  {
    id: 1,
    exchange_config: 1,
    exchange_name: "Binance Main",
    symbols: ["BTC/USDT", "ETH/USDT"],
    timeframes: ["1h", "4h"],
    fetch_interval_minutes: 60,
    is_active: true,
    last_fetched_at: "2026-02-15T12:00:00Z",
  },
];

const mockNotifPrefs = {
  telegram_enabled: true,
  webhook_enabled: false,
  on_order_submitted: true,
  on_order_filled: true,
  on_order_cancelled: false,
  on_risk_halt: true,
  on_trade_rejected: true,
  on_daily_summary: false,
};

function setupMocks() {
  vi.stubGlobal(
    "fetch",
    mockFetch({
      "/api/exchange-configs": mockConfigs,
      "/api/data-sources": mockDataSources,
      "/api/notifications/preferences": mockNotifPrefs,
    }),
  );
}

describe("Settings Page", () => {
  beforeEach(setupMocks);

  it("renders the page heading", () => {
    renderWithProviders(<Settings />);
    expect(screen.getByText("Settings")).toBeInTheDocument();
  });

  it("renders Exchange Connections section", () => {
    renderWithProviders(<Settings />);
    expect(screen.getByText("Exchange Connections")).toBeInTheDocument();
  });

  it("renders exchange config card", async () => {
    renderWithProviders(<Settings />);
    const names = await screen.findAllByText("Binance Main");
    expect(names.length).toBeGreaterThanOrEqual(1);
    expect(await screen.findByText("binance")).toBeInTheDocument();
  });

  it("shows sandbox badge for sandbox config", async () => {
    renderWithProviders(<Settings />);
    expect(await screen.findByText("sandbox")).toBeInTheDocument();
  });

  it("shows default badge for default config", async () => {
    renderWithProviders(<Settings />);
    expect(await screen.findByText("default")).toBeInTheDocument();
  });

  it("renders Data Sources section", () => {
    renderWithProviders(<Settings />);
    expect(screen.getByText("Data Sources")).toBeInTheDocument();
  });

  it("renders data source with symbols and timeframes", async () => {
    renderWithProviders(<Settings />);
    expect(await screen.findByText("BTC/USDT")).toBeInTheDocument();
    expect(await screen.findByText("ETH/USDT")).toBeInTheDocument();
  });

  it("renders Notifications section", () => {
    renderWithProviders(<Settings />);
    expect(screen.getByText("Notifications")).toBeInTheDocument();
  });

  it("renders About section", () => {
    renderWithProviders(<Settings />);
    expect(screen.getByText("About")).toBeInTheDocument();
    expect(screen.getByText("A1SI-AITP v0.1.0")).toBeInTheDocument();
  });
});

describe("Settings - Add Exchange Flow", () => {
  beforeEach(setupMocks);

  it("shows Add Exchange button initially", async () => {
    renderWithProviders(<Settings />);
    expect(await screen.findByText("Add Exchange")).toBeInTheDocument();
  });

  it("shows exchange form when Add Exchange is clicked", async () => {
    renderWithProviders(<Settings />);
    const addBtn = await screen.findByText("Add Exchange");
    fireEvent.click(addBtn);
    // Form should appear with Name and Exchange fields
    expect(screen.getByText("Name")).toBeInTheDocument();
    expect(screen.getByText("API Key")).toBeInTheDocument();
    expect(screen.getByText("API Secret")).toBeInTheDocument();
    expect(screen.getByText("Sandbox mode")).toBeInTheDocument();
  });

  it("hides Add Exchange button when form is open", async () => {
    renderWithProviders(<Settings />);
    const addBtn = await screen.findByText("Add Exchange");
    fireEvent.click(addBtn);
    // The "Add Exchange" button in the header should be gone
    // but the form submit button says "Add Exchange" too
    const addBtns = screen.queryAllByText("Add Exchange");
    // Only the form submit button should remain
    expect(addBtns.length).toBe(1);
  });

  it("shows Cancel button in add form", async () => {
    renderWithProviders(<Settings />);
    const addBtn = await screen.findByText("Add Exchange");
    fireEvent.click(addBtn);
    const cancelBtns = screen.getAllByText("Cancel");
    expect(cancelBtns.length).toBeGreaterThanOrEqual(1);
  });

  it("closes form when Cancel is clicked", async () => {
    renderWithProviders(<Settings />);
    const addBtn = await screen.findByText("Add Exchange");
    fireEvent.click(addBtn);
    expect(screen.getByText("API Key")).toBeInTheDocument();
    const cancelBtns = screen.getAllByText("Cancel");
    fireEvent.click(cancelBtns[0]);
    // Form should close, Add Exchange button should return in header
    expect(screen.queryByText("API Key")).not.toBeInTheDocument();
  });
});

describe("Settings - Edit and Delete Flow", () => {
  beforeEach(setupMocks);

  it("shows Edit button on config card", async () => {
    renderWithProviders(<Settings />);
    expect(await screen.findByText("Edit")).toBeInTheDocument();
  });

  it("shows edit form when Edit is clicked", async () => {
    renderWithProviders(<Settings />);
    const editBtn = await screen.findByText("Edit");
    fireEvent.click(editBtn);
    expect(screen.getByText("API Key")).toBeInTheDocument();
    expect(screen.getByText("Update")).toBeInTheDocument();
  });

  it("shows Delete buttons on config and data source cards", async () => {
    renderWithProviders(<Settings />);
    // Delete appears on both exchange config card and data source card
    const deleteBtns = await screen.findAllByText("Delete");
    expect(deleteBtns.length).toBeGreaterThanOrEqual(2);
  });

  it("shows Confirm and No buttons after Delete click on exchange config", async () => {
    renderWithProviders(<Settings />);
    const deleteBtns = await screen.findAllByText("Delete");
    // First Delete button is on the exchange config card
    fireEvent.click(deleteBtns[0]);
    expect(screen.getByText("Confirm")).toBeInTheDocument();
    expect(screen.getByText("No")).toBeInTheDocument();
  });

  it("cancels delete when No is clicked", async () => {
    renderWithProviders(<Settings />);
    const deleteBtns = await screen.findAllByText("Delete");
    fireEvent.click(deleteBtns[0]);
    fireEvent.click(screen.getByText("No"));
    // Should go back to normal state with Delete buttons
    const afterBtns = await screen.findAllByText("Delete");
    expect(afterBtns.length).toBeGreaterThanOrEqual(2);
    expect(screen.queryByText("Confirm")).not.toBeInTheDocument();
  });
});

describe("Settings - Test Connection", () => {
  beforeEach(setupMocks);

  it("shows Test button on config card", async () => {
    renderWithProviders(<Settings />);
    expect(await screen.findByText("Test")).toBeInTheDocument();
  });

  it("shows Testing... state while test is running", async () => {
    renderWithProviders(<Settings />);
    const testBtn = await screen.findByText("Test");
    fireEvent.click(testBtn);
    expect(screen.getByText("Testing...")).toBeInTheDocument();
  });
});

describe("Settings - Connection Status", () => {
  it("shows green dot for successful connection", async () => {
    setupMocks();
    renderWithProviders(<Settings />);
    const dot = await screen.findByTitle("Connected");
    expect(dot).toBeInTheDocument();
  });

  it("shows gray dot for untested connection", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/exchange-configs": [
          { ...mockConfigs[0], last_test_success: null },
        ],
        "/api/data-sources": mockDataSources,
        "/api/notifications/preferences": mockNotifPrefs,
      }),
    );
    renderWithProviders(<Settings />);
    const dot = await screen.findByTitle("Not tested");
    expect(dot).toBeInTheDocument();
  });

  it("shows red dot for failed connection", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/exchange-configs": [
          { ...mockConfigs[0], last_test_success: false, last_test_error: "Auth failed" },
        ],
        "/api/data-sources": mockDataSources,
        "/api/notifications/preferences": mockNotifPrefs,
      }),
    );
    renderWithProviders(<Settings />);
    const dot = await screen.findByTitle("Auth failed");
    expect(dot).toBeInTheDocument();
  });
});

describe("Settings - Masked API Key", () => {
  beforeEach(setupMocks);

  it("shows masked API key on config card", async () => {
    renderWithProviders(<Settings />);
    expect(await screen.findByText("Key: abc...xyz")).toBeInTheDocument();
  });
});

describe("Settings - Accessibility Labels", () => {
  it("show/hide buttons have aria-labels", async () => {
    setupMocks();
    renderWithProviders(<Settings />);
    const addBtn = await screen.findByText("Add Exchange");
    fireEvent.click(addBtn);
    const buttons = screen.getAllByRole("button");
    const toggleButtons = buttons.filter(btn => {
      const label = btn.getAttribute("aria-label") || "";
      return label.includes("API key") || label.includes("API secret") || label.includes("passphrase");
    });
    expect(toggleButtons.length).toBeGreaterThan(0);
  });
});

describe("Settings - Empty State", () => {
  it("shows empty message when no configs exist", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/exchange-configs": [],
        "/api/data-sources": [],
        "/api/notifications/preferences": mockNotifPrefs,
      }),
    );
    renderWithProviders(<Settings />);
    expect(
      await screen.findByText(/No exchange connections configured/),
    ).toBeInTheDocument();
  });
});

describe("Settings - Notification Preferences", () => {
  it("renders notification toggle labels", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/exchange-configs": mockConfigs,
        "/api/data-sources": mockDataSources,
        "/api/notifications/preferences": mockNotifPrefs,
        "/api/portfolios": [{ id: 1, name: "Main" }],
      }),
    );
    renderWithProviders(<Settings />);
    expect(await screen.findByText("Order Submitted")).toBeInTheDocument();
    expect(screen.getByText("Order Filled")).toBeInTheDocument();
    expect(screen.getByText("Order Cancelled")).toBeInTheDocument();
    expect(screen.getByText("Risk Halt/Resume")).toBeInTheDocument();
    expect(screen.getByText("Trade Rejected")).toBeInTheDocument();
    expect(screen.getByText("Daily Summary")).toBeInTheDocument();
  });

  it("renders Telegram and Webhook channel checkboxes", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/exchange-configs": mockConfigs,
        "/api/data-sources": mockDataSources,
        "/api/notifications/preferences": mockNotifPrefs,
        "/api/portfolios": [{ id: 1, name: "Main" }],
      }),
    );
    renderWithProviders(<Settings />);
    expect(await screen.findByText("Telegram")).toBeInTheDocument();
    expect(screen.getByText("Webhook")).toBeInTheDocument();
  });

  it("shows portfolio selector when portfolios exist", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/exchange-configs": mockConfigs,
        "/api/data-sources": mockDataSources,
        "/api/notifications/preferences": mockNotifPrefs,
        "/api/portfolios": [{ id: 1, name: "Main" }, { id: 2, name: "Test" }],
      }),
    );
    renderWithProviders(<Settings />);
    expect(await screen.findByText("Portfolio:")).toBeInTheDocument();
  });
});

describe("Settings - Audit Log", () => {
  it("renders Audit Log section heading", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/exchange-configs": mockConfigs,
        "/api/data-sources": mockDataSources,
        "/api/notifications/preferences": mockNotifPrefs,
        "/api/audit-log": { results: [], total: 0 },
      }),
    );
    renderWithProviders(<Settings />);
    expect(await screen.findByText("Audit Log")).toBeInTheDocument();
  });

  it("shows empty message when no audit entries", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/exchange-configs": mockConfigs,
        "/api/data-sources": mockDataSources,
        "/api/notifications/preferences": mockNotifPrefs,
        "/api/audit-log": { results: [], total: 0 },
      }),
    );
    renderWithProviders(<Settings />);
    expect(await screen.findByText("No audit log entries found.")).toBeInTheDocument();
  });

  it("shows audit log entries in table", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/exchange-configs": mockConfigs,
        "/api/data-sources": mockDataSources,
        "/api/notifications/preferences": mockNotifPrefs,
        "/api/audit-log": {
          results: [
            {
              id: 1,
              user: "admin",
              action: "POST /api/trading/orders/",
              ip_address: "127.0.0.1",
              status_code: 201,
              created_at: "2026-02-25T10:00:00Z",
            },
          ],
          total: 1,
        },
      }),
    );
    renderWithProviders(<Settings />);
    expect(await screen.findByText("admin")).toBeInTheDocument();
    expect(screen.getByText("POST /api/trading/orders/")).toBeInTheDocument();
    expect(screen.getByText("201")).toBeInTheDocument();
  });

  it("has user filter input", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/exchange-configs": mockConfigs,
        "/api/data-sources": mockDataSources,
        "/api/notifications/preferences": mockNotifPrefs,
        "/api/audit-log": { results: [], total: 0 },
      }),
    );
    renderWithProviders(<Settings />);
    expect(await screen.findByPlaceholderText("Filter by user")).toBeInTheDocument();
  });
});

describe("Settings - Data Source Display", () => {
  beforeEach(setupMocks);

  it("shows fetch interval", async () => {
    renderWithProviders(<Settings />);
    expect(await screen.findByText(/Every 60min/)).toBeInTheDocument();
  });

  it("shows timeframe badges", async () => {
    renderWithProviders(<Settings />);
    expect(await screen.findByText("1h")).toBeInTheDocument();
    expect(await screen.findByText("4h")).toBeInTheDocument();
  });

  it("shows Add Data Source button when configs exist", async () => {
    renderWithProviders(<Settings />);
    expect(await screen.findByText("Add Data Source")).toBeInTheDocument();
  });

  it("shows last fetched time", async () => {
    renderWithProviders(<Settings />);
    expect(await screen.findByText(/Last:/)).toBeInTheDocument();
  });
});

describe("Settings - Live badge for non-sandbox config", () => {
  it("shows live badge when is_sandbox is false", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/exchange-configs": [
          { ...mockConfigs[0], is_sandbox: false, is_default: false },
        ],
        "/api/data-sources": mockDataSources,
        "/api/notifications/preferences": mockNotifPrefs,
      }),
    );
    renderWithProviders(<Settings />);
    expect(await screen.findByText("live")).toBeInTheDocument();
  });
});

describe("Settings - ErrorBoundary", () => {
  beforeEach(() => {
    vi.spyOn(console, "error").mockImplementation(() => {});
  });

  it("catches render errors with named fallback", () => {
    function ThrowingChild() { throw new Error("render crash"); }
    renderWithProviders(
      <ErrorBoundary fallback={<WidgetErrorFallback name="Settings" />}>
        <ThrowingChild />
      </ErrorBoundary>,
    );
    expect(screen.getByText("Settings unavailable")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toBeInTheDocument();
  });
});

describe("Settings - Create Exchange Mutation", () => {
  it("submits create form and triggers mutation", async () => {
    const fetchSpy = vi.fn(
      mockFetch({
        "/api/exchange-configs": mockConfigs,
        "/api/data-sources": mockDataSources,
        "/api/notifications/preferences": mockNotifPrefs,
      }),
    );
    vi.stubGlobal("fetch", fetchSpy);
    renderWithProviders(<Settings />);
    const addBtn = await screen.findByText("Add Exchange");
    fireEvent.click(addBtn);
    // Fill the name field
    const nameInput = screen.getByPlaceholderText("e.g. Binance Main");
    fireEvent.change(nameInput, { target: { value: "My Exchange" } });
    // Fill API key
    const keyInput = screen.getByPlaceholderText("Enter API key");
    fireEvent.change(keyInput, { target: { value: "testkey123" } });
    // Fill API secret
    const secretInput = screen.getByPlaceholderText("Enter API secret");
    fireEvent.change(secretInput, { target: { value: "secret456" } });
    // Submit form
    const submitBtn = screen.getByText("Add Exchange");
    fireEvent.click(submitBtn);
    await waitFor(() => {
      const postCalls = fetchSpy.mock.calls.filter(
        (c: [RequestInfo | URL, RequestInit?]) =>
          typeof c[0] === "string" && c[0].includes("/api/exchange-configs") && c[1]?.method === "POST",
      );
      expect(postCalls.length).toBeGreaterThan(0);
    });
  });

  it("closes add form on successful create", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/exchange-configs": mockConfigs,
        "/api/data-sources": mockDataSources,
        "/api/notifications/preferences": mockNotifPrefs,
      }),
    );
    renderWithProviders(<Settings />);
    const addBtn = await screen.findByText("Add Exchange");
    fireEvent.click(addBtn);
    const nameInput = screen.getByPlaceholderText("e.g. Binance Main");
    fireEvent.change(nameInput, { target: { value: "New Exchange" } });
    const submitBtn = screen.getByText("Add Exchange");
    fireEvent.click(submitBtn);
    // After mutation succeeds, form should close
    await waitFor(() => {
      expect(screen.queryByPlaceholderText("e.g. Binance Main")).not.toBeInTheDocument();
    });
  });
});

describe("Settings - Update Exchange Mutation", () => {
  it("submits update form and triggers mutation", async () => {
    const fetchSpy = vi.fn(
      mockFetch({
        "/api/exchange-configs": mockConfigs,
        "/api/data-sources": mockDataSources,
        "/api/notifications/preferences": mockNotifPrefs,
      }),
    );
    vi.stubGlobal("fetch", fetchSpy);
    renderWithProviders(<Settings />);
    const editBtn = await screen.findByText("Edit");
    fireEvent.click(editBtn);
    // The form should be pre-filled; click Update
    const updateBtn = screen.getByText("Update");
    fireEvent.click(updateBtn);
    await waitFor(() => {
      const putCalls = fetchSpy.mock.calls.filter(
        (c: [RequestInfo | URL, RequestInit?]) =>
          typeof c[0] === "string" && c[0].includes("/api/exchange-configs/1") && c[1]?.method === "PUT",
      );
      expect(putCalls.length).toBeGreaterThan(0);
    });
  });

  it("closes edit form on successful update", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/exchange-configs": mockConfigs,
        "/api/data-sources": mockDataSources,
        "/api/notifications/preferences": mockNotifPrefs,
      }),
    );
    renderWithProviders(<Settings />);
    const editBtn = await screen.findByText("Edit");
    fireEvent.click(editBtn);
    const updateBtn = screen.getByText("Update");
    fireEvent.click(updateBtn);
    await waitFor(() => {
      expect(screen.queryByText("Update")).not.toBeInTheDocument();
    });
  });
});

describe("Settings - Delete Exchange Mutation", () => {
  it("triggers delete mutation on Confirm click", async () => {
    const fetchSpy = vi.fn(
      mockFetch({
        "/api/exchange-configs": mockConfigs,
        "/api/data-sources": mockDataSources,
        "/api/notifications/preferences": mockNotifPrefs,
      }),
    );
    vi.stubGlobal("fetch", fetchSpy);
    renderWithProviders(<Settings />);
    const deleteBtns = await screen.findAllByText("Delete");
    // Click Delete on exchange config card (first one)
    fireEvent.click(deleteBtns[0]);
    // Click Confirm
    fireEvent.click(screen.getByText("Confirm"));
    await waitFor(() => {
      const deleteCalls = fetchSpy.mock.calls.filter(
        (c: [RequestInfo | URL, RequestInit?]) =>
          typeof c[0] === "string" && c[0].includes("/api/exchange-configs/1") && c[1]?.method === "DELETE",
      );
      expect(deleteCalls.length).toBeGreaterThan(0);
    });
  });
});

describe("Settings - Test Connection Result", () => {
  it("shows success banner after successful test", async () => {
    // Custom fetch that handles /test/ URL before generic /exchange-configs
    const fetchFn = (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input.toString();
      if (url.includes("/test/") && init?.method === "POST") {
        return Promise.resolve(
          new Response(JSON.stringify({ success: true, message: "Connection successful!" }), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          }),
        );
      }
      return mockFetch({
        "/api/exchange-configs": mockConfigs,
        "/api/data-sources": mockDataSources,
        "/api/notifications/preferences": mockNotifPrefs,
      })(input, init);
    };
    vi.stubGlobal("fetch", fetchFn as typeof globalThis.fetch);
    renderWithProviders(<Settings />);
    const testBtn = await screen.findByText("Test");
    fireEvent.click(testBtn);
    expect(await screen.findByText("Connection successful!")).toBeInTheDocument();
    // Should also show dismiss button
    expect(screen.getByLabelText("Dismiss test result")).toBeInTheDocument();
  });

  it("shows failure banner after failed test", async () => {
    const fetchFn = (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input.toString();
      if (url.includes("/test/") && init?.method === "POST") {
        return Promise.resolve(
          new Response(JSON.stringify({ success: false, message: "Auth error" }), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          }),
        );
      }
      return mockFetch({
        "/api/exchange-configs": mockConfigs,
        "/api/data-sources": mockDataSources,
        "/api/notifications/preferences": mockNotifPrefs,
      })(input, init);
    };
    vi.stubGlobal("fetch", fetchFn as typeof globalThis.fetch);
    renderWithProviders(<Settings />);
    const testBtn = await screen.findByText("Test");
    fireEvent.click(testBtn);
    expect(await screen.findByText("Auth error")).toBeInTheDocument();
  });

  it("dismisses test result when dismiss is clicked", async () => {
    const fetchFn = (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input.toString();
      if (url.includes("/test/") && init?.method === "POST") {
        return Promise.resolve(
          new Response(JSON.stringify({ success: true, message: "All good" }), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          }),
        );
      }
      return mockFetch({
        "/api/exchange-configs": mockConfigs,
        "/api/data-sources": mockDataSources,
        "/api/notifications/preferences": mockNotifPrefs,
      })(input, init);
    };
    vi.stubGlobal("fetch", fetchFn as typeof globalThis.fetch);
    renderWithProviders(<Settings />);
    const testBtn = await screen.findByText("Test");
    fireEvent.click(testBtn);
    const msg = await screen.findByText("All good");
    expect(msg).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText("Dismiss test result"));
    expect(screen.queryByText("All good")).not.toBeInTheDocument();
  });

  it("shows failure banner when test mutation errors", async () => {
    // Make the test endpoint return a network error
    const fetchFn = (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input.toString();
      if (url.includes("/test/") && init?.method === "POST") {
        return Promise.reject(new Error("Network error"));
      }
      return mockFetch({
        "/api/exchange-configs": mockConfigs,
        "/api/data-sources": mockDataSources,
        "/api/notifications/preferences": mockNotifPrefs,
      })(input, init);
    };
    vi.stubGlobal("fetch", fetchFn as typeof globalThis.fetch);
    renderWithProviders(<Settings />);
    const testBtn = await screen.findByText("Test");
    fireEvent.click(testBtn);
    expect(await screen.findByText("Connection test failed")).toBeInTheDocument();
  });
});

describe("Settings - showSaved Banner", () => {
  it("shows saved banner after successful create", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/exchange-configs": mockConfigs,
        "/api/data-sources": mockDataSources,
        "/api/notifications/preferences": mockNotifPrefs,
      }),
    );
    renderWithProviders(<Settings />);
    const addBtn = await screen.findByText("Add Exchange");
    fireEvent.click(addBtn);
    const nameInput = screen.getByPlaceholderText("e.g. Binance Main");
    fireEvent.change(nameInput, { target: { value: "Test Exchange" } });
    fireEvent.click(screen.getByText("Add Exchange"));
    expect(
      await screen.findByText("Exchange configuration saved successfully."),
    ).toBeInTheDocument();
  });
});

describe("Settings - configsError Banner", () => {
  it("shows error banner when configs fail to load", async () => {
    const fetchFn = (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input.toString();
      if (url.includes("/api/exchange-configs")) {
        return Promise.resolve(
          new Response(JSON.stringify({ error: "fail" }), {
            status: 500,
            headers: { "Content-Type": "application/json" },
          }),
        );
      }
      return mockFetch({
        "/api/data-sources": mockDataSources,
        "/api/notifications/preferences": mockNotifPrefs,
      })(input, init);
    };
    vi.stubGlobal("fetch", fetchFn as typeof globalThis.fetch);
    renderWithProviders(<Settings />);
    expect(
      await screen.findByText("Failed to load exchange configurations."),
    ).toBeInTheDocument();
  });
});

describe("Settings - Notification Toggle Interactions", () => {
  function setupNotifMocks() {
    const fetchSpy = vi.fn(
      mockFetch({
        "/api/exchange-configs": mockConfigs,
        "/api/data-sources": mockDataSources,
        "/api/notifications/": mockNotifPrefs,
        "/api/portfolios": [{ id: 1, name: "Main" }],
      }),
    );
    vi.stubGlobal("fetch", fetchSpy);
    return fetchSpy;
  }

  it("toggles telegram_enabled via checkbox click", async () => {
    const fetchSpy = setupNotifMocks();
    renderWithProviders(<Settings />);
    // Wait for Telegram checkbox to appear
    const telegramLabel = await screen.findByText("Telegram");
    const checkbox = telegramLabel.parentElement!.querySelector("input[type=checkbox]")!;
    fireEvent.click(checkbox);
    await waitFor(() => {
      const putCalls = fetchSpy.mock.calls.filter(
        (c: [RequestInfo | URL, RequestInit?]) =>
          typeof c[0] === "string" && c[0].includes("/api/notifications/") && c[1]?.method === "PUT",
      );
      expect(putCalls.length).toBeGreaterThan(0);
    });
  });

  it("toggles webhook_enabled via checkbox change", async () => {
    const fetchSpy = setupNotifMocks();
    renderWithProviders(<Settings />);
    // Wait for prefs to load and Webhook checkbox to render
    await screen.findByText("Webhook");
    // The Webhook checkbox is inside a label element - find the checkbox within that label
    const allCheckboxes = document.querySelectorAll<HTMLInputElement>("input[type=checkbox]");
    // webhook_enabled is false in mockNotifPrefs, so find the unchecked channel checkbox
    // Telegram is checked (true), Webhook is unchecked (false)
    const webhookCheckbox = Array.from(allCheckboxes).find(
      (cb) => !cb.checked && cb.closest("label")?.textContent?.includes("Webhook"),
    )!;
    expect(webhookCheckbox).toBeTruthy();
    fireEvent.click(webhookCheckbox);
    await waitFor(() => {
      const putCalls = fetchSpy.mock.calls.filter(
        (c: [RequestInfo | URL, RequestInit?]) =>
          typeof c[0] === "string" && c[0].includes("/api/notifications/") && c[1]?.method === "PUT",
      );
      expect(putCalls.length).toBeGreaterThan(0);
    });
  });

  it("toggles event notification via toggle button", async () => {
    const fetchSpy = setupNotifMocks();
    renderWithProviders(<Settings />);
    // Wait for notification toggles to render
    await screen.findByText("Order Submitted");
    // The toggle buttons are inside the notification row divs
    // Find all toggle buttons (they have the rounded-full class)
    const allButtons = document.querySelectorAll("button.rounded-full");
    expect(allButtons.length).toBeGreaterThan(0);
    fireEvent.click(allButtons[0]);
    await waitFor(() => {
      const putCalls = fetchSpy.mock.calls.filter(
        (c: [RequestInfo | URL, RequestInit?]) =>
          typeof c[0] === "string" && c[0].includes("/api/notifications/") && c[1]?.method === "PUT",
      );
      expect(putCalls.length).toBeGreaterThan(0);
    });
  });
});

describe("Settings - Data Source Form", () => {
  function setupWithForm() {
    const fetchSpy = vi.fn(
      mockFetch({
        "/api/exchange-configs": mockConfigs,
        "/api/data-sources": mockDataSources,
        "/api/notifications/preferences": mockNotifPrefs,
      }),
    );
    vi.stubGlobal("fetch", fetchSpy);
    return fetchSpy;
  }

  it("opens data source form and shows exchange selector", async () => {
    setupWithForm();
    renderWithProviders(<Settings />);
    const addBtn = await screen.findByText("Add Data Source");
    fireEvent.click(addBtn);
    expect(screen.getByText("Symbols (comma-separated)")).toBeInTheDocument();
    expect(screen.getByText("Timeframes")).toBeInTheDocument();
    expect(screen.getByText("Fetch interval (minutes)")).toBeInTheDocument();
  });

  it("submits data source form", async () => {
    const fetchSpy = setupWithForm();
    renderWithProviders(<Settings />);
    const addBtn = await screen.findByText("Add Data Source");
    fireEvent.click(addBtn);
    // Fill symbols
    const symbolsInput = screen.getByPlaceholderText("BTC/USDT, ETH/USDT");
    fireEvent.change(symbolsInput, { target: { value: "SOL/USDT" } });
    // Submit
    const submitBtns = screen.getAllByText("Add Data Source");
    const submitBtn = submitBtns[submitBtns.length - 1]; // form submit button
    fireEvent.click(submitBtn);
    await waitFor(() => {
      const postCalls = fetchSpy.mock.calls.filter(
        (c: [RequestInfo | URL, RequestInit?]) =>
          typeof c[0] === "string" && c[0].includes("/api/data-sources") && c[1]?.method === "POST",
      );
      expect(postCalls.length).toBeGreaterThan(0);
    });
  });

  it("toggles timeframe buttons", async () => {
    setupWithForm();
    renderWithProviders(<Settings />);
    const addBtn = await screen.findByText("Add Data Source");
    fireEvent.click(addBtn);
    // 1h is selected by default, click 5m to add it
    const fiveMinBtn = screen.getByRole("button", { name: "5m" });
    fireEvent.click(fiveMinBtn);
    // 5m should now have the selected style (blue)
    expect(fiveMinBtn.className).toContain("bg-blue-600");
    // Click 1h to deselect it
    const oneHourBtn = screen.getByRole("button", { name: "1h" });
    fireEvent.click(oneHourBtn);
    expect(oneHourBtn.className).not.toContain("bg-blue-600");
  });

  it("changes fetch interval input", async () => {
    setupWithForm();
    renderWithProviders(<Settings />);
    const addBtn = await screen.findByText("Add Data Source");
    fireEvent.click(addBtn);
    const intervalInput = screen.getByDisplayValue("60");
    fireEvent.change(intervalInput, { target: { value: "30" } });
    expect(screen.getByDisplayValue("30")).toBeInTheDocument();
  });

  it("cancels data source form", async () => {
    setupWithForm();
    renderWithProviders(<Settings />);
    const addBtn = await screen.findByText("Add Data Source");
    fireEvent.click(addBtn);
    expect(screen.getByPlaceholderText("BTC/USDT, ETH/USDT")).toBeInTheDocument();
    const cancelBtns = screen.getAllByText("Cancel");
    fireEvent.click(cancelBtns[cancelBtns.length - 1]);
    expect(screen.queryByPlaceholderText("BTC/USDT, ETH/USDT")).not.toBeInTheDocument();
  });

  it("closes data source form on successful create", async () => {
    setupWithForm();
    renderWithProviders(<Settings />);
    const addBtn = await screen.findByText("Add Data Source");
    fireEvent.click(addBtn);
    const symbolsInput = screen.getByPlaceholderText("BTC/USDT, ETH/USDT");
    fireEvent.change(symbolsInput, { target: { value: "DOGE/USDT" } });
    const submitBtns = screen.getAllByText("Add Data Source");
    fireEvent.click(submitBtns[submitBtns.length - 1]);
    await waitFor(() => {
      expect(screen.queryByPlaceholderText("BTC/USDT, ETH/USDT")).not.toBeInTheDocument();
    });
  });
});

describe("Settings - Data Source Deletion", () => {
  it("triggers delete mutation for data source", async () => {
    const fetchSpy = vi.fn(
      mockFetch({
        "/api/exchange-configs": mockConfigs,
        "/api/data-sources": mockDataSources,
        "/api/notifications/preferences": mockNotifPrefs,
      }),
    );
    vi.stubGlobal("fetch", fetchSpy);
    renderWithProviders(<Settings />);
    // Wait for data sources to load, then click Delete on the data source card
    const deleteBtns = await screen.findAllByText("Delete");
    // Second Delete button should be on the data source card
    fireEvent.click(deleteBtns[1]);
    await waitFor(() => {
      const deleteCalls = fetchSpy.mock.calls.filter(
        (c: [RequestInfo | URL, RequestInit?]) =>
          typeof c[0] === "string" && c[0].includes("/api/data-sources/1") && c[1]?.method === "DELETE",
      );
      expect(deleteCalls.length).toBeGreaterThan(0);
    });
  });
});

describe("Settings - Audit Log Filter Interactions", () => {
  function setupAuditMocks() {
    const fetchSpy = vi.fn(
      mockFetch({
        "/api/exchange-configs": mockConfigs,
        "/api/data-sources": mockDataSources,
        "/api/notifications/preferences": mockNotifPrefs,
        "/api/audit-log": {
          results: [
            {
              id: 1,
              user: "admin",
              action: "GET /api/dashboard/",
              ip_address: "127.0.0.1",
              status_code: 200,
              created_at: "2026-03-01T10:00:00Z",
            },
          ],
          total: 1,
        },
      }),
    );
    vi.stubGlobal("fetch", fetchSpy);
    return fetchSpy;
  }

  it("changes user filter and resets page", async () => {
    const fetchSpy = setupAuditMocks();
    renderWithProviders(<Settings />);
    const userInput = await screen.findByPlaceholderText("Filter by user");
    fireEvent.change(userInput, { target: { value: "admin" } });
    await waitFor(() => {
      const auditCalls = fetchSpy.mock.calls.filter(
        (c: [RequestInfo | URL, RequestInit?]) =>
          typeof c[0] === "string" && c[0].includes("/api/audit-log"),
      );
      expect(auditCalls.length).toBeGreaterThan(1); // initial + after filter
    });
  });

  it("changes date filter and resets page", async () => {
    const fetchSpy = setupAuditMocks();
    renderWithProviders(<Settings />);
    await screen.findByPlaceholderText("Filter by user");
    const dateInputs = document.querySelectorAll("input[type='date']");
    expect(dateInputs.length).toBeGreaterThan(0);
    fireEvent.change(dateInputs[0], { target: { value: "2026-03-01" } });
    await waitFor(() => {
      const auditCalls = fetchSpy.mock.calls.filter(
        (c: [RequestInfo | URL, RequestInit?]) =>
          typeof c[0] === "string" && c[0].includes("/api/audit-log"),
      );
      expect(auditCalls.length).toBeGreaterThan(1);
    });
  });
});

describe("Settings - Audit Log Pagination", () => {
  it("renders pagination when total > page size", async () => {
    const manyEntries = Array.from({ length: 15 }, (_, i) => ({
      id: i + 1,
      user: `user${i}`,
      action: `GET /api/test/${i}`,
      ip_address: "127.0.0.1",
      status_code: 200,
      created_at: "2026-03-01T10:00:00Z",
    }));
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/exchange-configs": mockConfigs,
        "/api/data-sources": mockDataSources,
        "/api/notifications/preferences": mockNotifPrefs,
        "/api/audit-log": { results: manyEntries, total: 20 },
      }),
    );
    renderWithProviders(<Settings />);
    // Wait for audit entries to load
    await screen.findByText("user0");
    // Pagination shows "Next" button and page info
    expect(screen.getByText("Next")).toBeInTheDocument();
    expect(screen.getByText("Prev")).toBeInTheDocument();
  });

  it("shows audit entry with null ip_address as dash", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/exchange-configs": mockConfigs,
        "/api/data-sources": mockDataSources,
        "/api/notifications/preferences": mockNotifPrefs,
        "/api/audit-log": {
          results: [
            {
              id: 1,
              user: "system",
              action: "POST /api/cron/",
              ip_address: null,
              status_code: 200,
              created_at: "2026-03-01T10:00:00Z",
            },
          ],
          total: 1,
        },
      }),
    );
    renderWithProviders(<Settings />);
    const dash = await screen.findByText("\u2014");
    expect(dash).toBeInTheDocument();
  });

  it("shows warning-colored status code for 4xx", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/exchange-configs": mockConfigs,
        "/api/data-sources": mockDataSources,
        "/api/notifications/preferences": mockNotifPrefs,
        "/api/audit-log": {
          results: [
            {
              id: 1,
              user: "admin",
              action: "POST /api/test/",
              ip_address: "127.0.0.1",
              status_code: 403,
              created_at: "2026-03-01T10:00:00Z",
            },
          ],
          total: 1,
        },
      }),
    );
    renderWithProviders(<Settings />);
    const badge = await screen.findByText("403");
    expect(badge.className).toContain("text-yellow-400");
  });

  it("shows error-colored status code for 5xx", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/exchange-configs": mockConfigs,
        "/api/data-sources": mockDataSources,
        "/api/notifications/preferences": mockNotifPrefs,
        "/api/audit-log": {
          results: [
            {
              id: 1,
              user: "admin",
              action: "POST /api/test/",
              ip_address: "127.0.0.1",
              status_code: 500,
              created_at: "2026-03-01T10:00:00Z",
            },
          ],
          total: 1,
        },
      }),
    );
    renderWithProviders(<Settings />);
    const badge = await screen.findByText("500");
    expect(badge.className).toContain("text-red-400");
  });
});

describe("Settings - KuCoin Passphrase Field", () => {
  it("shows passphrase field when KuCoin is selected", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/exchange-configs": mockConfigs,
        "/api/data-sources": mockDataSources,
        "/api/notifications/preferences": mockNotifPrefs,
      }),
    );
    renderWithProviders(<Settings />);
    const addBtn = await screen.findByText("Add Exchange");
    fireEvent.click(addBtn);
    // Select KuCoin
    const selects = document.querySelectorAll("select");
    const exchangeSelect = selects[0]; // first select is exchange
    fireEvent.change(exchangeSelect, { target: { value: "kucoin" } });
    expect(screen.getByText("Passphrase")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("Enter passphrase")).toBeInTheDocument();
  });

  it("does not show passphrase field for non-KuCoin exchanges", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/exchange-configs": mockConfigs,
        "/api/data-sources": mockDataSources,
        "/api/notifications/preferences": mockNotifPrefs,
      }),
    );
    renderWithProviders(<Settings />);
    const addBtn = await screen.findByText("Add Exchange");
    fireEvent.click(addBtn);
    // Default is binance
    expect(screen.queryByText("Passphrase")).not.toBeInTheDocument();
  });

  it("includes passphrase in submit data when KuCoin selected", async () => {
    const fetchSpy = vi.fn(
      mockFetch({
        "/api/exchange-configs": mockConfigs,
        "/api/data-sources": mockDataSources,
        "/api/notifications/preferences": mockNotifPrefs,
      }),
    );
    vi.stubGlobal("fetch", fetchSpy);
    renderWithProviders(<Settings />);
    const addBtn = await screen.findByText("Add Exchange");
    fireEvent.click(addBtn);
    // Fill name
    fireEvent.change(screen.getByPlaceholderText("e.g. Binance Main"), {
      target: { value: "KuCoin Main" },
    });
    // Select KuCoin
    const selects = document.querySelectorAll("select");
    fireEvent.change(selects[0], { target: { value: "kucoin" } });
    // Fill passphrase
    fireEvent.change(screen.getByPlaceholderText("Enter passphrase"), {
      target: { value: "mypass" },
    });
    // Submit
    fireEvent.click(screen.getByText("Add Exchange"));
    await waitFor(() => {
      const postCalls = fetchSpy.mock.calls.filter(
        (c: [RequestInfo | URL, RequestInit?]) =>
          typeof c[0] === "string" && c[0].includes("/api/exchange-configs") && c[1]?.method === "POST",
      );
      expect(postCalls.length).toBeGreaterThan(0);
      const body = JSON.parse(postCalls[0][1]!.body as string);
      expect(body.passphrase).toBe("mypass");
      expect(body.exchange_id).toBe("kucoin");
    });
  });

  it("shows and hides passphrase via toggle button", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/exchange-configs": mockConfigs,
        "/api/data-sources": mockDataSources,
        "/api/notifications/preferences": mockNotifPrefs,
      }),
    );
    renderWithProviders(<Settings />);
    const addBtn = await screen.findByText("Add Exchange");
    fireEvent.click(addBtn);
    const selects = document.querySelectorAll("select");
    fireEvent.change(selects[0], { target: { value: "kucoin" } });
    const passInput = screen.getByPlaceholderText("Enter passphrase");
    expect(passInput).toHaveAttribute("type", "password");
    fireEvent.click(screen.getByLabelText("Show passphrase"));
    expect(passInput).toHaveAttribute("type", "text");
    fireEvent.click(screen.getByLabelText("Hide passphrase"));
    expect(passInput).toHaveAttribute("type", "password");
  });
});

describe("Settings - StatusDot with null error", () => {
  it("shows red dot with fallback 'Failed' title when last_test_error is null", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/exchange-configs": [
          { ...mockConfigs[0], last_test_success: false, last_test_error: null },
        ],
        "/api/data-sources": mockDataSources,
        "/api/notifications/preferences": mockNotifPrefs,
      }),
    );
    renderWithProviders(<Settings />);
    const dot = await screen.findByTitle("Failed");
    expect(dot).toBeInTheDocument();
    expect(dot.className).toContain("bg-red-500");
  });
});

describe("Settings - Inactive Data Source", () => {
  it("shows inactive badge when data source is not active", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/exchange-configs": mockConfigs,
        "/api/data-sources": [
          { ...mockDataSources[0], is_active: false },
        ],
        "/api/notifications/preferences": mockNotifPrefs,
      }),
    );
    renderWithProviders(<Settings />);
    expect(await screen.findByText("inactive")).toBeInTheDocument();
  });
});

describe("Settings - Data Source without last_fetched_at", () => {
  it("does not show Last: text when last_fetched_at is null", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/exchange-configs": mockConfigs,
        "/api/data-sources": [
          { ...mockDataSources[0], last_fetched_at: null },
        ],
        "/api/notifications/preferences": mockNotifPrefs,
      }),
    );
    renderWithProviders(<Settings />);
    await screen.findByText(/Every 60min/);
    expect(screen.queryByText(/Last:/)).not.toBeInTheDocument();
  });
});

describe("Settings - Exchange Form Show/Hide toggles", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/exchange-configs": mockConfigs,
        "/api/data-sources": mockDataSources,
        "/api/notifications/preferences": mockNotifPrefs,
      }),
    );
  });

  it("toggles API key visibility", async () => {
    renderWithProviders(<Settings />);
    const addBtn = await screen.findByText("Add Exchange");
    fireEvent.click(addBtn);
    const keyInput = screen.getByPlaceholderText("Enter API key");
    expect(keyInput).toHaveAttribute("type", "password");
    fireEvent.click(screen.getByLabelText("Show API key"));
    expect(keyInput).toHaveAttribute("type", "text");
    fireEvent.click(screen.getByLabelText("Hide API key"));
    expect(keyInput).toHaveAttribute("type", "password");
  });

  it("toggles API secret visibility", async () => {
    renderWithProviders(<Settings />);
    const addBtn = await screen.findByText("Add Exchange");
    fireEvent.click(addBtn);
    const secretInput = screen.getByPlaceholderText("Enter API secret");
    expect(secretInput).toHaveAttribute("type", "password");
    fireEvent.click(screen.getByLabelText("Show API secret"));
    expect(secretInput).toHaveAttribute("type", "text");
    fireEvent.click(screen.getByLabelText("Hide API secret"));
    expect(secretInput).toHaveAttribute("type", "password");
  });

  it("toggles sandbox and default checkboxes", async () => {
    renderWithProviders(<Settings />);
    const addBtn = await screen.findByText("Add Exchange");
    fireEvent.click(addBtn);
    const sandboxCheckbox = screen.getByRole("checkbox", { name: /sandbox/i });
    // Default is checked
    expect(sandboxCheckbox).toBeChecked();
    fireEvent.click(sandboxCheckbox);
    expect(sandboxCheckbox).not.toBeChecked();
    const defaultCheckbox = screen.getByRole("checkbox", { name: /default/i });
    expect(defaultCheckbox).not.toBeChecked();
    fireEvent.click(defaultCheckbox);
    expect(defaultCheckbox).toBeChecked();
  });
});

describe("Settings - Edit form with existing config", () => {
  it("pre-fills name from existing config", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/exchange-configs": mockConfigs,
        "/api/data-sources": mockDataSources,
        "/api/notifications/preferences": mockNotifPrefs,
      }),
    );
    renderWithProviders(<Settings />);
    const editBtn = await screen.findByText("Edit");
    fireEvent.click(editBtn);
    expect(screen.getByDisplayValue("Binance Main")).toBeInTheDocument();
  });

  it("shows masked key placeholder in edit form", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/exchange-configs": mockConfigs,
        "/api/data-sources": mockDataSources,
        "/api/notifications/preferences": mockNotifPrefs,
      }),
    );
    renderWithProviders(<Settings />);
    const editBtn = await screen.findByText("Edit");
    fireEvent.click(editBtn);
    expect(screen.getByPlaceholderText("abc...xyz")).toBeInTheDocument();
  });

  it("shows ******** placeholder for secret when has_api_secret", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/exchange-configs": mockConfigs,
        "/api/data-sources": mockDataSources,
        "/api/notifications/preferences": mockNotifPrefs,
      }),
    );
    renderWithProviders(<Settings />);
    const editBtn = await screen.findByText("Edit");
    fireEvent.click(editBtn);
    expect(screen.getByPlaceholderText("********")).toBeInTheDocument();
  });

  it("cancels edit form via Cancel button", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/exchange-configs": mockConfigs,
        "/api/data-sources": mockDataSources,
        "/api/notifications/preferences": mockNotifPrefs,
      }),
    );
    renderWithProviders(<Settings />);
    const editBtn = await screen.findByText("Edit");
    fireEvent.click(editBtn);
    expect(screen.getByText("Update")).toBeInTheDocument();
    const cancelBtns = screen.getAllByText("Cancel");
    fireEvent.click(cancelBtns[0]);
    expect(screen.queryByText("Update")).not.toBeInTheDocument();
  });
});

describe("Settings - Notification portfolio selector change", () => {
  it("changes portfolio selection and refetches prefs", async () => {
    const fetchSpy = vi.fn(
      mockFetch({
        "/api/exchange-configs": mockConfigs,
        "/api/data-sources": mockDataSources,
        "/api/notifications/preferences": mockNotifPrefs,
        "/api/portfolios": [
          { id: 1, name: "Main" },
          { id: 2, name: "Test" },
        ],
      }),
    );
    vi.stubGlobal("fetch", fetchSpy);
    renderWithProviders(<Settings />);
    await screen.findByText("Portfolio:");
    const portfolioSelect = screen.getByLabelText("Portfolio:");
    fireEvent.change(portfolioSelect, { target: { value: "2" } });
    await waitFor(() => {
      const prefCalls = fetchSpy.mock.calls.filter(
        (c: [RequestInfo | URL, RequestInit?]) =>
          typeof c[0] === "string" && c[0].includes("/api/notifications/2/preferences"),
      );
      expect(prefCalls.length).toBeGreaterThan(0);
    });
  });
});

describe("Settings - Mutation Error Paths", () => {
  function makeErrorFetch(errorPath: string) {
    return (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input.toString();
      if (url.includes(errorPath) && init?.method && init.method !== "GET") {
        return Promise.resolve(
          new Response(JSON.stringify({ error: "Server error" }), {
            status: 500,
            headers: { "Content-Type": "application/json" },
          }),
        );
      }
      return mockFetch({
        "/api/exchange-configs": mockConfigs,
        "/api/data-sources": mockDataSources,
        "/api/notifications/": mockNotifPrefs,
        "/api/portfolios": [{ id: 1, name: "Main" }],
      })(input, init);
    };
  }

  it("handles create exchange config error", async () => {
    vi.stubGlobal("fetch", makeErrorFetch("/api/exchange-configs/") as typeof globalThis.fetch);
    renderWithProviders(<Settings />);
    const addBtn = await screen.findByText("Add Exchange");
    fireEvent.click(addBtn);
    fireEvent.change(screen.getByPlaceholderText("e.g. Binance Main"), {
      target: { value: "Fail Exchange" },
    });
    fireEvent.click(screen.getByText("Add Exchange"));
    // Form should remain open on error (not closed by onSuccess)
    await waitFor(() => {
      expect(screen.getByPlaceholderText("e.g. Binance Main")).toBeInTheDocument();
    });
  });

  it("handles update exchange config error", async () => {
    vi.stubGlobal("fetch", makeErrorFetch("/api/exchange-configs/1") as typeof globalThis.fetch);
    renderWithProviders(<Settings />);
    const editBtn = await screen.findByText("Edit");
    fireEvent.click(editBtn);
    fireEvent.click(screen.getByText("Update"));
    // Form should remain open on error
    await waitFor(() => {
      expect(screen.getByText("Update")).toBeInTheDocument();
    });
  });

  it("handles delete exchange config error", async () => {
    vi.stubGlobal("fetch", makeErrorFetch("/api/exchange-configs/1") as typeof globalThis.fetch);
    renderWithProviders(<Settings />);
    const deleteBtns = await screen.findAllByText("Delete");
    fireEvent.click(deleteBtns[0]);
    fireEvent.click(screen.getByText("Confirm"));
    // After error, Confirm should eventually disappear but delete wasn't successful
    await waitFor(() => {
      // The deletingId state remains since onSuccess didn't fire to clear it
      expect(screen.getByText("Confirm")).toBeInTheDocument();
    });
  });

  it("handles create data source error", async () => {
    vi.stubGlobal("fetch", makeErrorFetch("/api/data-sources/") as typeof globalThis.fetch);
    renderWithProviders(<Settings />);
    const addBtn = await screen.findByText("Add Data Source");
    fireEvent.click(addBtn);
    fireEvent.change(screen.getByPlaceholderText("BTC/USDT, ETH/USDT"), {
      target: { value: "SOL/USDT" },
    });
    const submitBtns = screen.getAllByText("Add Data Source");
    fireEvent.click(submitBtns[submitBtns.length - 1]);
    // Form should remain open on error
    await waitFor(() => {
      expect(screen.getByPlaceholderText("BTC/USDT, ETH/USDT")).toBeInTheDocument();
    });
  });

  it("handles delete data source error", async () => {
    // Custom fetch: DELETE on /data-sources/ returns 500, everything else normal
    const fetchFn = (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input.toString();
      if (url.includes("/api/data-sources/") && init?.method === "DELETE") {
        return Promise.resolve(
          new Response(JSON.stringify({ error: "Server error" }), {
            status: 500,
            headers: { "Content-Type": "application/json" },
          }),
        );
      }
      return mockFetch({
        "/api/exchange-configs": mockConfigs,
        "/api/data-sources": mockDataSources,
        "/api/notifications/": mockNotifPrefs,
        "/api/portfolios": [{ id: 1, name: "Main" }],
      })(input, init);
    };
    vi.stubGlobal("fetch", fetchFn as typeof globalThis.fetch);
    renderWithProviders(<Settings />);
    const deleteBtns = await screen.findAllByText("Delete");
    // Second delete is for data source
    fireEvent.click(deleteBtns[1]);
    // The mutation fires and errors, data source remains
    await waitFor(() => {
      expect(screen.getByText("BTC/USDT")).toBeInTheDocument();
    });
  });

  it("handles notification update error", async () => {
    vi.stubGlobal("fetch", makeErrorFetch("/api/notifications/") as typeof globalThis.fetch);
    renderWithProviders(<Settings />);
    const telegramLabel = await screen.findByText("Telegram");
    const checkbox = telegramLabel.parentElement!.querySelector("input[type=checkbox]")!;
    fireEvent.click(checkbox);
    // Mutation fires and errors, but UI remains functional
    await waitFor(() => {
      expect(screen.getByText("Telegram")).toBeInTheDocument();
    });
  });
});

describe("Settings - Data Source exchange selector in form", () => {
  it("changes exchange selection in data source form", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/exchange-configs": [
          mockConfigs[0],
          { ...mockConfigs[0], id: 2, name: "Kraken Main", exchange_id: "kraken" },
        ],
        "/api/data-sources": mockDataSources,
        "/api/notifications/preferences": mockNotifPrefs,
      }),
    );
    renderWithProviders(<Settings />);
    const addBtn = await screen.findByText("Add Data Source");
    fireEvent.click(addBtn);
    // The DS form exchange selector should list both exchanges
    const dsSelect = screen.getByDisplayValue("Binance Main");
    fireEvent.change(dsSelect, { target: { value: "2" } });
    expect(screen.getByDisplayValue("Kraken Main")).toBeInTheDocument();
  });
});
