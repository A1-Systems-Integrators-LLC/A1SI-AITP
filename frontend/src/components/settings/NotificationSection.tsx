import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { notificationsApi } from "../../api/notifications";
import { portfoliosApi } from "../../api/portfolios";
import { useToast } from "../../hooks/useToast";
import { getErrorMessage } from "../../utils/errors";
import type { NotificationPreferences, Portfolio } from "../../types";

const NOTIFICATION_TOGGLES: { key: keyof NotificationPreferences; label: string; description: string }[] = [
  { key: "on_order_submitted", label: "Order Submitted", description: "When a live order is placed on the exchange" },
  { key: "on_order_filled", label: "Order Filled", description: "When an order is completely filled" },
  { key: "on_order_cancelled", label: "Order Cancelled", description: "When an order is cancelled" },
  { key: "on_risk_halt", label: "Risk Halt/Resume", description: "When trading is halted or resumed" },
  { key: "on_trade_rejected", label: "Trade Rejected", description: "When a trade fails risk checks" },
  { key: "on_daily_summary", label: "Daily Summary", description: "Daily PnL and equity summary" },
];

export function NotificationSection() {
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const [portfolioId, setPortfolioId] = useState(1);

  const { data: portfolios } = useQuery<Portfolio[]>({
    queryKey: ["portfolios"],
    queryFn: () => portfoliosApi.list(),
  });

  const { data: prefs } = useQuery<NotificationPreferences>({
    queryKey: ["notification-prefs", portfolioId],
    queryFn: () => notificationsApi.getPreferences(portfolioId),
  });

  const notifUpdateMutation = useMutation({
    mutationFn: (updates: Partial<NotificationPreferences>) =>
      notificationsApi.updatePreferences(portfolioId, updates),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["notification-prefs", portfolioId] });
    },
    onError: (err) => toast(getErrorMessage(err) || "Failed to update notification preferences", "error"),
  });

  const toggle = (key: keyof NotificationPreferences) => {
    if (!prefs) return;
    notifUpdateMutation.mutate({ [key]: !prefs[key] });
  };

  return (
    <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h3 className="text-lg font-semibold">Notifications</h3>
          <p className="text-sm text-[var(--color-text-muted)]">
            Configure which events trigger notifications. Requires Telegram bot token
            and chat ID in environment variables.
          </p>
        </div>
        {portfolios && portfolios.length > 0 && (
          <div className="flex items-center gap-2">
            <label htmlFor="notif-portfolio" className="text-sm text-[var(--color-text-muted)]">Portfolio:</label>
            <select
              id="notif-portfolio"
              value={portfolioId}
              onChange={(e) => setPortfolioId(Number(e.target.value))}
              className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-2 py-1 text-sm"
            >
              {portfolios.map((p) => (
                <option key={p.id} value={p.id}>{p.name}</option>
              ))}
            </select>
          </div>
        )}
      </div>

      {prefs && (
        <div className="space-y-4">
          {/* Channel toggles */}
          <div className="flex gap-6">
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={prefs.telegram_enabled}
                onChange={() => toggle("telegram_enabled")}
                className="h-4 w-4 rounded border-gray-600 bg-gray-700"
              />
              Telegram
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={prefs.webhook_enabled}
                onChange={() => toggle("webhook_enabled")}
                className="h-4 w-4 rounded border-gray-600 bg-gray-700"
              />
              Webhook
            </label>
          </div>

          {/* Event toggles */}
          <div className="space-y-2">
            {NOTIFICATION_TOGGLES.map(({ key, label, description }) => (
              <div
                key={key}
                className="flex items-center justify-between rounded-lg border border-[var(--color-border)] px-3 py-2"
              >
                <div>
                  <p className="text-sm font-medium">{label}</p>
                  <p className="text-xs text-[var(--color-text-muted)]">{description}</p>
                </div>
                <button
                  onClick={() => toggle(key)}
                  className={`relative h-6 w-11 rounded-full transition-colors ${
                    prefs[key] ? "bg-blue-600" : "bg-gray-600"
                  }`}
                >
                  <span
                    className={`absolute top-0.5 h-5 w-5 rounded-full bg-white transition-transform ${
                      prefs[key] ? "translate-x-5" : "translate-x-0.5"
                    }`}
                  />
                </button>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
