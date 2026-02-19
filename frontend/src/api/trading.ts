import { api } from "./client";
import type { LiveTradingStatus, Order, OrderCreate, TradingMode } from "../types";

export const tradingApi = {
  listOrders: (limit = 50, mode?: TradingMode) => {
    const params = new URLSearchParams({ limit: String(limit) });
    if (mode) params.set("mode", mode);
    return api.get<Order[]>(`/trading/orders?${params}`);
  },
  getOrder: (id: number) => api.get<Order>(`/trading/orders/${id}`),
  createOrder: (data: OrderCreate) => api.post<Order>("/trading/orders/", data),
  cancelOrder: (id: number) => api.post<Order>(`/trading/orders/${id}/cancel/`),
  liveStatus: () => api.get<LiveTradingStatus>("/live-trading/status/"),
};
