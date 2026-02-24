interface QueryErrorProps {
  error: Error | null;
  message?: string;
  onRetry?: () => void;
}

export function QueryError({ error, message, onRetry }: QueryErrorProps) {
  const displayMessage = message ?? (error instanceof Error ? error.message : "An error occurred");

  return (
    <div className="mb-4 rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-400">
      <p>{displayMessage}</p>
      {onRetry && (
        <button
          onClick={onRetry}
          className="mt-2 rounded border border-red-500/30 px-3 py-1 text-xs hover:bg-red-500/20"
        >
          Retry
        </button>
      )}
    </div>
  );
}
