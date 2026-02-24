import { useEffect } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { schedulerApi } from "../api/scheduler";
import { useToast } from "../hooks/useToast";
import type { ScheduledTask, SchedulerStatus } from "../types";

export function Scheduler() {
  const queryClient = useQueryClient();
  const { toast } = useToast();

  useEffect(() => { document.title = "Scheduler | A1SI-AITP"; }, []);

  const { data: status } = useQuery<SchedulerStatus>({
    queryKey: ["scheduler-status"],
    queryFn: schedulerApi.status,
    refetchInterval: 30000,
  });

  const { data: tasks, isLoading } = useQuery<ScheduledTask[]>({
    queryKey: ["scheduler-tasks"],
    queryFn: schedulerApi.tasks,
    refetchInterval: 30000,
  });

  const pauseMutation = useMutation({
    mutationFn: (id: string) => schedulerApi.pause(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["scheduler-tasks"] });
      toast("Task paused", "info");
    },
    onError: (err) => toast((err as Error).message || "Failed to pause task", "error"),
  });

  const resumeMutation = useMutation({
    mutationFn: (id: string) => schedulerApi.resume(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["scheduler-tasks"] });
      toast("Task resumed", "success");
    },
    onError: (err) => toast((err as Error).message || "Failed to resume task", "error"),
  });

  const triggerMutation = useMutation({
    mutationFn: (id: string) => schedulerApi.trigger(id),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["scheduler-tasks"] });
      toast(`Task triggered (job: ${data.job_id})`, "success");
    },
    onError: (err) => toast((err as Error).message || "Failed to trigger task", "error"),
  });

  const formatInterval = (seconds: number) => {
    if (seconds >= 3600) return `${Math.round(seconds / 3600)}h`;
    if (seconds >= 60) return `${Math.round(seconds / 60)}m`;
    return `${seconds}s`;
  };

  const formatDate = (d: string | null) =>
    d ? new Date(d).toLocaleString() : "—";

  return (
    <div>
      <h2 className="mb-6 text-2xl font-bold">Scheduler</h2>

      {/* Status bar */}
      <div className="mb-6 grid grid-cols-2 gap-3 md:grid-cols-4">
        <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
          <p className="text-xs text-[var(--color-text-muted)]">Status</p>
          <p className={`text-lg font-bold ${status?.running ? "text-green-400" : "text-red-400"}`}>
            {status?.running ? "Running" : "Stopped"}
          </p>
        </div>
        <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
          <p className="text-xs text-[var(--color-text-muted)]">Total Tasks</p>
          <p className="text-lg font-bold">{status?.total_tasks ?? 0}</p>
        </div>
        <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
          <p className="text-xs text-[var(--color-text-muted)]">Active</p>
          <p className="text-lg font-bold text-green-400">{status?.active_tasks ?? 0}</p>
        </div>
        <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
          <p className="text-xs text-[var(--color-text-muted)]">Paused</p>
          <p className="text-lg font-bold text-yellow-400">{status?.paused_tasks ?? 0}</p>
        </div>
      </div>

      {/* Task table */}
      <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-lg font-semibold">Scheduled Tasks</h3>
          <button
            onClick={() => queryClient.invalidateQueries({ queryKey: ["scheduler-tasks"] })}
            className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-2 py-1 text-xs text-[var(--color-text-muted)] hover:text-[var(--color-text)]"
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
        {tasks && tasks.length === 0 && (
          <p className="text-sm text-[var(--color-text-muted)]">No scheduled tasks found.</p>
        )}
        {tasks && tasks.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-[var(--color-border)] text-xs text-[var(--color-text-muted)]">
                  <th className="pb-2 pr-3">Name</th>
                  <th className="pb-2 pr-3">Type</th>
                  <th className="pb-2 pr-3">Status</th>
                  <th className="pb-2 pr-3">Interval</th>
                  <th className="pb-2 pr-3">Last Run</th>
                  <th className="pb-2 pr-3">Next Run</th>
                  <th className="pb-2 pr-3 text-right">Runs</th>
                  <th className="pb-2 pr-3 text-right">Errors</th>
                  <th className="pb-2">Actions</th>
                </tr>
              </thead>
              <tbody>
                {tasks.map((t) => (
                  <tr key={t.id} className="border-b border-[var(--color-border)] last:border-0">
                    <td className="py-2 pr-3 font-medium">{t.name}</td>
                    <td className="py-2 pr-3 text-xs">{t.task_type}</td>
                    <td className="py-2 pr-3">
                      <StatusBadge status={t.status} />
                    </td>
                    <td className="py-2 pr-3 font-mono text-xs">{formatInterval(t.interval_seconds)}</td>
                    <td className="py-2 pr-3 text-xs text-[var(--color-text-muted)]">{formatDate(t.last_run_at)}</td>
                    <td className="py-2 pr-3 text-xs text-[var(--color-text-muted)]">{formatDate(t.next_run_at)}</td>
                    <td className="py-2 pr-3 text-right font-mono text-xs">{t.run_count}</td>
                    <td className="py-2 pr-3 text-right font-mono text-xs">
                      <span className={t.error_count > 0 ? "text-red-400" : ""}>{t.error_count}</span>
                    </td>
                    <td className="py-2">
                      <div className="flex gap-1">
                        {t.status === "active" ? (
                          <button
                            onClick={() => pauseMutation.mutate(t.id)}
                            disabled={pauseMutation.isPending}
                            className="rounded bg-yellow-500/10 px-2 py-0.5 text-xs text-yellow-400 hover:bg-yellow-500/20"
                          >
                            Pause
                          </button>
                        ) : (
                          <button
                            onClick={() => resumeMutation.mutate(t.id)}
                            disabled={resumeMutation.isPending}
                            className="rounded bg-green-500/10 px-2 py-0.5 text-xs text-green-400 hover:bg-green-500/20"
                          >
                            Resume
                          </button>
                        )}
                        <button
                          onClick={() => triggerMutation.mutate(t.id)}
                          disabled={triggerMutation.isPending}
                          className="rounded bg-blue-500/10 px-2 py-0.5 text-xs text-blue-400 hover:bg-blue-500/20"
                        >
                          Trigger
                        </button>
                      </div>
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

function StatusBadge({ status }: { status: string }) {
  const styles: Record<string, string> = {
    active: "bg-green-500/20 text-green-400",
    paused: "bg-yellow-500/20 text-yellow-400",
    error: "bg-red-500/20 text-red-400",
  };
  return (
    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${styles[status] ?? "bg-gray-500/20 text-gray-400"}`}>
      {status}
    </span>
  );
}
