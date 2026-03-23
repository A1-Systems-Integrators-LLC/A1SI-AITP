import { createContext } from "react";
import type {
  OrderUpdateEvent,
  RiskAlertEvent,
  RegimeChangeEvent,
  SchedulerEventData,
} from "../types";

export interface SystemEventsContextValue {
  isConnected: boolean;
  isReconnecting: boolean;
  reconnectAttempt: number;
  reconnect: () => void;
  isHalted: boolean | null;
  haltReason: string;
  lastOrderUpdate: OrderUpdateEvent["data"] | null;
  lastRiskAlert: RiskAlertEvent["data"] | null;
  lastRegimeChange: RegimeChangeEvent["data"] | null;
  lastSchedulerEvent: SchedulerEventData["data"] | null;
}

export const SystemEventsContext = createContext<SystemEventsContextValue | null>(null);
