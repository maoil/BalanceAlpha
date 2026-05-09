import { useMemo, useState } from "react";

import { AppShell, type PageKey } from "./components/AppShell";
import { BacktestsPage } from "./pages/BacktestsPage";
import { DashboardPage } from "./pages/DashboardPage";
import { InstrumentsPage } from "./pages/InstrumentsPage";
import { LogsPage } from "./pages/LogsPage";
import { ManualFundOrdersPage } from "./pages/ManualFundOrdersPage";
import { PositionsPage } from "./pages/PositionsPage";
import { SettingsPage } from "./pages/SettingsPage";
import { SignalsPage } from "./pages/SignalsPage";
import { TradesPage } from "./pages/TradesPage";

export default function App() {
  const [activePage, setActivePage] = useState<PageKey>("dashboard");
  const page = useMemo(() => renderPage(activePage), [activePage]);

  return (
    <AppShell activePage={activePage} onNavigate={setActivePage}>
      {page}
    </AppShell>
  );
}

function renderPage(page: PageKey) {
  switch (page) {
    case "instruments":
      return <InstrumentsPage />;
    case "positions":
      return <PositionsPage />;
    case "trades":
      return <TradesPage />;
    case "orders":
      return <ManualFundOrdersPage />;
    case "signals":
      return <SignalsPage />;
    case "settings":
      return <SettingsPage />;
    case "backtests":
      return <BacktestsPage />;
    case "logs":
      return <LogsPage />;
    case "dashboard":
    default:
      return <DashboardPage />;
  }
}
