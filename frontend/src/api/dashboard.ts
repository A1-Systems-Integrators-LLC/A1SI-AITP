import { api } from "./client";
import type { DashboardKPIs } from "../types";

export const dashboardApi = {
  kpis: (assetClass?: string): Promise<DashboardKPIs> => {
    const params = assetClass ? `?asset_class=${assetClass}` : "";
    return api.get<DashboardKPIs>(`/dashboard/kpis/${params}`);
  },
};
