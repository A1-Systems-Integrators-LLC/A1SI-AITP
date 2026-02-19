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
  Settings,
  LogOut,
} from "lucide-react";
import { EmergencyStopButton } from "./EmergencyStopButton";
import { ErrorBoundary } from "./ErrorBoundary";
import { useSystemEvents } from "../hooks/useSystemEvents";

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
  { to: "/settings", icon: Settings, label: "Settings" },
];

interface LayoutProps {
  onLogout: () => Promise<void>;
  username: string | null;
}

export function Layout({ onLogout, username }: LayoutProps) {
  const { isHalted, haltReason } = useSystemEvents();

  return (
    <div className="flex h-screen">
      <nav className="flex w-56 flex-col border-r border-[var(--color-border)] bg-[var(--color-surface)] p-4">
        <h1 className="mb-8 text-xl font-bold text-[var(--color-primary)]">
          CryptoInvestor
        </h1>
        <ul className="flex flex-1 flex-col gap-1">
          {navItems.map(({ to, icon: Icon, label }) => (
            <li key={to}>
              <NavLink
                to={to}
                end={to === "/"}
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
          {username && (
            <p className="mb-2 truncate px-3 text-xs text-[var(--color-text-muted)]">
              {username}
            </p>
          )}
          <button
            onClick={onLogout}
            className="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm text-[var(--color-text-muted)] transition-colors hover:bg-[var(--color-bg)] hover:text-red-400"
          >
            <LogOut size={18} />
            Sign Out
          </button>
        </div>
      </nav>
      <main className="flex-1 overflow-auto">
        {/* Global halt banner */}
        {isHalted && (
          <div className="border-b border-red-500/50 bg-red-500/10 px-6 py-2 text-center text-sm font-bold text-red-400">
            TRADING HALTED{haltReason ? `: ${haltReason}` : ""}
          </div>
        )}
        <div className="p-6">
          <ErrorBoundary>
            <Outlet />
          </ErrorBoundary>
        </div>
      </main>
    </div>
  );
}
