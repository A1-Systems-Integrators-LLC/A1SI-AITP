import { useCallback, useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { riskApi } from "../api/risk";
import { useToast } from "../hooks/useToast";

interface EmergencyStopButtonProps {
  portfolioId?: number;
  isHalted?: boolean | null;
}

export function EmergencyStopButton({
  portfolioId = 1,
  isHalted,
}: EmergencyStopButtonProps) {
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const [holdProgress, setHoldProgress] = useState(0);
  const intervalRef = useRef<ReturnType<typeof setInterval>>(undefined);

  const haltMutation = useMutation({
    mutationFn: () =>
      riskApi.haltTrading(portfolioId, "Emergency manual halt"),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["risk-status"] });
      queryClient.invalidateQueries({ queryKey: ["orders"] });
      toast("Trading halted", "error");
    },
    onError: (err) => toast((err as Error).message || "Failed to halt trading", "error"),
  });

  const startHold = useCallback(() => {
    setHoldProgress(0);
    let progress = 0;
    intervalRef.current = setInterval(() => {
      progress += 5;
      setHoldProgress(progress);
      if (progress >= 100) {
        clearInterval(intervalRef.current);
        haltMutation.mutate();
        setHoldProgress(0);
      }
    }, 100); // 20 steps * 100ms = 2 seconds
  }, [haltMutation]);

  const cancelHold = useCallback(() => {
    clearInterval(intervalRef.current);
    setHoldProgress(0);
  }, []);

  if (isHalted) {
    return (
      <div className="mx-3 mb-2 flex items-center gap-2 rounded-lg border border-red-500/50 bg-red-500/20 px-3 py-2">
        <span className="h-2.5 w-2.5 animate-pulse rounded-full bg-red-500" />
        <span className="text-xs font-bold text-red-400">HALTED</span>
      </div>
    );
  }

  return (
    <div className="mx-3 mb-2">
      <button
        onMouseDown={startHold}
        onMouseUp={cancelHold}
        onMouseLeave={cancelHold}
        onTouchStart={startHold}
        onTouchEnd={cancelHold}
        disabled={haltMutation.isPending}
        className="relative w-full overflow-hidden rounded-lg border border-red-700 bg-red-900/30 px-3 py-2 text-xs font-bold text-red-400 transition-colors hover:bg-red-900/50 disabled:opacity-50"
      >
        {/* Hold progress bar */}
        {holdProgress > 0 && (
          <div
            className="absolute inset-y-0 left-0 bg-red-600/30 transition-all"
            style={{ width: `${holdProgress}%` }}
          />
        )}
        <span className="relative">
          {haltMutation.isPending
            ? "Halting..."
            : holdProgress > 0
              ? "Hold to halt..."
              : "EMERGENCY STOP"}
        </span>
      </button>
    </div>
  );
}
