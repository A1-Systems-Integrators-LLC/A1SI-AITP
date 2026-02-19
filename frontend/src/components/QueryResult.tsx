import type { UseQueryResult } from "@tanstack/react-query";
import type { ReactNode } from "react";

interface QueryResultProps<T> {
  query: UseQueryResult<T>;
  children: (data: T) => ReactNode;
  /** Compact inline loader instead of centered block */
  inline?: boolean;
}

/**
 * Renders loading / error / data states from a useQuery result.
 *
 * Usage:
 *   <QueryResult query={portfoliosQuery}>
 *     {(data) => <PortfolioList portfolios={data} />}
 *   </QueryResult>
 */
export function QueryResult<T>({
  query,
  children,
  inline,
}: QueryResultProps<T>) {
  if (query.isLoading) {
    if (inline) {
      return (
        <span className="text-sm text-[var(--color-text-muted)]">
          Loading...
        </span>
      );
    }
    return (
      <div className="flex items-center justify-center py-12">
        <div className="flex items-center gap-3 text-[var(--color-text-muted)]">
          <Spinner />
          <span className="text-sm">Loading...</span>
        </div>
      </div>
    );
  }

  if (query.isError) {
    const msg =
      query.error instanceof Error
        ? query.error.message
        : "Failed to load data";
    if (inline) {
      return <span className="text-sm text-red-400">{msg}</span>;
    }
    return (
      <div className="flex items-center justify-center py-12">
        <div className="w-full max-w-sm rounded-xl border border-red-500/30 bg-red-500/5 p-5 text-center">
          <p className="mb-3 text-sm text-red-400">{msg}</p>
          <button
            onClick={() => query.refetch()}
            className="rounded-lg bg-[var(--color-primary)] px-4 py-1.5 text-sm font-medium text-white transition-colors hover:opacity-90"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  if (query.data === undefined) return null;

  return <>{children(query.data)}</>;
}

function Spinner() {
  return (
    <svg
      className="h-5 w-5 animate-spin"
      viewBox="0 0 24 24"
      fill="none"
    >
      <circle
        className="opacity-25"
        cx="12"
        cy="12"
        r="10"
        stroke="currentColor"
        strokeWidth="4"
      />
      <path
        className="opacity-75"
        fill="currentColor"
        d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
      />
    </svg>
  );
}
