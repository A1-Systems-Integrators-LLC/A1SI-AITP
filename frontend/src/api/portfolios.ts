import { api } from "./client";
import type { Holding, Portfolio } from "../types";

export const portfoliosApi = {
  list: () => api.get<Portfolio[]>("/portfolios/"),
  get: (id: number) => api.get<Portfolio>(`/portfolios/${id}/`),
  create: (data: { name: string; exchange_id?: string; description?: string }) =>
    api.post<Portfolio>("/portfolios/", data),
  update: (id: number, data: { name?: string; exchange_id?: string; description?: string }) =>
    api.put<Portfolio>(`/portfolios/${id}/`, data),
  patch: (id: number, data: { name?: string; exchange_id?: string; description?: string }) =>
    api.patch<Portfolio>(`/portfolios/${id}/`, data),
  delete: (id: number) => api.delete<void>(`/portfolios/${id}/`),
  addHolding: (portfolioId: number, data: { symbol: string; amount?: number; avg_buy_price?: number }) =>
    api.post<Holding>(`/portfolios/${portfolioId}/holdings/`, data),
  updateHolding: (portfolioId: number, holdingId: number, data: { amount?: number; avg_buy_price?: number }) =>
    api.put<Holding>(`/portfolios/${portfolioId}/holdings/${holdingId}/`, data),
  deleteHolding: (portfolioId: number, holdingId: number) =>
    api.delete<void>(`/portfolios/${portfolioId}/holdings/${holdingId}/`),
};
