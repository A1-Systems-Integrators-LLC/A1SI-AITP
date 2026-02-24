import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { workflowsApi } from "../api/workflows";
import { useToast } from "../hooks/useToast";
import { useAssetClass } from "../hooks/useAssetClass";
import { AssetClassBadge } from "../components/AssetClassBadge";
import { QueryError } from "../components/QueryError";
import { getErrorMessage } from "../utils/errors";
import type {
  StepType,
  WorkflowDetail,
  WorkflowListItem,
  WorkflowRunDetail,
  WorkflowRunListItem,
} from "../types";

export function Workflows() {
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const { assetClass } = useAssetClass();
  const [expandedWorkflow, setExpandedWorkflow] = useState<string | null>(null);
  const [expandedRun, setExpandedRun] = useState<string | null>(null);
  const [showStepTypes, setShowStepTypes] = useState(false);

  useEffect(() => { document.title = "Workflows | A1SI-AITP"; }, []);

  const { data: workflows, isLoading, isError: workflowsError, error: workflowsErr } = useQuery<WorkflowListItem[]>({
    queryKey: ["workflows", assetClass],
    queryFn: () => workflowsApi.list(assetClass),
  });

  const { data: stepTypes } = useQuery<StepType[]>({
    queryKey: ["workflow-step-types"],
    queryFn: workflowsApi.stepTypes,
  });

  const triggerMutation = useMutation({
    mutationFn: (id: string) => workflowsApi.trigger(id),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["workflows"] });
      toast(`Workflow triggered (job: ${data.job_id})`, "success");
    },
    onError: (err) => toast(getErrorMessage(err) || "Failed to trigger workflow", "error"),
  });

  const enableMutation = useMutation({
    mutationFn: (id: string) => workflowsApi.enable(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["workflows"] });
      toast("Workflow schedule enabled", "success");
    },
  });

  const disableMutation = useMutation({
    mutationFn: (id: string) => workflowsApi.disable(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["workflows"] });
      toast("Workflow schedule disabled", "info");
    },
  });

  const formatDate = (d: string | null) =>
    d ? new Date(d).toLocaleString() : "—";

  return (
    <div>
      <h2 className="mb-6 text-2xl font-bold">Workflows</h2>

      {workflowsError && <QueryError error={workflowsErr instanceof Error ? workflowsErr : null} message="Failed to load workflows" />}

      {/* Workflow list */}
      <div className="space-y-4">
        {isLoading && (
          <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
            <div className="space-y-2">
              {[1, 2, 3].map((i) => (
                <div key={i} className="h-12 animate-pulse rounded bg-[var(--color-border)]" />
              ))}
            </div>
          </div>
        )}

        {workflows?.map((wf) => (
          <div key={wf.id} className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
            <div className="flex items-start justify-between">
              <div className="flex-1">
                <div className="mb-1 flex items-center gap-2">
                  <h3 className="text-lg font-semibold">{wf.name}</h3>
                  <AssetClassBadge assetClass={wf.asset_class} />
                  {wf.is_template && (
                    <span className="rounded-full bg-purple-500/20 px-2 py-0.5 text-xs font-medium text-purple-400">
                      template
                    </span>
                  )}
                  {wf.schedule_enabled && (
                    <span className="rounded-full bg-blue-500/20 px-2 py-0.5 text-xs font-medium text-blue-400">
                      scheduled
                    </span>
                  )}
                </div>
                <p className="text-sm text-[var(--color-text-muted)]">{wf.description || "No description"}</p>
                <div className="mt-2 flex gap-4 text-xs text-[var(--color-text-muted)]">
                  <span>{wf.step_count} steps</span>
                  <span>{wf.run_count} runs</span>
                  <span>Last run: {formatDate(wf.last_run_at)}</span>
                </div>
              </div>
              <div className="flex gap-1">
                <button
                  onClick={() => triggerMutation.mutate(wf.id)}
                  disabled={triggerMutation.isPending}
                  className="rounded bg-[var(--color-primary)] px-3 py-1 text-xs font-medium text-white hover:opacity-90 disabled:opacity-50"
                >
                  Trigger
                </button>
                {wf.schedule_enabled ? (
                  <button
                    onClick={() => disableMutation.mutate(wf.id)}
                    className="rounded bg-yellow-500/10 px-3 py-1 text-xs text-yellow-400 hover:bg-yellow-500/20"
                  >
                    Disable
                  </button>
                ) : (
                  <button
                    onClick={() => enableMutation.mutate(wf.id)}
                    className="rounded bg-green-500/10 px-3 py-1 text-xs text-green-400 hover:bg-green-500/20"
                  >
                    Enable
                  </button>
                )}
                <button
                  onClick={() => setExpandedWorkflow(expandedWorkflow === wf.id ? null : wf.id)}
                  className="rounded bg-[var(--color-bg)] px-3 py-1 text-xs text-[var(--color-text-muted)] hover:text-[var(--color-text)]"
                >
                  {expandedWorkflow === wf.id ? "Collapse" : "Details"}
                </button>
              </div>
            </div>

            {/* Expanded detail */}
            {expandedWorkflow === wf.id && (
              <WorkflowExpandedDetail workflowId={wf.id} expandedRun={expandedRun} setExpandedRun={setExpandedRun} />
            )}
          </div>
        ))}

        {workflows && workflows.length === 0 && (
          <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
            <p className="text-sm text-[var(--color-text-muted)]">No workflows found for this asset class.</p>
          </div>
        )}
      </div>

      {/* Step types reference */}
      <div className="mt-6">
        <button
          onClick={() => setShowStepTypes(!showStepTypes)}
          className="mb-2 text-sm text-[var(--color-text-muted)] hover:text-[var(--color-text)]"
        >
          {showStepTypes ? "Hide" : "Show"} Available Step Types
        </button>
        {showStepTypes && stepTypes && (
          <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
            <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
              {stepTypes.map((st) => (
                <div key={st.step_type} className="rounded-lg bg-[var(--color-bg)] p-3">
                  <p className="font-mono text-sm font-medium">{st.step_type}</p>
                  <p className="text-xs text-[var(--color-text-muted)]">{st.description}</p>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function WorkflowExpandedDetail({
  workflowId,
  expandedRun,
  setExpandedRun,
}: {
  workflowId: string;
  expandedRun: string | null;
  setExpandedRun: (id: string | null) => void;
}) {
  const { data: detail } = useQuery<WorkflowDetail>({
    queryKey: ["workflow-detail", workflowId],
    queryFn: () => workflowsApi.get(workflowId),
  });

  const { data: runs } = useQuery<WorkflowRunListItem[]>({
    queryKey: ["workflow-runs", workflowId],
    queryFn: () => workflowsApi.runs(workflowId, 10),
  });

  return (
    <div className="mt-4 border-t border-[var(--color-border)] pt-4">
      {/* Steps */}
      {detail?.steps && detail.steps.length > 0 && (
        <div className="mb-4">
          <h4 className="mb-2 text-sm font-semibold">Steps</h4>
          <div className="space-y-1">
            {detail.steps
              .sort((a, b) => a.order - b.order)
              .map((step) => (
                <div key={step.id} className="flex items-center gap-3 rounded-lg bg-[var(--color-bg)] p-2 text-sm">
                  <span className="flex h-6 w-6 items-center justify-center rounded-full bg-[var(--color-primary)]/20 text-xs font-bold text-[var(--color-primary)]">
                    {step.order}
                  </span>
                  <span className="font-medium">{step.name}</span>
                  <span className="font-mono text-xs text-[var(--color-text-muted)]">{step.step_type}</span>
                  {step.condition && (
                    <span className="text-xs text-yellow-400">if: {step.condition}</span>
                  )}
                </div>
              ))}
          </div>
        </div>
      )}

      {/* Run History */}
      {runs && runs.length > 0 && (
        <div>
          <h4 className="mb-2 text-sm font-semibold">Run History</h4>
          <div className="space-y-1">
            {runs.map((run) => (
              <div key={run.id}>
                <button
                  onClick={() => setExpandedRun(expandedRun === run.id ? null : run.id)}
                  className="flex w-full items-center gap-3 rounded-lg bg-[var(--color-bg)] p-2 text-left text-sm hover:bg-[var(--color-border)]"
                >
                  <RunStatusBadge status={run.status} />
                  <span className="text-xs text-[var(--color-text-muted)]">{run.trigger}</span>
                  <span className="text-xs text-[var(--color-text-muted)]">
                    Step {run.current_step}/{run.total_steps}
                  </span>
                  <span className="ml-auto text-xs text-[var(--color-text-muted)]">
                    {run.started_at ? new Date(run.started_at).toLocaleString() : "—"}
                  </span>
                </button>
                {expandedRun === run.id && <RunDetail runId={run.id} />}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function RunDetail({ runId }: { runId: string }) {
  const { data: run } = useQuery<WorkflowRunDetail>({
    queryKey: ["workflow-run-detail", runId],
    queryFn: () => workflowsApi.run(runId),
  });

  if (!run) return null;

  return (
    <div className="ml-8 mt-1 space-y-1 border-l-2 border-[var(--color-border)] pl-3">
      {run.step_runs
        ?.sort((a, b) => a.order - b.order)
        .map((sr) => (
          <div key={sr.id} className="flex items-center gap-2 text-xs">
            <RunStatusBadge status={sr.status} />
            <span className="font-medium">{sr.step_name}</span>
            <span className="text-[var(--color-text-muted)]">{sr.step_type}</span>
            {sr.duration_seconds != null && (
              <span className="text-[var(--color-text-muted)]">{sr.duration_seconds.toFixed(1)}s</span>
            )}
            {sr.error && <span className="text-red-400">{sr.error}</span>}
            {!sr.condition_met && <span className="text-yellow-400">skipped</span>}
          </div>
        ))}
      {run.error && (
        <p className="text-xs text-red-400">Error: {run.error}</p>
      )}
    </div>
  );
}

function RunStatusBadge({ status }: { status: string }) {
  const styles: Record<string, string> = {
    completed: "bg-green-500/20 text-green-400",
    running: "bg-blue-500/20 text-blue-400",
    failed: "bg-red-500/20 text-red-400",
    cancelled: "bg-gray-500/20 text-gray-400",
    pending: "bg-yellow-500/20 text-yellow-400",
    skipped: "bg-gray-500/20 text-gray-400",
  };
  return (
    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${styles[status] ?? "bg-gray-500/20 text-gray-400"}`}>
      {status}
    </span>
  );
}
