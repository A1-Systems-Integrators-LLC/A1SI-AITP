import { lazy, Suspense } from "react";
import { Routes, Route, Navigate } from "react-router-dom";
import { Layout } from "./components/Layout";
import { Login } from "./pages/Login";
import { useAuth } from "./hooks/useAuth";

// Lazy-loaded pages — Vite creates separate chunks automatically
const Dashboard = lazy(() => import("./pages/Dashboard").then(m => ({ default: m.Dashboard })));
const PortfolioPage = lazy(() => import("./pages/Portfolio").then(m => ({ default: m.PortfolioPage })));
const MarketAnalysis = lazy(() => import("./pages/MarketAnalysis").then(m => ({ default: m.MarketAnalysis })));
const Trading = lazy(() => import("./pages/Trading").then(m => ({ default: m.Trading })));
const DataManagement = lazy(() => import("./pages/DataManagement").then(m => ({ default: m.DataManagement })));
const Screening = lazy(() => import("./pages/Screening").then(m => ({ default: m.Screening })));
const RiskManagement = lazy(() => import("./pages/RiskManagement").then(m => ({ default: m.RiskManagement })));
const Backtesting = lazy(() => import("./pages/Backtesting").then(m => ({ default: m.Backtesting })));
const RegimeDashboard = lazy(() => import("./pages/RegimeDashboard").then(m => ({ default: m.RegimeDashboard })));
const PaperTrading = lazy(() => import("./pages/PaperTrading").then(m => ({ default: m.PaperTrading })));
const Settings = lazy(() => import("./pages/Settings").then(m => ({ default: m.Settings })));
const MLModels = lazy(() => import("./pages/MLModels").then(m => ({ default: m.MLModels })));
const Scheduler = lazy(() => import("./pages/Scheduler").then(m => ({ default: m.Scheduler })));
const Workflows = lazy(() => import("./pages/Workflows").then(m => ({ default: m.Workflows })));
const MarketOpportunities = lazy(() => import("./pages/MarketOpportunities").then(m => ({ default: m.MarketOpportunities })));
const ConvictionDashboard = lazy(() => import("./pages/ConvictionDashboard").then(m => ({ default: m.ConvictionDashboard })));

function PageLoader() {
  return (
    <div className="space-y-4 p-6" data-testid="page-loader">
      <div className="h-8 w-48 animate-pulse rounded bg-[var(--color-border)]" />
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        {[1, 2, 3, 4].map((i) => (
          <div
            key={i}
            className="h-24 animate-pulse rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4"
          >
            <div className="mb-2 h-3 w-1/3 rounded bg-[var(--color-border)]" />
            <div className="h-6 w-2/3 rounded bg-[var(--color-border)]" />
          </div>
        ))}
      </div>
      <div className="h-64 animate-pulse rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)]" />
    </div>
  );
}

export default function App() {
  const { isAuthenticated, isLoading, login, logout, username } = useAuth();

  if (isLoading) {
    return (
      <div className="flex h-screen items-center justify-center bg-[var(--color-bg)]">
        <div className="text-[var(--color-text-muted)]">Loading...</div>
      </div>
    );
  }

  return (
    <Routes>
      <Route
        path="/login"
        element={
          isAuthenticated ? (
            <Navigate to="/" replace />
          ) : (
            <Login onLogin={login} />
          )
        }
      />
      <Route
        element={
          isAuthenticated ? (
            <Layout onLogout={logout} username={username} />
          ) : (
            <Navigate to="/login" replace />
          )
        }
      >
        <Route path="/" element={<Suspense fallback={<PageLoader />}><Dashboard /></Suspense>} />
        <Route path="/portfolio" element={<Suspense fallback={<PageLoader />}><PortfolioPage /></Suspense>} />
        <Route path="/market" element={<Suspense fallback={<PageLoader />}><MarketAnalysis /></Suspense>} />
        <Route path="/trading" element={<Suspense fallback={<PageLoader />}><Trading /></Suspense>} />
        <Route path="/data" element={<Suspense fallback={<PageLoader />}><DataManagement /></Suspense>} />
        <Route path="/screening" element={<Suspense fallback={<PageLoader />}><Screening /></Suspense>} />
        <Route path="/risk" element={<Suspense fallback={<PageLoader />}><RiskManagement /></Suspense>} />
        <Route path="/regime" element={<Suspense fallback={<PageLoader />}><RegimeDashboard /></Suspense>} />
        <Route path="/backtest" element={<Suspense fallback={<PageLoader />}><Backtesting /></Suspense>} />
        <Route path="/paper-trading" element={<Suspense fallback={<PageLoader />}><PaperTrading /></Suspense>} />
        <Route path="/ml" element={<Suspense fallback={<PageLoader />}><MLModels /></Suspense>} />
        <Route path="/scheduler" element={<Suspense fallback={<PageLoader />}><Scheduler /></Suspense>} />
        <Route path="/workflows" element={<Suspense fallback={<PageLoader />}><Workflows /></Suspense>} />
        <Route path="/opportunities" element={<Suspense fallback={<PageLoader />}><MarketOpportunities /></Suspense>} />
        <Route path="/conviction" element={<Suspense fallback={<PageLoader />}><ConvictionDashboard /></Suspense>} />
        <Route path="/settings" element={<Suspense fallback={<PageLoader />}><Settings /></Suspense>} />
      </Route>
    </Routes>
  );
}
