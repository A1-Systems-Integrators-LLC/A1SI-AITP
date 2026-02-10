import { Routes, Route } from "react-router-dom";
import { Layout } from "./components/Layout";
import { Dashboard } from "./pages/Dashboard";
import { PortfolioPage } from "./pages/Portfolio";
import { MarketAnalysis } from "./pages/MarketAnalysis";
import { Trading } from "./pages/Trading";
import { Settings } from "./pages/Settings";

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<Dashboard />} />
        <Route path="/portfolio" element={<PortfolioPage />} />
        <Route path="/market" element={<MarketAnalysis />} />
        <Route path="/trading" element={<Trading />} />
        <Route path="/settings" element={<Settings />} />
      </Route>
    </Routes>
  );
}
