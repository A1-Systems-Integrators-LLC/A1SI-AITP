import { api } from "./client";
import type { ExchangeInfo } from "../types";

export const exchangesApi = {
  list: () => api.get<ExchangeInfo[]>("/exchanges/"),
};
