import { useContext } from "react";
import { SystemEventsContext } from "../contexts/systemEvents";

/**
 * Consume the SystemEventsContext provided by Layout.
 * Use this in child pages (Trading, RiskManagement, etc.) to avoid
 * opening duplicate WebSocket connections.
 *
 * Falls back to a safe default if used outside the provider (should not happen).
 */
export function useSystemEventsContext() {
  const ctx = useContext(SystemEventsContext);
  if (!ctx) {
    return {
      isConnected: false,
      isReconnecting: false,
      reconnectAttempt: 0,
      reconnect: () => {},
      isHalted: null,
      haltReason: "",
      lastOrderUpdate: null,
      lastRiskAlert: null,
      lastRegimeChange: null,
      lastSchedulerEvent: null,
    };
  }
  return ctx;
}
