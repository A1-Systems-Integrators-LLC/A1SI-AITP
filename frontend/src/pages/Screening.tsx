import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { screeningApi } from "../api/screening";
import { useJobPolling } from "../hooks/useJobPolling";
import { useToast } from "../hooks/useToast";
import { ProgressBar } from "../components/ProgressBar";

export function Screening() {
  const { toast } = useToast();
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [symbol, setSymbol] = useState("BTC/USDT");
  const [timeframe, setTimeframe] = useState("1h");
  const [exchange, setExchange] = useState("binance");
  const [fees, setFees] = useState(0.001);

  const { data: strategies } = useQuery({
    queryKey: ["screening-strategies"],
    queryFn: screeningApi.strategies,
  });

  const job = useJobPolling(activeJobId);

  const runMutation = useMutation({
    mutationFn: () => screeningApi.run({ symbol, timeframe, exchange, fees }),
    onSuccess: (data) => setActiveJobId(data.job_id),
    onError: (err) => toast((err as Error).message || "Failed to start screening", "error"),
  });

  const isJobActive = job.data?.status === "pending" || job.data?.status === "running";
  const jobResult = job.data?.result as Record<string, unknown> | undefined;
  const strategiesResult = (jobResult?.strategies ?? {}) as Record<string, Record<string, unknown>>;

  return (
    <div>
      <h2 className="mb-6 text-2xl font-bold">Strategy Screening</h2>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-4">
        {/* Config Form */}
        <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
          <h3 className="mb-4 text-lg font-semibold">Configuration</h3>
          <div className="space-y-3">
            <div>
              <label htmlFor="screen-symbol" className="mb-1 block text-xs text-[var(--color-text-muted)]">Symbol</label>
              <input
                id="screen-symbol"
                value={symbol}
                onChange={(e) => setSymbol(e.target.value)}
                className="w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-2 text-sm"
              />
            </div>
            <div>
              <label htmlFor="screen-timeframe" className="mb-1 block text-xs text-[var(--color-text-muted)]">Timeframe</label>
              <select
                id="screen-timeframe"
                value={timeframe}
                onChange={(e) => setTimeframe(e.target.value)}
                className="w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-2 text-sm"
              >
                {["1h", "4h", "1d"].map((tf) => (
                  <option key={tf} value={tf}>{tf}</option>
                ))}
              </select>
            </div>
            <div>
              <label htmlFor="screen-exchange" className="mb-1 block text-xs text-[var(--color-text-muted)]">Exchange</label>
              <select
                id="screen-exchange"
                value={exchange}
                onChange={(e) => setExchange(e.target.value)}
                className="w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-2 text-sm"
              >
                <option value="binance">Binance</option>
                <option value="sample">Sample</option>
              </select>
            </div>
            <div>
              <label htmlFor="screen-fees" className="mb-1 block text-xs text-[var(--color-text-muted)]">Fees (%)</label>
              <input
                id="screen-fees"
                type="number"
                step="0.01"
                value={fees * 100}
                onChange={(e) => setFees(Number(e.target.value) / 100)}
                className="w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-2 text-sm"
              />
            </div>
            <button
              onClick={() => runMutation.mutate()}
              disabled={isJobActive || runMutation.isPending}
              className="w-full rounded-lg bg-[var(--color-primary)] px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
            >
              {runMutation.isPending ? "Starting..." : "Run Screen"}
            </button>
          </div>

          {/* Strategy list */}
          {strategies && (
            <div className="mt-4 space-y-2">
              <h4 className="text-xs font-medium text-[var(--color-text-muted)]">Strategies</h4>
              {strategies.map((s) => (
                <div key={s.name} className="text-xs">
                  <span className="font-medium">{s.label}</span>
                  <span className="text-[var(--color-text-muted)]"> — {s.description}</span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Results area */}
        <div className="lg:col-span-3 space-y-4">
          {/* Job progress */}
          {activeJobId && job.data && (
            <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
              <div className="mb-2 flex items-center justify-between">
                <h3 className="text-sm font-medium">Screening Job</h3>
                <span
                  className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                    job.data.status === "completed"
                      ? "bg-green-500/20 text-green-400"
                      : job.data.status === "failed"
                        ? "bg-red-500/20 text-red-400"
                        : "bg-blue-500/20 text-blue-400"
                  }`}
                >
                  {job.data.status}
                </span>
              </div>
              {isJobActive && (
                <ProgressBar progress={job.data.progress} message={job.data.progress_message} />
              )}
              {job.data.status === "failed" && job.data.error && (
                <p className="mt-2 text-xs text-red-400">{job.data.error}</p>
              )}
            </div>
          )}

          {/* Results per strategy */}
          {job.data?.status === "completed" && Object.keys(strategiesResult).length > 0 && (
            <div className="space-y-4">
              {Object.entries(strategiesResult).map(([name, data]) => (
                <div
                  key={name}
                  className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4"
                >
                  <div className="mb-3 flex items-center justify-between">
                    <h3 className="font-semibold capitalize">{name.replace(/_/g, " ")}</h3>
                    {data.error ? (
                      <span className="text-xs text-red-400">{String(data.error)}</span>
                    ) : (
                      <span className="text-xs text-[var(--color-text-muted)]">
                        {String(data.total_combinations ?? 0)} combinations
                      </span>
                    )}
                  </div>
                  {!data.error && Array.isArray(data.top_results) && data.top_results.length > 0 && (
                    <div className="overflow-x-auto">
                      <table className="w-full text-left text-xs">
                        <thead>
                          <tr className="border-b border-[var(--color-border)] text-[var(--color-text-muted)]">
                            {Object.keys(data.top_results[0] as Record<string, unknown>).map((col) => (
                              <th key={col} className="pb-2 pr-3">{col}</th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {data.top_results.map((row: Record<string, unknown>, i: number) => (
                            <tr
                              key={i}
                              className="border-b border-[var(--color-border)] last:border-0"
                            >
                              {Object.values(row).map((val, j) => (
                                <td key={j} className="py-1.5 pr-3">
                                  {typeof val === "number" ? val.toFixed(4) : String(val)}
                                </td>
                              ))}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}

          {!activeJobId && (
            <div className="flex h-64 items-center justify-center rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)]">
              <p className="text-sm text-[var(--color-text-muted)]">
                Configure parameters and run a screen to see results.
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
