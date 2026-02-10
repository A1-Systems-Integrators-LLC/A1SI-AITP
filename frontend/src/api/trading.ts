import { api } from "./client";
import type { Order } from "../types";

export const tradingApi = {
  listOrders: (limit = 50) =>
    api.get<Order[]>(`/trading/orders?limit=${limit}`),
  getOrder: (id: number) => api.get<Order>(`/trading/orders/${id}`),
  createOrder: (data: {
    symbol: string;
    side: "buy" | "sell";
    order_type?: string;
    amount: number;
    price?: number;
    exchange_id?: string;
  }) => api.post<Order>("/trading/orders", data),
};
