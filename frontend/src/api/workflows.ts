import { api } from "./client";
import type {
  AssetClass,
  StepType,
  WorkflowDetail,
  WorkflowListItem,
  WorkflowRunDetail,
  WorkflowRunListItem,
} from "../types";

export const workflowsApi = {
  list: (assetClass?: AssetClass) => {
    const qs = assetClass ? `?asset_class=${assetClass}` : "";
    return api.get<WorkflowListItem[]>(`/workflows/${qs}`);
  },
  get: (id: string) => api.get<WorkflowDetail>(`/workflows/${id}/`),
  create: (data: Record<string, unknown>) =>
    api.post<WorkflowDetail>("/workflows/", data),
  delete: (id: string) => api.delete<void>(`/workflows/${id}/`),
  trigger: (id: string, params?: Record<string, unknown>) =>
    api.post<{ workflow_run_id: string; job_id: string }>(
      `/workflows/${id}/trigger/`,
      params ? { params } : undefined,
    ),
  enable: (id: string) =>
    api.post<{ status: string }>(`/workflows/${id}/enable/`),
  disable: (id: string) =>
    api.post<{ status: string }>(`/workflows/${id}/disable/`),
  runs: (id: string, limit?: number) =>
    api.get<WorkflowRunListItem[]>(
      `/workflows/${id}/runs/${limit ? `?limit=${limit}` : ""}`,
    ),
  run: (runId: string) =>
    api.get<WorkflowRunDetail>(`/workflow-runs/${runId}/`),
  cancelRun: (runId: string) =>
    api.post<{ status: string }>(`/workflow-runs/${runId}/cancel/`),
  stepTypes: () => api.get<StepType[]>("/workflow-steps/"),
};
