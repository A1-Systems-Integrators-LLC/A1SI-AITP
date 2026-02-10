import { api } from "./client";
import type { Portfolio } from "../types";

export const portfoliosApi = {
  list: () => api.get<Portfolio[]>("/portfolios/"),
  get: (id: number) => api.get<Portfolio>(`/portfolios/${id}`),
  create: (data: { name: string; exchange_id?: string }) =>
    api.post<Portfolio>("/portfolios/", data),
  delete: (id: number) => api.delete<void>(`/portfolios/${id}`),
};
