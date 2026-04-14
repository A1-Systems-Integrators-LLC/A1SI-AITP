import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { reportsApi, type PDFReport } from "../api/reports";

const MONTH_NAMES = [
  "", "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

export function Reports() {
  useEffect(() => {
    document.title = "Reports | A1SI-AITP";
  }, []);

  const { data: reports, isLoading, error } = useQuery<PDFReport[]>({
    queryKey: ["pdf-reports"],
    queryFn: () => reportsApi.list(),
  });

  const [selectedReport, setSelectedReport] = useState<PDFReport | null>(null);
  const [filterYear, setFilterYear] = useState<number | null>(null);
  const [filterMonth, setFilterMonth] = useState<number | null>(null);

  // Extract available years and months for filter dropdowns
  const { years, months } = useMemo(() => {
    if (!reports) return { years: [], months: [] };
    const ySet = new Set(reports.map((r) => r.year));
    const mSet = new Set(
      reports
        .filter((r) => !filterYear || r.year === filterYear)
        .map((r) => r.month),
    );
    return {
      years: Array.from(ySet).sort((a, b) => b - a),
      months: Array.from(mSet).sort((a, b) => a - b),
    };
  }, [reports, filterYear]);

  // Apply filters
  const filteredReports = useMemo(() => {
    if (!reports) return [];
    return reports.filter((r) => {
      if (filterYear && r.year !== filterYear) return false;
      if (filterMonth && r.month !== filterMonth) return false;
      return true;
    });
  }, [reports, filterYear, filterMonth]);

  // Auto-select the most recent report on load
  useEffect(() => {
    if (filteredReports.length > 0 && !selectedReport) {
      setSelectedReport(filteredReports[0]);
    }
  }, [filteredReports, selectedReport]);

  const pdfUrl = selectedReport
    ? reportsApi.downloadUrl(selectedReport.filename)
    : null;

  if (error) {
    return (
      <div className="p-6">
        <h2 className="mb-4 text-2xl font-bold text-[var(--color-text)]">Reports</h2>
        <div className="rounded-xl border border-red-500/30 bg-red-500/10 p-4 text-red-400">
          Failed to load reports: {String(error)}
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-[calc(100vh-4rem)] flex-col gap-4 p-6">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold text-[var(--color-text)]">Reports</h2>
        <div className="flex items-center gap-3">
          {/* Year filter */}
          <select
            value={filterYear ?? ""}
            onChange={(e) => {
              const v = e.target.value ? Number(e.target.value) : null;
              setFilterYear(v);
              setFilterMonth(null);
            }}
            className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-1.5 text-sm text-[var(--color-text)]"
          >
            <option value="">All Years</option>
            {years.map((y) => (
              <option key={y} value={y}>{y}</option>
            ))}
          </select>

          {/* Month filter */}
          <select
            value={filterMonth ?? ""}
            onChange={(e) => {
              setFilterMonth(e.target.value ? Number(e.target.value) : null);
            }}
            className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-1.5 text-sm text-[var(--color-text)]"
          >
            <option value="">All Months</option>
            {months.map((m) => (
              <option key={m} value={m}>{MONTH_NAMES[m]}</option>
            ))}
          </select>
        </div>
      </div>

      <div className="flex min-h-0 flex-1 gap-4">
        {/* Report list sidebar */}
        <div className="w-64 shrink-0 overflow-y-auto rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)]">
          {isLoading ? (
            <div className="space-y-2 p-3">
              {[1, 2, 3, 4, 5].map((i) => (
                <div key={i} className="h-12 animate-pulse rounded-lg bg-[var(--color-border)]" />
              ))}
            </div>
          ) : filteredReports.length === 0 ? (
            <div className="p-4 text-center text-sm text-[var(--color-text-muted)]">
              No reports found
            </div>
          ) : (
            <ul className="divide-y divide-[var(--color-border)]">
              {filteredReports.map((report) => {
                const isActive = selectedReport?.filename === report.filename;
                const sizeKB = Math.round(report.size_bytes / 1024);
                return (
                  <li key={report.filename}>
                    <button
                      onClick={() => setSelectedReport(report)}
                      className={`w-full px-4 py-3 text-left transition-colors ${
                        isActive
                          ? "bg-[var(--color-primary)]/10 text-[var(--color-primary)]"
                          : "text-[var(--color-text)] hover:bg-[var(--color-border)]/30"
                      }`}
                    >
                      <div className="text-sm font-medium">{report.date}</div>
                      <div className="text-xs text-[var(--color-text-muted)]">
                        {sizeKB} KB
                      </div>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>

        {/* PDF viewer */}
        <div className="flex-1 overflow-hidden rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)]">
          {pdfUrl ? (
            <iframe
              key={pdfUrl}
              src={pdfUrl}
              className="h-full w-full"
              title={`Report ${selectedReport?.date}`}
            />
          ) : (
            <div className="flex h-full items-center justify-center text-[var(--color-text-muted)]">
              {isLoading ? "Loading reports..." : "Select a report to view"}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
