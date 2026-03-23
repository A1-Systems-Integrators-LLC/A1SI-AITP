import { useEffect, useRef, useState } from "react";
import { NavLink, Outlet } from "react-router-dom";
import {
  LayoutDashboard,
  Wallet,
  BarChart3,
  ArrowLeftRight,
  Database,
  Search,
  Shield,
  Activity,
  Play,
  PlayCircle,
  BrainCircuit,
  Clock,
  GitBranch,
  Crosshair,
  Target,
  Settings,
  LogOut,
  Menu,
  X,
} from "lucide-react";
import { ConnectionStatus } from "./ConnectionStatus";
import { EmergencyStopButton } from "./EmergencyStopButton";
import { ErrorBoundary } from "./ErrorBoundary";
import { AssetClassSelector } from "./AssetClassSelector";
import { ThemeToggle } from "./ThemeToggle";
import { AssetClassContext } from "../contexts/assetClass";
import { SystemEventsContext } from "../contexts/systemEvents";
import { ThemeContext } from "../contexts/theme";
import type { Theme } from "../contexts/theme";
import { useLocalStorage } from "../hooks/useLocalStorage";
import { useSystemEvents } from "../hooks/useSystemEvents";
import { useToast } from "../hooks/useToast";
import type { AssetClass } from "../types";

const navItems = [
  { to: "/", icon: LayoutDashboard, label: "Dashboard" },
  { to: "/portfolio", icon: Wallet, label: "Portfolio" },
  { to: "/market", icon: BarChart3, label: "Market" },
  { to: "/trading", icon: ArrowLeftRight, label: "Trading" },
  { to: "/data", icon: Database, label: "Data" },
  { to: "/screening", icon: Search, label: "Screening" },
  { to: "/risk", icon: Shield, label: "Risk" },
  { to: "/regime", icon: Activity, label: "Regime" },
  { to: "/backtest", icon: Play, label: "Backtest" },
  { to: "/paper-trading", icon: PlayCircle, label: "Paper Trade" },
  { to: "/ml", icon: BrainCircuit, label: "ML Models" },
  { to: "/scheduler", icon: Clock, label: "Scheduler" },
  { to: "/workflows", icon: GitBranch, label: "Workflows" },
  { to: "/opportunities", icon: Crosshair, label: "Opportunities" },
  { to: "/conviction", icon: Target, label: "Conviction" },
  { to: "/settings", icon: Settings, label: "Settings" },
];

interface LayoutProps {
  onLogout: () => Promise<void>;
  username: string | null;
}

export function Layout({ onLogout, username }: LayoutProps) {
  const [assetClass, setAssetClass] = useLocalStorage<AssetClass>("ci:asset-class", "crypto");
  const [theme, setTheme] = useLocalStorage<Theme>("ci:theme", "dark");
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const systemEvents = useSystemEvents();
  const { isConnected, isReconnecting, reconnectAttempt, reconnect, isHalted, haltReason, lastOrderUpdate, lastRiskAlert } = systemEvents;
  const { toast } = useToast();
  const prevOrderRef = useRef(lastOrderUpdate);
  const prevAlertRef = useRef(lastRiskAlert);

  useEffect(() => {
    if (lastOrderUpdate && lastOrderUpdate !== prevOrderRef.current) {
      const symbol = String(lastOrderUpdate?.symbol ?? "");
      const status = String(lastOrderUpdate?.status ?? "updated");
      toast(`Order ${symbol}: ${status}`, "info");
    }
    prevOrderRef.current = lastOrderUpdate;
  }, [lastOrderUpdate, toast]);

  useEffect(() => {
    if (lastRiskAlert && lastRiskAlert !== prevAlertRef.current) {
      const message = String(lastRiskAlert?.message ?? "New risk alert");
      toast(message, "error");
    }
    prevAlertRef.current = lastRiskAlert;
  }, [lastRiskAlert, toast]);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
  }, [theme]);

  return (
    <ThemeContext.Provider value={{ theme, setTheme }}>
    <AssetClassContext.Provider value={{ assetClass, setAssetClass }}>
    <SystemEventsContext.Provider value={systemEvents}>
    <div className="flex h-screen">
      {/* Mobile hamburger button */}
      <button
        className="fixed left-4 top-4 z-40 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-2 md:hidden"
        aria-label="Toggle navigation"
        onClick={() => setSidebarOpen(!sidebarOpen)}
      >
        {sidebarOpen ? <X size={20} /> : <Menu size={20} />}
      </button>
      {/* Mobile backdrop */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 z-20 bg-black/50 md:hidden"
          onClick={() => setSidebarOpen(false)}
          data-testid="sidebar-backdrop"
        />
      )}
      <nav aria-label="Main navigation" className={`fixed inset-y-0 left-0 z-30 flex w-56 flex-col border-r border-[var(--color-border)] bg-[var(--color-surface)] p-4 transition-transform md:relative md:translate-x-0 ${sidebarOpen ? "translate-x-0" : "-translate-x-full"}`}>
        <h1 className="mb-4 text-xl font-bold text-[var(--color-primary)]">
          A1SI-AITP
        </h1>
        <div className="mb-4">
          <AssetClassSelector />
        </div>
        <ul role="list" className="flex flex-1 flex-col gap-1">
          {navItems.map(({ to, icon: Icon, label }) => (
            <li key={to}>
              <NavLink
                to={to}
                end={to === "/"}
                onClick={() => setSidebarOpen(false)}
                className={({ isActive }) =>
                  `flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors ${
                    isActive
                      ? "bg-[var(--color-primary)] text-white"
                      : "text-[var(--color-text-muted)] hover:bg-[var(--color-bg)] hover:text-[var(--color-text)]"
                  }`
                }
              >
                <Icon size={18} />
                {label}
              </NavLink>
            </li>
          ))}
        </ul>
        <EmergencyStopButton isHalted={isHalted} />
        <div className="mt-auto border-t border-[var(--color-border)] pt-4">
          <div className="mb-2">
            <ConnectionStatus
              isConnected={isConnected}
              isReconnecting={isReconnecting}
              reconnectAttempt={reconnectAttempt}
              onReconnect={reconnect}
            />
          </div>
          <ThemeToggle />
          {username && (
            <p className="mb-2 truncate px-3 text-xs text-[var(--color-text-muted)]">
              {username}
            </p>
          )}
          <button
            aria-label="Sign out"
            onClick={onLogout}
            className="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm text-[var(--color-text-muted)] transition-colors hover:bg-[var(--color-bg)] hover:text-red-400"
          >
            <LogOut size={18} />
            Sign Out
          </button>
        </div>
      </nav>
      <main role="main" className="flex-1 overflow-auto">
        {/* Global halt banner */}
        {isHalted && (
          <div role="alert" className="border-b border-red-500/50 bg-red-500/10 px-6 py-2 text-center text-sm font-bold text-red-400">
            TRADING HALTED{haltReason ? `: ${haltReason}` : ""}
          </div>
        )}
        {/* Reconnecting banner */}
        {isReconnecting && (
          <div role="status" className="border-b border-amber-500/50 bg-amber-500/10 px-6 py-2 text-center text-sm text-amber-400">
            WebSocket reconnecting... (attempt {reconnectAttempt})
          </div>
        )}
        <div className="p-6">
          <ErrorBoundary>
            <Outlet key={assetClass} />
          </ErrorBoundary>
        </div>
      </main>
    </div>
    </SystemEventsContext.Provider>
    </AssetClassContext.Provider>
    </ThemeContext.Provider>
  );
}
