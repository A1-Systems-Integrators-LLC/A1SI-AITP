import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { auditApi } from "../../api/audit";
import { Pagination } from "../Pagination";
import type { AuditLogEntry } from "../../types";

const AUDIT_PAGE_SIZE = 15;

export function AuditLogSection() {
  const [userFilter, setUserFilter] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [page, setPage] = useState(1);

  const params = {
    limit: AUDIT_PAGE_SIZE,
    offset: (page - 1) * AUDIT_PAGE_SIZE,
    ...(userFilter && { user: userFilter }),
    ...(dateFrom && { created_after: dateFrom }),
  };

  const { data } = useQuery({
    queryKey: ["audit-log", params],
    queryFn: () => auditApi.list(params),
  });

  return (
    <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
      <h3 className="mb-4 text-lg font-semibold">Audit Log</h3>
      <p className="mb-4 text-sm text-[var(--color-text-muted)]">
        Request history recorded by the audit middleware.
      </p>

      <div className="mb-4 flex gap-3">
        <input
          type="text"
          placeholder="Filter by user"
          value={userFilter}
          onChange={(e) => { setUserFilter(e.target.value); setPage(1); }}
          className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-1.5 text-sm"
        />
        <input
          type="date"
          value={dateFrom}
          onChange={(e) => { setDateFrom(e.target.value); setPage(1); }}
          className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-1.5 text-sm"
        />
      </div>

      {data?.results && data.results.length > 0 ? (
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-[var(--color-border)] text-[var(--color-text-muted)]">
                <th className="pb-2 text-left">Time</th>
                <th className="pb-2 text-left">User</th>
                <th className="pb-2 text-left">Action</th>
                <th className="pb-2 text-left">IP</th>
                <th className="pb-2 text-right">Status</th>
              </tr>
            </thead>
            <tbody>
              {data.results.map((entry: AuditLogEntry) => (
                <tr key={entry.id} className="border-b border-[var(--color-border)]/30">
                  <td className="py-1.5 text-[var(--color-text-muted)]">
                    {new Date(entry.created_at).toLocaleString()}
                  </td>
                  <td className="py-1.5">{entry.user}</td>
                  <td className="py-1.5 max-w-xs truncate font-mono">{entry.action}</td>
                  <td className="py-1.5 text-[var(--color-text-muted)]">{entry.ip_address ?? "—"}</td>
                  <td className="py-1.5 text-right">
                    <span
                      className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                        entry.status_code < 400
                          ? "bg-green-500/20 text-green-400"
                          : entry.status_code < 500
                            ? "bg-yellow-500/20 text-yellow-400"
                            : "bg-red-500/20 text-red-400"
                      }`}
                    >
                      {entry.status_code}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <Pagination page={page} pageSize={AUDIT_PAGE_SIZE} total={data.total} onPageChange={setPage} />
        </div>
      ) : (
        <p className="text-sm text-[var(--color-text-muted)]">
          No audit log entries found.
        </p>
      )}
    </div>
  );
}
