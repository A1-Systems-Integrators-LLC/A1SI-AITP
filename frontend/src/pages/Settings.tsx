import { useEffect } from "react";
import { ErrorBoundary } from "../components/ErrorBoundary";
import { WidgetErrorFallback } from "../components/WidgetErrorFallback";
import { ExchangeConfigSection } from "../components/settings/ExchangeConfigSection";
import { DataSourceSection } from "../components/settings/DataSourceSection";
import { NotificationSection } from "../components/settings/NotificationSection";
import { AuditLogSection } from "../components/settings/AuditLogSection";

export function Settings() {
  useEffect(() => { document.title = "Settings | A1SI-AITP"; }, []);

  return (
    <div>
      <section aria-labelledby="page-heading">
      <h2 id="page-heading" className="mb-6 text-2xl font-bold">Settings</h2>

      <ErrorBoundary fallback={<WidgetErrorFallback name="Settings" />}>
      <div className="max-w-2xl space-y-6">
        {/* Exchange Connections */}
        <ExchangeConfigSection />

        {/* Data Sources */}
        <DataSourceSection />

        {/* Notification Preferences */}
        <NotificationSection />

        {/* Audit Log */}
        <AuditLogSection />

        {/* About */}
        <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
          <h3 className="mb-2 text-lg font-semibold">About</h3>
          <p className="text-sm text-[var(--color-text-muted)]">
            A1SI-AITP v0.1.0
          </p>
        </div>
      </div>
      </ErrorBoundary>
      </section>
    </div>
  );
}
