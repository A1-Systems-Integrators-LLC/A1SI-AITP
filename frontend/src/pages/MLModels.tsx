import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { mlApi, type MLModel } from "../api/ml";
import { useJobPolling } from "../hooks/useJobPolling";
import { useToast } from "../hooks/useToast";
import { ProgressBar } from "../components/ProgressBar";
import { QueryError } from "../components/QueryError";

export function MLModels() {
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const [trainSymbol, setTrainSymbol] = useState("BTC/USDT");
  const [trainTimeframe, setTrainTimeframe] = useState("1h");
  const [trainExchange, setTrainExchange] = useState("binance");
  const [testRatio, setTestRatio] = useState(0.2);
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [predictModelId, setPredictModelId] = useState("");
  const [predictResult, setPredictResult] = useState<string | null>(null);

  const { data: models, isLoading, isError: modelsError, error: modelsErr } = useQuery<MLModel[]>({
    queryKey: ["ml-models"],
    queryFn: mlApi.listModels,
  });

  const job = useJobPolling(activeJobId);
  const isJobActive = job.data?.status === "pending" || job.data?.status === "running";

  if (job.data?.status === "completed" || job.data?.status === "failed") {
    if (activeJobId) {
      queryClient.invalidateQueries({ queryKey: ["ml-models"] });
    }
  }

  const trainMutation = useMutation({
    mutationFn: () =>
      mlApi.train({
        symbol: trainSymbol,
        timeframe: trainTimeframe,
        exchange: trainExchange,
        test_ratio: testRatio,
      }),
    onSuccess: (data) => setActiveJobId(data.job_id),
    onError: (err) => toast((err as Error).message || "Failed to start training", "error"),
  });

  const predictMutation = useMutation({
    mutationFn: (modelId: string) =>
      mlApi.predict({ model_id: modelId, symbol: trainSymbol, bars: 10 }),
    onSuccess: (data) =>
      setPredictResult(JSON.stringify(data.predictions?.slice(0, 5), null, 2)),
    onError: (err) => setPredictResult(`Error: ${err.message}`),
  });

  return (
    <div>
      <h2 className="mb-6 text-2xl font-bold">ML Models</h2>

      {modelsError && <QueryError error={modelsErr instanceof Error ? modelsErr : null} message="Failed to load ML models" />}

      {/* Active Job Progress */}
      {activeJobId && job.data && (
        <div className="mb-6 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
          <div className="mb-2 flex items-center justify-between">
            <h3 className="text-sm font-medium">
              Training: {job.data.job_type?.replace(/_/g, " ") ?? "ml train"}
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
        {/* Train Form */}
        <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
          <h3 className="mb-4 text-lg font-semibold">Train Model</h3>
          <div className="space-y-3">
            <div>
              <label htmlFor="ml-symbol" className="mb-1 block text-xs text-[var(--color-text-muted)]">Symbol</label>
              <input
                id="ml-symbol"
                type="text"
                value={trainSymbol}
                onChange={(e) => setTrainSymbol(e.target.value)}
                className="w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-2 text-sm"
              />
            </div>
            <div>
              <label htmlFor="ml-timeframe" className="mb-1 block text-xs text-[var(--color-text-muted)]">Timeframe</label>
              <select
                id="ml-timeframe"
                value={trainTimeframe}
                onChange={(e) => setTrainTimeframe(e.target.value)}
                className="w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-2 text-sm"
              >
                <option value="1h">1h</option>
                <option value="4h">4h</option>
                <option value="1d">1d</option>
              </select>
            </div>
            <div>
              <label htmlFor="ml-exchange" className="mb-1 block text-xs text-[var(--color-text-muted)]">Exchange</label>
              <select
                id="ml-exchange"
                value={trainExchange}
                onChange={(e) => setTrainExchange(e.target.value)}
                className="w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-2 text-sm"
              >
                <option value="binance">Binance</option>
                <option value="bybit">Bybit</option>
                <option value="sample">Sample</option>
              </select>
            </div>
            <div>
              <label htmlFor="ml-test-ratio" className="mb-1 block text-xs text-[var(--color-text-muted)]">Test Ratio</label>
              <input
                id="ml-test-ratio"
                type="number"
                value={testRatio}
                onChange={(e) => setTestRatio(Number(e.target.value))}
                min={0.05}
                max={0.5}
                step={0.05}
                className="w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-2 text-sm"
              />
            </div>
            <button
              onClick={() => trainMutation.mutate()}
              disabled={isJobActive || trainMutation.isPending}
              className="w-full rounded-lg bg-[var(--color-primary)] px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
            >
              {trainMutation.isPending ? "Starting..." : "Train Model"}
            </button>
          </div>
        </div>

        {/* Predict */}
        <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
          <h3 className="mb-4 text-lg font-semibold">Predict</h3>
          <div className="space-y-3">
            <div>
              <label htmlFor="ml-predict-model" className="mb-1 block text-xs text-[var(--color-text-muted)]">Model ID</label>
              <select
                id="ml-predict-model"
                value={predictModelId}
                onChange={(e) => setPredictModelId(e.target.value)}
                className="w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-2 text-sm"
              >
                <option value="">Select a model...</option>
                {models?.map((m) => (
                  <option key={m.model_id} value={m.model_id}>
                    {m.model_id} ({m.symbol})
                  </option>
                ))}
              </select>
            </div>
            <button
              onClick={() => predictModelId && predictMutation.mutate(predictModelId)}
              disabled={!predictModelId || predictMutation.isPending}
              className="w-full rounded-lg border border-[var(--color-border)] px-4 py-2 text-sm font-medium text-[var(--color-text)] hover:bg-[var(--color-bg)] disabled:opacity-50"
            >
              {predictMutation.isPending ? "Predicting..." : "Run Prediction"}
            </button>
            {predictResult && (
              <pre className="mt-2 max-h-48 overflow-auto rounded-lg bg-[var(--color-bg)] p-3 text-xs">
                {predictResult}
              </pre>
            )}
          </div>
        </div>

        {/* Summary */}
        <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
          <h3 className="mb-4 text-lg font-semibold">Model Summary</h3>
          <div className="text-3xl font-bold">{models?.length ?? 0}</div>
          <p className="text-sm text-[var(--color-text-muted)]">Trained models available</p>
        </div>
      </div>

      {/* Model List */}
      <div className="mt-6 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
        <h3 className="mb-4 text-lg font-semibold">Trained Models</h3>
        {isLoading && (
          <div className="space-y-2">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-10 animate-pulse rounded bg-[var(--color-border)]" />
            ))}
          </div>
        )}
        {models && models.length === 0 && (
          <p className="text-sm text-[var(--color-text-muted)]">
            No trained models yet. Use the training form to create one.
          </p>
        )}
        {models && models.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-[var(--color-border)] text-[var(--color-text-muted)]">
                  <th className="pb-2 pr-4">Model ID</th>
                  <th className="pb-2 pr-4">Symbol</th>
                  <th className="pb-2 pr-4">Timeframe</th>
                  <th className="pb-2 pr-4">Exchange</th>
                  <th className="pb-2">Created</th>
                </tr>
              </thead>
              <tbody>
                {models.map((m) => (
                  <tr key={m.model_id} className="border-b border-[var(--color-border)] last:border-0">
                    <td className="py-2 pr-4 font-mono text-xs">{m.model_id}</td>
                    <td className="py-2 pr-4 font-medium">{m.symbol}</td>
                    <td className="py-2 pr-4">{m.timeframe}</td>
                    <td className="py-2 pr-4">{m.exchange}</td>
                    <td className="py-2 text-xs text-[var(--color-text-muted)]">
                      {m.created_at ? new Date(m.created_at).toLocaleDateString() : "\u2014"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
