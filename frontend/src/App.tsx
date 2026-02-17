import { Routes, Route, Navigate } from "react-router-dom";
import { Layout } from "./components/Layout";
import { Login } from "./pages/Login";
import { Dashboard } from "./pages/Dashboard";
import { PortfolioPage } from "./pages/Portfolio";
import { MarketAnalysis } from "./pages/MarketAnalysis";
import { Trading } from "./pages/Trading";
import { DataManagement } from "./pages/DataManagement";
import { Screening } from "./pages/Screening";
import { RiskManagement } from "./pages/RiskManagement";
import { Backtesting } from "./pages/Backtesting";
import { RegimeDashboard } from "./pages/RegimeDashboard";
import { PaperTrading } from "./pages/PaperTrading";
import { Settings } from "./pages/Settings";
import { useAuth } from "./hooks/useAuth";

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
        <Route path="/" element={<Dashboard />} />
        <Route path="/portfolio" element={<PortfolioPage />} />
        <Route path="/market" element={<MarketAnalysis />} />
        <Route path="/trading" element={<Trading />} />
        <Route path="/data" element={<DataManagement />} />
        <Route path="/screening" element={<Screening />} />
        <Route path="/risk" element={<RiskManagement />} />
        <Route path="/regime" element={<RegimeDashboard />} />
        <Route path="/backtest" element={<Backtesting />} />
        <Route path="/paper-trading" element={<PaperTrading />} />
        <Route path="/settings" element={<Settings />} />
      </Route>
    </Routes>
  );
}
