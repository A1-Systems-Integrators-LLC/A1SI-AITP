import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { dataApi } from "../api/data";
import { useJobPolling } from "../hooks/useJobPolling";
import { useToast } from "../hooks/useToast";
import { useAssetClass } from "../hooks/useAssetClass";
import { ProgressBar } from "../components/ProgressBar";
import { QueryError } from "../components/QueryError";
import {
  DEFAULT_SYMBOLS as DEFAULT_SYMBOLS_MAP,
  EXCHANGE_OPTIONS,
  TIMEFRAME_OPTIONS,
} from "../constants/assetDefaults";
import type { DataFileInfo, DataQualityResponse } from "../types";

export function DataManagement() {
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const { assetClass } = useAssetClass();

  const defaultSymbols = DEFAULT_SYMBOLS_MAP[assetClass];
  const timeframes = TIMEFRAME_OPTIONS[assetClass].map((tf) => tf.value);

  useEffect(() => { document.title = "Data Management | A1SI-AITP"; }, []);
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [downloadSymbols, setDownloadSymbols] = useState(defaultSymbols.join(", "));
  const [downloadTimeframes, setDownloadTimeframes] = useState(["1h"]);
  const [downloadExchange, setDownloadExchange] = useState(EXCHANGE_OPTIONS[assetClass][0]?.value ?? "binance");
  const [downloadDays, setDownloadDays] = useState(90);

  const { data: files, isLoading, isError: filesError } = useQuery<DataFileInfo[]>({
    queryKey: ["data-files", assetClass],
    queryFn: () => dataApi.list(assetClass),
  });

  const job = useJobPolling(activeJobId);

  // Refetch file list when job completes
  if (job.data?.status === "completed" || job.data?.status === "failed") {
    if (activeJobId) {
      queryClient.invalidateQueries({ queryKey: ["data-files"] });
    }
  }

  const downloadMutation = useMutation({
    mutationFn: () =>
      dataApi.download({
        symbols: downloadSymbols.split(",").map((s) => s.trim()),
        timeframes: downloadTimeframes,
        exchange: downloadExchange,
        since_days: downloadDays,
        asset_class: assetClass,
      }),
    onSuccess: (data) => setActiveJobId(data.job_id),
    onError: (err) => toast((err as Error).message || "Failed to start download", "error"),
  });

  const sampleMutation = useMutation({
    mutationFn: () =>
      dataApi.generateSample({
        symbols: defaultSymbols.slice(0, 3),
        timeframes: ["1h", "4h"],
        days: 90,
      }),
    onSuccess: (data) => setActiveJobId(data.job_id),
    onError: (err) => toast((err as Error).message || "Failed to generate sample data", "error"),
  });

  const tfToggle = (tf: string) => {
    setDownloadTimeframes((prev) =>
      prev.includes(tf) ? prev.filter((t) => t !== tf) : [...prev, tf],
    );
  };

  const [showQuality, setShowQuality] = useState(false);

  const qualityQuery = useQuery<DataQualityResponse>({
    queryKey: ["data-quality"],
    queryFn: dataApi.quality,
    enabled: showQuality,
  });

  const isJobActive = job.data?.status === "pending" || job.data?.status === "running";

  return (
    <div>
      <h2 className="mb-6 text-2xl font-bold">Data Management</h2>

      {filesError && <QueryError error={null} message="Failed to load data files" />}

      {/* Active Job Progress */}
      {activeJobId && job.data && (
        <div className="mb-6 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
          <div className="mb-2 flex items-center justify-between">
            <h3 className="text-sm font-medium">
              Job: {job.data.job_type.replace("_", " ")}
            </h3>
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

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Download Form */}
        <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
          <h3 className="mb-4 text-lg font-semibold">Download Data</h3>
          <div className="space-y-3">
            <div>
              <label htmlFor="data-symbols" className="mb-1 block text-xs text-[var(--color-text-muted)]">
                Symbols (comma-separated)
              </label>
              <input
                id="data-symbols"
                type="text"
                value={downloadSymbols}
                onChange={(e) => setDownloadSymbols(e.target.value)}
                className="w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-2 text-sm"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs text-[var(--color-text-muted)]">
                Timeframes
              </label>
              <div className="flex flex-wrap gap-1">
                {timeframes.map((tf) => (
                  <button
                    key={tf}
                    onClick={() => tfToggle(tf)}
                    className={`rounded px-2 py-1 text-xs ${
                      downloadTimeframes.includes(tf)
                        ? "bg-[var(--color-primary)] text-white"
                        : "bg-[var(--color-bg)] text-[var(--color-text-muted)]"
                    }`}
                  >
                    {tf}
                  </button>
                ))}
              </div>
            </div>
            <div>
              <label htmlFor="data-exchange" className="mb-1 block text-xs text-[var(--color-text-muted)]">
                Data Source
              </label>
              <select
                id="data-exchange"
                value={downloadExchange}
                onChange={(e) => setDownloadExchange(e.target.value)}
                className="w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-2 text-sm"
              >
                {EXCHANGE_OPTIONS[assetClass].map((ex) => (
                  <option key={ex.value} value={ex.value}>{ex.label}</option>
                ))}
              </select>
            </div>
            <div>
              <label htmlFor="data-days" className="mb-1 block text-xs text-[var(--color-text-muted)]">
                History (days)
              </label>
              <input
                id="data-days"
                type="number"
                value={downloadDays}
                onChange={(e) => setDownloadDays(Number(e.target.value))}
                className="w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-2 text-sm"
              />
            </div>
            <button
              onClick={() => downloadMutation.mutate()}
              disabled={isJobActive || downloadMutation.isPending}
              className="w-full rounded-lg bg-[var(--color-primary)] px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
            >
              {downloadMutation.isPending ? "Starting..." : "Download"}
            </button>
          </div>
        </div>

        {/* Quick Actions */}
        <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
          <h3 className="mb-4 text-lg font-semibold">Quick Actions</h3>
          <div className="space-y-3">
            <button
              onClick={() => sampleMutation.mutate()}
              disabled={isJobActive || sampleMutation.isPending}
              className="w-full rounded-lg border border-[var(--color-border)] px-4 py-2 text-sm font-medium text-[var(--color-text)] hover:bg-[var(--color-bg)] disabled:opacity-50"
            >
              Generate Sample Data
            </button>
            <p className="text-xs text-[var(--color-text-muted)]">
              Creates synthetic OHLCV data for {defaultSymbols.slice(0, 3).join(", ")} (1h + 4h, 90 days) — no API keys
              required.
            </p>
          </div>
        </div>

        {/* Summary */}
        <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
          <h3 className="mb-4 text-lg font-semibold">Data Summary</h3>
          <div className="text-3xl font-bold">{files?.length ?? 0}</div>
          <p className="text-sm text-[var(--color-text-muted)]">Parquet files available</p>
        </div>
      </div>

      {/* Data Files Table */}
      <div className="mt-6 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-lg font-semibold">Available Data</h3>
          <button
            onClick={() => queryClient.invalidateQueries({ queryKey: ["data-files"] })}
            className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-2 py-1 text-xs text-[var(--color-text-muted)] transition-colors hover:bg-[var(--color-surface)] hover:text-[var(--color-text)]"
            title="Refresh files"
          >
            &#8635; Refresh
          </button>
        </div>
        {isLoading && (
          <div className="space-y-2">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-10 animate-pulse rounded bg-[var(--color-border)]" />
            ))}
          </div>
        )}
        {filesError && (
          <p className="text-sm text-red-400">Failed to load data files.</p>
        )}
        {files && files.length === 0 && (
          <p className="text-sm text-[var(--color-text-muted)]">
            No data files found. Use the download form or generate sample data.
          </p>
        )}
        {files && files.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-[var(--color-border)] text-[var(--color-text-muted)]">
                  <th className="pb-2 pr-4">Symbol</th>
                  <th className="pb-2 pr-4">Timeframe</th>
                  <th className="pb-2 pr-4">Exchange</th>
                  <th className="pb-2 pr-4">Rows</th>
                  <th className="pb-2 pr-4">Start</th>
                  <th className="pb-2">End</th>
                </tr>
              </thead>
              <tbody>
                {files.map((f) => (
                  <tr
                    key={f.file}
                    className="border-b border-[var(--color-border)] last:border-0"
                  >
                    <td className="py-2 pr-4 font-medium">{f.symbol}</td>
                    <td className="py-2 pr-4">{f.timeframe}</td>
                    <td className="py-2 pr-4">{f.exchange}</td>
                    <td className="py-2 pr-4">{f.rows.toLocaleString()}</td>
                    <td className="py-2 pr-4 text-xs text-[var(--color-text-muted)]">
                      {f.start ? new Date(f.start).toLocaleDateString() : "—"}
                    </td>
                    <td className="py-2 text-xs text-[var(--color-text-muted)]">
                      {f.end ? new Date(f.end).toLocaleDateString() : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Data Quality Section */}
      <div className="mt-6 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-lg font-semibold">Data Quality</h3>
          <button
            onClick={() => {
              setShowQuality(true);
              if (showQuality) qualityQuery.refetch();
            }}
            disabled={qualityQuery.isFetching}
            className="rounded-lg bg-[var(--color-primary)] px-3 py-1 text-xs font-medium text-white disabled:opacity-50"
          >
            {qualityQuery.isFetching ? "Checking..." : "Run Quality Check"}
          </button>
        </div>
        {qualityQuery.data && (
          <>
            <div className="mb-4 flex gap-4 text-sm">
              <span className="text-green-400">{qualityQuery.data.passed} passed</span>
              <span className="text-red-400">{qualityQuery.data.failed} failed</span>
              <span className="text-[var(--color-text-muted)]">{qualityQuery.data.total} total</span>
            </div>
            {qualityQuery.data.reports.length > 0 && (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead>
                    <tr className="border-b border-[var(--color-border)] text-xs text-[var(--color-text-muted)]">
                      <th className="pb-2 pr-3">Symbol</th>
                      <th className="pb-2 pr-3">Timeframe</th>
                      <th className="pb-2 pr-3">Rows</th>
                      <th className="pb-2 pr-3">Status</th>
                      <th className="pb-2 pr-3">Gaps</th>
                      <th className="pb-2 pr-3">Outliers</th>
                      <th className="pb-2 pr-3">Stale</th>
                      <th className="pb-2">Issues</th>
                    </tr>
                  </thead>
                  <tbody>
                    {qualityQuery.data.reports.map((r) => (
                      <tr key={`${r.symbol}-${r.timeframe}`} className="border-b border-[var(--color-border)] last:border-0">
                        <td className="py-2 pr-3 font-medium">{r.symbol}</td>
                        <td className="py-2 pr-3">{r.timeframe}</td>
                        <td className="py-2 pr-3 font-mono text-xs">{r.rows.toLocaleString()}</td>
                        <td className="py-2 pr-3">
                          <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                            r.passed
                              ? "bg-green-500/20 text-green-400"
                              : "bg-red-500/20 text-red-400"
                          }`}>
                            {r.passed ? "pass" : "fail"}
                          </span>
                        </td>
                        <td className="py-2 pr-3 font-mono text-xs">{r.gaps.length}</td>
                        <td className="py-2 pr-3 font-mono text-xs">{r.outliers.length}</td>
                        <td className="py-2 pr-3">
                          {r.is_stale ? (
                            <span className="text-xs text-yellow-400">{r.stale_hours.toFixed(0)}h</span>
                          ) : (
                            <span className="text-xs text-green-400">fresh</span>
                          )}
                        </td>
                        <td className="max-w-[200px] truncate py-2 text-xs text-[var(--color-text-muted)]" title={r.issues_summary.join("; ")}>
                          {r.issues_summary.length > 0 ? r.issues_summary.join("; ") : "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}
        {!showQuality && (
          <p className="text-sm text-[var(--color-text-muted)]">
            Click &quot;Run Quality Check&quot; to validate all data files for gaps, outliers, and staleness.
          </p>
        )}
      </div>
    </div>
  );
}
