import { api } from "./client";
import type { NotificationPreferences } from "../types";

export const notificationsApi = {
  getPreferences: (portfolioId: number) =>
    api.get<NotificationPreferences>(`/notifications/${portfolioId}/preferences`),

  updatePreferences: (portfolioId: number, prefs: Partial<NotificationPreferences>) =>
    api.put<NotificationPreferences>(`/notifications/${portfolioId}/preferences/`, prefs),
};
