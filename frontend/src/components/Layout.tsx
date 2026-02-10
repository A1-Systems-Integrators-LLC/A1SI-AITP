import { NavLink, Outlet } from "react-router-dom";
import {
  LayoutDashboard,
  Wallet,
  BarChart3,
  ArrowLeftRight,
  Settings,
} from "lucide-react";

const navItems = [
  { to: "/", icon: LayoutDashboard, label: "Dashboard" },
  { to: "/portfolio", icon: Wallet, label: "Portfolio" },
  { to: "/market", icon: BarChart3, label: "Market" },
  { to: "/trading", icon: ArrowLeftRight, label: "Trading" },
  { to: "/settings", icon: Settings, label: "Settings" },
];

export function Layout() {
  return (
    <div className="flex h-screen">
      <nav className="flex w-56 flex-col border-r border-[var(--color-border)] bg-[var(--color-surface)] p-4">
        <h1 className="mb-8 text-xl font-bold text-[var(--color-primary)]">
          CryptoInvestor
        </h1>
        <ul className="flex flex-col gap-1">
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
      </nav>
      <main className="flex-1 overflow-auto p-6">
        <Outlet />
      </main>
    </div>
  );
}
