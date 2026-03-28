import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { exchangeConfigsApi } from "../../api/exchangeConfigs";
import { useToast } from "../../hooks/useToast";
import { getErrorMessage } from "../../utils/errors";
import type {
  ExchangeConfig,
  ExchangeConfigCreate,
  ExchangeTestResult,
} from "../../types";

const EXCHANGE_OPTIONS = [
  { id: "binance", label: "Binance" },
  { id: "coinbase", label: "Coinbase" },
  { id: "kraken", label: "Kraken" },
  { id: "kucoin", label: "KuCoin" },
  { id: "bybit", label: "Bybit" },
  { id: "yfinance", label: "Yahoo Finance" },
];

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
  const [exchangeId, setExchangeId] = useState(initial?.exchange_id ?? "kraken");
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

export function ExchangeConfigSection() {
  const queryClient = useQueryClient();
  const { toast } = useToast();

  const { data: configs, isError: configsError } = useQuery({
    queryKey: ["exchange-configs"],
    queryFn: exchangeConfigsApi.list,
  });

  const [showAddExchange, setShowAddExchange] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
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

  const handleTest = (id: number) => {
    setTestingId(id);
    setTestResult(null);
    testMutation.mutate(id);
  };

  return (
    <>
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
    </>
  );
}
