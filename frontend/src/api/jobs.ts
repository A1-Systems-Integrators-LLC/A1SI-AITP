import { api } from "./client";
import type { BackgroundJob } from "../types";

export const jobsApi = {
  list: (type?: string, limit?: number) => {
    const params = new URLSearchParams();
    if (type) params.set("type", type);
    if (limit) params.set("limit", String(limit));
    const qs = params.toString();
    return api.get<BackgroundJob[]>(`/jobs/${qs ? `?${qs}` : ""}`);
  },

  get: (id: string) => api.get<BackgroundJob>(`/jobs/${id}`),

  cancel: (id: string) => api.post<{ status: string }>(`/jobs/${id}/cancel/`),
};
