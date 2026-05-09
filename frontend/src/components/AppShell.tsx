import {
  Activity,
  BarChart3,
  Boxes,
  ClipboardList,
  Gauge,
  LineChart,
  ListChecks,
  ReceiptText,
  Settings,
  WalletCards,
} from "lucide-react";
import type { ReactNode } from "react";

export type PageKey =
  | "dashboard"
  | "instruments"
  | "positions"
  | "trades"
  | "orders"
  | "signals"
  | "settings"
  | "backtests"
  | "logs";

type NavigationItem = {
  key: PageKey;
  label: string;
  icon: ReactNode;
};

const items: NavigationItem[] = [
  { key: "dashboard", label: "仪表盘", icon: <Gauge /> },
  { key: "instruments", label: "产品", icon: <Boxes /> },
  { key: "positions", label: "持仓", icon: <WalletCards /> },
  { key: "trades", label: "交易", icon: <ReceiptText /> },
  { key: "orders", label: "确认", icon: <ClipboardList /> },
  { key: "signals", label: "策略", icon: <Activity /> },
  { key: "settings", label: "参数", icon: <Settings /> },
  { key: "backtests", label: "回测", icon: <LineChart /> },
  { key: "logs", label: "日志", icon: <ListChecks /> },
];

export function AppShell({
  activePage,
  onNavigate,
  children,
}: {
  activePage: PageKey;
  onNavigate: (page: PageKey) => void;
  children: ReactNode;
}) {
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand" role="banner">
          <BarChart3 aria-hidden="true" />
          <div>
            <strong>BalanceAlpha</strong>
            <span>投资执行台</span>
          </div>
        </div>
        <nav className="nav" aria-label="主导航">
          {items.map((item) => (
            <button
              className={item.key === activePage ? "nav-item active" : "nav-item"}
              key={item.key}
              onClick={() => onNavigate(item.key)}
              type="button"
              title={item.label}
            >
              {item.icon}
              <span>{item.label}</span>
            </button>
          ))}
        </nav>
      </aside>
      <main className="main-surface">{children}</main>
    </div>
  );
}
