import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  exchangeConfigsApi,
  dataSourcesApi,
} from "../api/exchangeConfigs";
import { auditApi } from "../api/audit";
import { notificationsApi } from "../api/notifications";
import { portfoliosApi } from "../api/portfolios";
import { useToast } from "../hooks/useToast";
import { ErrorBoundary } from "../components/ErrorBoundary";
import { WidgetErrorFallback } from "../components/WidgetErrorFallback";
import { Pagination } from "../components/Pagination";
import { getErrorMessage } from "../utils/errors";
import type {
  AuditLogEntry,
  ExchangeConfig,
  ExchangeConfigCreate,
  DataSourceConfig,
  DataSourceConfigCreate,
  ExchangeTestResult,
  NotificationPreferences,
  Portfolio,
} from "../types";

const EXCHANGE_OPTIONS = [
  { id: "binance", label: "Binance" },
  { id: "coinbase", label: "Coinbase" },
  { id: "kraken", label: "Kraken" },
  { id: "kucoin", label: "KuCoin" },
  { id: "bybit", label: "Bybit" },
  { id: "yfinance", label: "Yahoo Finance" },
];

const TIMEFRAME_OPTIONS = ["1m", "5m", "15m", "1h", "4h", "1d"];

function StatusDot({ config }: { config: ExchangeConfig }) {
  if (config.last_test_success === null) {
    return <span className="inline-block h-2.5 w-2.5 rounded-full bg-gray-400" title="Not tested" />;
  }
  return config.last_test_success ? (
    <span className="inline-block h-2.5 w-2.5 rounded-full bg-green-500" title="Connected" />
  ) : (
    <span className="inline-block h-2.5 w-2.5 rounded-full bg-red-500" title={config.last_test_error || "Failed"} />
  );
}

function ExchangeForm({
  initial,
  onSubmit,
  onCancel,
  isSubmitting,
}: {
  initial?: ExchangeConfig;
  onSubmit: (data: ExchangeConfigCreate) => void;
  onCancel: () => void;
  isSubmitting: boolean;
}) {
  const [name, setName] = useState(initial?.name ?? "");
  const [exchangeId, setExchangeId] = useState(initial?.exchange_id ?? "binance");
  const [apiKey, setApiKey] = useState("");
  const [apiSecret, setApiSecret] = useState("");
  const [passphrase, setPassphrase] = useState("");
  const [isSandbox, setIsSandbox] = useState(initial?.is_sandbox ?? true);
  const [isDefault, setIsDefault] = useState(initial?.is_default ?? false);
  const [showKey, setShowKey] = useState(false);
  const [showSecret, setShowSecret] = useState(false);
  const [showPass, setShowPass] = useState(false);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const data: ExchangeConfigCreate = {
      name,
      exchange_id: exchangeId,
      is_sandbox: isSandbox,
      is_default: isDefault,
    };
    if (apiKey) data.api_key = apiKey;
    if (apiSecret) data.api_secret = apiSecret;
    if (passphrase) data.passphrase = passphrase;
    onSubmit(data);
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="mb-1 block text-sm font-medium">Name</label>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
            placeholder="e.g. Binance Main"
            className="w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-2 text-sm"
          />
        </div>
        <div>
          <label className="mb-1 block text-sm font-medium">Exchange</label>
          <select
            value={exchangeId}
            onChange={(e) => setExchangeId(e.target.value)}
            className="w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-2 text-sm"
          >
            {EXCHANGE_OPTIONS.map((ex) => (
              <option key={ex.id} value={ex.id}>{ex.label}</option>
            ))}
          </select>
        </div>
      </div>

      <div>
        <label className="mb-1 block text-sm font-medium">API Key</label>
        <div className="flex gap-2">
          <input
            type={showKey ? "text" : "password"}
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            placeholder={initial?.api_key_masked || "Enter API key"}
            className="flex-1 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-2 text-sm font-mono"
          />
          <button
            type="button"
            onClick={() => setShowKey(!showKey)}
            aria-label={showKey ? "Hide API key" : "Show API key"}
            className="rounded-lg border border-[var(--color-border)] px-3 py-2 text-xs"
          >
            {showKey ? "Hide" : "Show"}
          </button>
        </div>
      </div>

      <div>
        <label className="mb-1 block text-sm font-medium">API Secret</label>
        <div className="flex gap-2">
          <input
            type={showSecret ? "text" : "password"}
            value={apiSecret}
            onChange={(e) => setApiSecret(e.target.value)}
            placeholder={initial?.has_api_secret ? "********" : "Enter API secret"}
            className="flex-1 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-2 text-sm font-mono"
          />
          <button
            type="button"
            onClick={() => setShowSecret(!showSecret)}
            aria-label={showSecret ? "Hide API secret" : "Show API secret"}
            className="rounded-lg border border-[var(--color-border)] px-3 py-2 text-xs"
          >
            {showSecret ? "Hide" : "Show"}
          </button>
        </div>
      </div>

      {exchangeId === "kucoin" && (
        <div>
          <label className="mb-1 block text-sm font-medium">Passphrase</label>
          <div className="flex gap-2">
            <input
              type={showPass ? "text" : "password"}
              value={passphrase}
              onChange={(e) => setPassphrase(e.target.value)}
              placeholder={initial?.has_passphrase ? "********" : "Enter passphrase"}
              className="flex-1 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-2 text-sm font-mono"
            />
            <button
              type="button"
              onClick={() => setShowPass(!showPass)}
              aria-label={showPass ? "Hide passphrase" : "Show passphrase"}
              className="rounded-lg border border-[var(--color-border)] px-3 py-2 text-xs"
            >
              {showPass ? "Hide" : "Show"}
            </button>
          </div>
        </div>
      )}

      <div className="flex gap-4">
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={isSandbox}
            onChange={(e) => setIsSandbox(e.target.checked)}
          />
          Sandbox mode
        </label>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={isDefault}
            onChange={(e) => setIsDefault(e.target.checked)}
          />
          Set as default
        </label>
      </div>

      <div className="flex gap-2">
        <button
          type="submit"
          disabled={isSubmitting}
          className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
        >
          {isSubmitting ? "Saving..." : initial ? "Update" : "Add Exchange"}
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="rounded-lg border border-[var(--color-border)] px-4 py-2 text-sm"
        >
          Cancel
        </button>
      </div>
    </form>
  );
}

function DataSourceForm({
  exchanges,
  onSubmit,
  onCancel,
  isSubmitting,
}: {
  exchanges: ExchangeConfig[];
  onSubmit: (data: DataSourceConfigCreate) => void;
  onCancel: () => void;
  isSubmitting: boolean;
}) {
  const [exchangeConfigId, setExchangeConfigId] = useState(exchanges[0]?.id ?? 0);
  const [symbolsText, setSymbolsText] = useState("");
  const [selectedTimeframes, setSelectedTimeframes] = useState<string[]>(["1h"]);
  const [fetchInterval, setFetchInterval] = useState(60);

  const toggleTimeframe = (tf: string) => {
    setSelectedTimeframes((prev) =>
      prev.includes(tf) ? prev.filter((t) => t !== tf) : [...prev, tf],
    );
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const symbols = symbolsText
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    onSubmit({
      exchange_config: exchangeConfigId,
      symbols,
      timeframes: selectedTimeframes,
      fetch_interval_minutes: fetchInterval,
    });
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div>
        <label className="mb-1 block text-sm font-medium">Exchange</label>
        <select
          value={exchangeConfigId}
          onChange={(e) => setExchangeConfigId(Number(e.target.value))}
          className="w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-2 text-sm"
        >
          {exchanges.map((ex) => (
            <option key={ex.id} value={ex.id}>{ex.name}</option>
          ))}
        </select>
      </div>

      <div>
        <label className="mb-1 block text-sm font-medium">
          Symbols (comma-separated)
        </label>
        <input
          type="text"
          value={symbolsText}
          onChange={(e) => setSymbolsText(e.target.value)}
          required
          placeholder="BTC/USDT, ETH/USDT"
          className="w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-2 text-sm font-mono"
        />
      </div>

      <div>
        <label className="mb-1 block text-sm font-medium">Timeframes</label>
        <div className="flex flex-wrap gap-2">
          {TIMEFRAME_OPTIONS.map((tf) => (
            <button
              key={tf}
              type="button"
              onClick={() => toggleTimeframe(tf)}
              className={`rounded-lg border px-3 py-1 text-sm ${
                selectedTimeframes.includes(tf)
                  ? "border-blue-500 bg-blue-600 text-white"
                  : "border-[var(--color-border)] bg-[var(--color-bg)]"
              }`}
            >
              {tf}
            </button>
          ))}
        </div>
      </div>

      <div>
        <label className="mb-1 block text-sm font-medium">
          Fetch interval (minutes)
        </label>
        <input
          type="number"
          value={fetchInterval}
          onChange={(e) => setFetchInterval(Number(e.target.value))}
          min={1}
          className="w-32 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-2 text-sm"
        />
      </div>

      <div className="flex gap-2">
        <button
          type="submit"
          disabled={isSubmitting}
          className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
        >
          {isSubmitting ? "Saving..." : "Add Data Source"}
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="rounded-lg border border-[var(--color-border)] px-4 py-2 text-sm"
        >
          Cancel
        </button>
      </div>
    </form>
  );
}

export function Settings() {
  const queryClient = useQueryClient();
  const { toast } = useToast();

  useEffect(() => { document.title = "Settings | A1SI-AITP"; }, []);

  // Exchange configs
  const { data: configs, isError: configsError } = useQuery({
    queryKey: ["exchange-configs"],
    queryFn: exchangeConfigsApi.list,
  });

  // Data sources
  const { data: dataSources } = useQuery({
    queryKey: ["data-sources"],
    queryFn: dataSourcesApi.list,
  });

  const [showAddExchange, setShowAddExchange] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [showAddDataSource, setShowAddDataSource] = useState(false);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [testingId, setTestingId] = useState<number | null>(null);
  const [testResult, setTestResult] = useState<ExchangeTestResult | null>(null);
  const [showSaved, setShowSaved] = useState(false);

  useEffect(() => {
    if (!showSaved) return;
    const timer = setTimeout(() => setShowSaved(false), 3000);
    return () => clearTimeout(timer);
  }, [showSaved]);

  const createMutation = useMutation({
    mutationFn: exchangeConfigsApi.create,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["exchange-configs"] });
      setShowAddExchange(false);
      setShowSaved(true);
      toast("Exchange config created", "success");
    },
    onError: (err) => toast(getErrorMessage(err) || "Failed to create exchange config", "error"),
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<ExchangeConfigCreate> }) =>
      exchangeConfigsApi.update(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["exchange-configs"] });
      setEditingId(null);
      setShowSaved(true);
      toast("Exchange config updated", "success");
    },
    onError: (err) => toast(getErrorMessage(err) || "Failed to update exchange config", "error"),
  });

  const deleteMutation = useMutation({
    mutationFn: exchangeConfigsApi.delete,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["exchange-configs"] });
      queryClient.invalidateQueries({ queryKey: ["data-sources"] });
      setDeletingId(null);
      toast("Exchange config deleted", "info");
    },
    onError: (err) => toast(getErrorMessage(err) || "Failed to delete exchange config", "error"),
  });

  const testMutation = useMutation({
    mutationFn: exchangeConfigsApi.test,
    onSuccess: (result) => {
      setTestResult(result);
      queryClient.invalidateQueries({ queryKey: ["exchange-configs"] });
    },
    onError: () => {
      setTestResult({ success: false, message: "Connection test failed" });
      queryClient.invalidateQueries({ queryKey: ["exchange-configs"] });
    },
    onSettled: () => setTestingId(null),
  });

  const createDSMutation = useMutation({
    mutationFn: dataSourcesApi.create,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["data-sources"] });
      setShowAddDataSource(false);
      toast("Data source created", "success");
    },
    onError: (err) => toast(getErrorMessage(err) || "Failed to create data source", "error"),
  });

  const deleteDSMutation = useMutation({
    mutationFn: dataSourcesApi.delete,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["data-sources"] });
      toast("Data source deleted", "info");
    },
    onError: (err) => toast(getErrorMessage(err) || "Failed to delete data source", "error"),
  });

  const handleTest = (id: number) => {
    setTestingId(id);
    setTestResult(null);
    testMutation.mutate(id);
  };

  return (
    <div>
      <section aria-labelledby="page-heading">
      <h2 id="page-heading" className="mb-6 text-2xl font-bold">Settings</h2>

      {configsError && (
        <div className="mb-4 max-w-2xl rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-400">
          Failed to load exchange configurations.
        </div>
      )}

      {showSaved && (
        <div className="mb-4 max-w-2xl rounded-lg border border-green-500/30 bg-green-500/10 p-3 text-sm text-green-400">
          Exchange configuration saved successfully.
        </div>
      )}

      <ErrorBoundary fallback={<WidgetErrorFallback name="Settings" />}>
      <div className="max-w-2xl space-y-6">
        {/* Exchange Connections */}
        <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
          <div className="mb-4 flex items-center justify-between">
            <h3 className="text-lg font-semibold">Exchange Connections</h3>
            {!showAddExchange && editingId === null && (
              <button
                onClick={() => setShowAddExchange(true)}
                className="rounded-lg bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-700"
              >
                Add Exchange
              </button>
            )}
          </div>

          <p className="mb-4 text-sm text-[var(--color-text-muted)]">
            Manage API keys for exchange connections. Credentials are encrypted
            at rest and never displayed in plaintext.
          </p>

          {/* Test result banner */}
          {testResult && (
            <div
              className={`mb-4 rounded-lg p-3 text-sm ${
                testResult.success
                  ? "border border-green-700 bg-green-900/30 text-green-300"
                  : "border border-red-700 bg-red-900/30 text-red-300"
              }`}
            >
              {testResult.message}
              <button
                onClick={() => setTestResult(null)}
                aria-label="Dismiss test result"
                className="ml-2 text-xs opacity-70 hover:opacity-100"
              >
                dismiss
              </button>
            </div>
          )}

          {/* Config cards */}
          {configs && configs.length > 0 && (
            <div className="mb-4 space-y-2">
              {configs.map((config) =>
                editingId === config.id ? (
                  <div
                    key={config.id}
                    className="rounded-lg border border-blue-500/50 bg-[var(--color-bg)] p-4"
                  >
                    <ExchangeForm
                      initial={config}
                      onSubmit={(data) =>
                        updateMutation.mutate({ id: config.id, data })
                      }
                      onCancel={() => setEditingId(null)}
                      isSubmitting={updateMutation.isPending}
                    />
                  </div>
                ) : (
                  <div
                    key={config.id}
                    className="flex items-center justify-between rounded-lg border border-[var(--color-border)] p-3"
                  >
                    <div className="flex items-center gap-3">
                      <StatusDot config={config} />
                      <div>
                        <div className="flex items-center gap-2">
                          <p className="font-medium">{config.name}</p>
                          <span className="rounded bg-[var(--color-bg)] px-1.5 py-0.5 text-xs text-[var(--color-text-muted)]">
                            {config.exchange_id}
                          </span>
                          {config.is_sandbox && (
                            <span className="rounded bg-yellow-800/40 px-1.5 py-0.5 text-xs text-yellow-400">
                              sandbox
                            </span>
                          )}
                          {!config.is_sandbox && (
                            <span className="rounded bg-green-800/40 px-1.5 py-0.5 text-xs text-green-400">
                              live
                            </span>
                          )}
                          {config.is_default && (
                            <span className="rounded bg-blue-800/40 px-1.5 py-0.5 text-xs text-blue-400">
                              default
                            </span>
                          )}
                        </div>
                        {config.api_key_masked && (
                          <p className="mt-0.5 font-mono text-xs text-[var(--color-text-muted)]">
                            Key: {config.api_key_masked}
                          </p>
                        )}
                      </div>
                    </div>
                    <div className="flex gap-1">
                      <button
                        onClick={() => handleTest(config.id)}
                        disabled={testingId === config.id}
                        className="rounded-lg border border-[var(--color-border)] px-2.5 py-1 text-xs hover:bg-[var(--color-bg)] disabled:opacity-50"
                      >
                        {testingId === config.id ? "Testing..." : "Test"}
                      </button>
                      <button
                        onClick={() => setEditingId(config.id)}
                        className="rounded-lg border border-[var(--color-border)] px-2.5 py-1 text-xs hover:bg-[var(--color-bg)]"
                      >
                        Edit
                      </button>
                      {deletingId === config.id ? (
                        <span className="flex gap-1">
                          <button
                            onClick={() => deleteMutation.mutate(config.id)}
                            className="rounded-lg bg-red-600 px-2.5 py-1 text-xs text-white hover:bg-red-700"
                          >
                            Confirm
                          </button>
                          <button
                            onClick={() => setDeletingId(null)}
                            className="rounded-lg border border-[var(--color-border)] px-2.5 py-1 text-xs"
                          >
                            No
                          </button>
                        </span>
                      ) : (
                        <button
                          onClick={() => setDeletingId(config.id)}
                          className="rounded-lg border border-red-700 px-2.5 py-1 text-xs text-red-400 hover:bg-red-900/30"
                        >
                          Delete
                        </button>
                      )}
                    </div>
                  </div>
                ),
              )}
            </div>
          )}

          {configs && configs.length === 0 && !showAddExchange && (
            <p className="mb-4 text-sm text-[var(--color-text-muted)]">
              No exchange connections configured. Click &quot;Add Exchange&quot; to get
              started.
            </p>
          )}

          {/* Add form */}
          {showAddExchange && (
            <div className="rounded-lg border border-blue-500/50 bg-[var(--color-bg)] p-4">
              <ExchangeForm
                onSubmit={(data) => createMutation.mutate(data)}
                onCancel={() => setShowAddExchange(false)}
                isSubmitting={createMutation.isPending}
              />
            </div>
          )}
        </div>

        {/* Data Sources */}
        <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
          <div className="mb-4 flex items-center justify-between">
            <h3 className="text-lg font-semibold">Data Sources</h3>
            {!showAddDataSource && configs && configs.length > 0 && (
              <button
                onClick={() => setShowAddDataSource(true)}
                className="rounded-lg bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-700"
              >
                Add Data Source
              </button>
            )}
          </div>

          <p className="mb-4 text-sm text-[var(--color-text-muted)]">
            Configure which symbols and timeframes to fetch from each exchange.
          </p>

          {dataSources && dataSources.length > 0 && (
            <div className="mb-4 space-y-2">
              {dataSources.map((ds: DataSourceConfig) => (
                <div
                  key={ds.id}
                  className="flex items-center justify-between rounded-lg border border-[var(--color-border)] p-3"
                >
                  <div>
                    <div className="flex items-center gap-2">
                      <p className="font-medium">{ds.exchange_name}</p>
                      {!ds.is_active && (
                        <span className="rounded bg-gray-700 px-1.5 py-0.5 text-xs text-gray-400">
                          inactive
                        </span>
                      )}
                    </div>
                    <div className="mt-1 flex flex-wrap gap-1">
                      {ds.symbols.map((s) => (
                        <span
                          key={s}
                          className="rounded bg-[var(--color-bg)] px-1.5 py-0.5 text-xs font-mono"
                        >
                          {s}
                        </span>
                      ))}
                      <span className="text-xs text-[var(--color-text-muted)]">|</span>
                      {ds.timeframes.map((tf) => (
                        <span
                          key={tf}
                          className="rounded bg-blue-900/30 px-1.5 py-0.5 text-xs text-blue-300"
                        >
                          {tf}
                        </span>
                      ))}
                    </div>
                    <p className="mt-0.5 text-xs text-[var(--color-text-muted)]">
                      Every {ds.fetch_interval_minutes}min
                      {ds.last_fetched_at &&
                        ` | Last: ${new Date(ds.last_fetched_at).toLocaleString()}`}
                    </p>
                  </div>
                  <button
                    onClick={() => deleteDSMutation.mutate(ds.id)}
                    className="rounded-lg border border-red-700 px-2.5 py-1 text-xs text-red-400 hover:bg-red-900/30"
                  >
                    Delete
                  </button>
                </div>
              ))}
            </div>
          )}

          {showAddDataSource && configs && (
            <div className="rounded-lg border border-blue-500/50 bg-[var(--color-bg)] p-4">
              <DataSourceForm
                exchanges={configs}
                onSubmit={(data) => createDSMutation.mutate(data)}
                onCancel={() => setShowAddDataSource(false)}
                isSubmitting={createDSMutation.isPending}
              />
            </div>
          )}
        </div>

        {/* Notification Preferences */}
        <NotificationPreferencesSection />

        {/* Audit Log */}
        <AuditLogSection />

        {/* About */}
        <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
          <h3 className="mb-2 text-lg font-semibold">About</h3>
          <p className="text-sm text-[var(--color-text-muted)]">
            A1SI-AITP v0.1.0
          </p>
        </div>
      </div>
      </ErrorBoundary>
      </section>
    </div>
  );
}

const AUDIT_PAGE_SIZE = 15;

function AuditLogSection() {
  const [userFilter, setUserFilter] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [page, setPage] = useState(1);

  const params = {
    limit: AUDIT_PAGE_SIZE,
    offset: (page - 1) * AUDIT_PAGE_SIZE,
    ...(userFilter && { user: userFilter }),
    ...(dateFrom && { created_after: dateFrom }),
  };

  const { data } = useQuery({
    queryKey: ["audit-log", params],
    queryFn: () => auditApi.list(params),
  });

  return (
    <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
      <h3 className="mb-4 text-lg font-semibold">Audit Log</h3>
      <p className="mb-4 text-sm text-[var(--color-text-muted)]">
        Request history recorded by the audit middleware.
      </p>

      <div className="mb-4 flex gap-3">
        <input
          type="text"
          placeholder="Filter by user"
          value={userFilter}
          onChange={(e) => { setUserFilter(e.target.value); setPage(1); }}
          className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-1.5 text-sm"
        />
        <input
          type="date"
          value={dateFrom}
          onChange={(e) => { setDateFrom(e.target.value); setPage(1); }}
          className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-1.5 text-sm"
        />
      </div>

      {data?.results && data.results.length > 0 ? (
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-[var(--color-border)] text-[var(--color-text-muted)]">
                <th className="pb-2 text-left">Time</th>
                <th className="pb-2 text-left">User</th>
                <th className="pb-2 text-left">Action</th>
                <th className="pb-2 text-left">IP</th>
                <th className="pb-2 text-right">Status</th>
              </tr>
            </thead>
            <tbody>
              {data.results.map((entry: AuditLogEntry) => (
                <tr key={entry.id} className="border-b border-[var(--color-border)]/30">
                  <td className="py-1.5 text-[var(--color-text-muted)]">
                    {new Date(entry.created_at).toLocaleString()}
                  </td>
                  <td className="py-1.5">{entry.user}</td>
                  <td className="py-1.5 max-w-xs truncate font-mono">{entry.action}</td>
                  <td className="py-1.5 text-[var(--color-text-muted)]">{entry.ip_address ?? "—"}</td>
                  <td className="py-1.5 text-right">
                    <span
                      className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                        entry.status_code < 400
                          ? "bg-green-500/20 text-green-400"
                          : entry.status_code < 500
                            ? "bg-yellow-500/20 text-yellow-400"
                            : "bg-red-500/20 text-red-400"
                      }`}
                    >
                      {entry.status_code}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <Pagination page={page} pageSize={AUDIT_PAGE_SIZE} total={data.total} onPageChange={setPage} />
        </div>
      ) : (
        <p className="text-sm text-[var(--color-text-muted)]">
          No audit log entries found.
        </p>
      )}
    </div>
  );
}

const NOTIFICATION_TOGGLES: { key: keyof NotificationPreferences; label: string; description: string }[] = [
  { key: "on_order_submitted", label: "Order Submitted", description: "When a live order is placed on the exchange" },
  { key: "on_order_filled", label: "Order Filled", description: "When an order is completely filled" },
  { key: "on_order_cancelled", label: "Order Cancelled", description: "When an order is cancelled" },
  { key: "on_risk_halt", label: "Risk Halt/Resume", description: "When trading is halted or resumed" },
  { key: "on_trade_rejected", label: "Trade Rejected", description: "When a trade fails risk checks" },
  { key: "on_daily_summary", label: "Daily Summary", description: "Daily PnL and equity summary" },
];

function NotificationPreferencesSection() {
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const [portfolioId, setPortfolioId] = useState(1);

  const { data: portfolios } = useQuery<Portfolio[]>({
    queryKey: ["portfolios"],
    queryFn: () => portfoliosApi.list(),
  });

  const { data: prefs } = useQuery<NotificationPreferences>({
    queryKey: ["notification-prefs", portfolioId],
    queryFn: () => notificationsApi.getPreferences(portfolioId),
  });

  const notifUpdateMutation = useMutation({
    mutationFn: (updates: Partial<NotificationPreferences>) =>
      notificationsApi.updatePreferences(portfolioId, updates),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["notification-prefs", portfolioId] });
    },
    onError: (err) => toast(getErrorMessage(err) || "Failed to update notification preferences", "error"),
  });

  const toggle = (key: keyof NotificationPreferences) => {
    if (!prefs) return;
    notifUpdateMutation.mutate({ [key]: !prefs[key] });
  };

  return (
    <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h3 className="text-lg font-semibold">Notifications</h3>
          <p className="text-sm text-[var(--color-text-muted)]">
            Configure which events trigger notifications. Requires Telegram bot token
            and chat ID in environment variables.
          </p>
        </div>
        {portfolios && portfolios.length > 0 && (
          <div className="flex items-center gap-2">
            <label htmlFor="notif-portfolio" className="text-sm text-[var(--color-text-muted)]">Portfolio:</label>
            <select
              id="notif-portfolio"
              value={portfolioId}
              onChange={(e) => setPortfolioId(Number(e.target.value))}
              className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-2 py-1 text-sm"
            >
              {portfolios.map((p) => (
                <option key={p.id} value={p.id}>{p.name}</option>
              ))}
            </select>
          </div>
        )}
      </div>

      {prefs && (
        <div className="space-y-4">
          {/* Channel toggles */}
          <div className="flex gap-6">
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={prefs.telegram_enabled}
                onChange={() => toggle("telegram_enabled")}
                className="h-4 w-4 rounded border-gray-600 bg-gray-700"
              />
              Telegram
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={prefs.webhook_enabled}
                onChange={() => toggle("webhook_enabled")}
                className="h-4 w-4 rounded border-gray-600 bg-gray-700"
              />
              Webhook
            </label>
          </div>

          {/* Event toggles */}
          <div className="space-y-2">
            {NOTIFICATION_TOGGLES.map(({ key, label, description }) => (
              <div
                key={key}
                className="flex items-center justify-between rounded-lg border border-[var(--color-border)] px-3 py-2"
              >
                <div>
                  <p className="text-sm font-medium">{label}</p>
                  <p className="text-xs text-[var(--color-text-muted)]">{description}</p>
                </div>
                <button
                  onClick={() => toggle(key)}
                  className={`relative h-6 w-11 rounded-full transition-colors ${
                    prefs[key] ? "bg-blue-600" : "bg-gray-600"
                  }`}
                >
                  <span
                    className={`absolute top-0.5 h-5 w-5 rounded-full bg-white transition-transform ${
                      prefs[key] ? "translate-x-5" : "translate-x-0.5"
                    }`}
                  />
                </button>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
