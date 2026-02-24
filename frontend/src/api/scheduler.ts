import { api } from "./client";
import type { ScheduledTask, SchedulerStatus } from "../types";

export const schedulerApi = {
  status: () => api.get<SchedulerStatus>("/scheduler/status/"),
  tasks: () => api.get<ScheduledTask[]>("/scheduler/tasks/"),
  task: (id: string) => api.get<ScheduledTask>(`/scheduler/tasks/${id}/`),
  pause: (id: string) => api.post<{ status: string }>(`/scheduler/tasks/${id}/pause/`),
  resume: (id: string) => api.post<{ status: string }>(`/scheduler/tasks/${id}/resume/`),
  trigger: (id: string) => api.post<{ status: string; job_id: string }>(`/scheduler/tasks/${id}/trigger/`),
};
