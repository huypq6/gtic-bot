import { useEffect } from "react";
import { NavLink, Outlet } from "react-router";
import { Moon, Sun } from "lucide-react";
import { useWsStore } from "../lib/ws";
import { useTheme } from "../lib/theme";
import FeedBanner from "./FeedBanner";

export default function AppLayout() {
  const connect = useWsStore((s) => s.connect);
  const feed = useWsStore((s) => s.feed);
  const theme = useTheme((s) => s.theme);
  const toggleTheme = useTheme((s) => s.toggle);

  useEffect(() => {
    connect();
  }, [connect]);

  return (
    <div className="flex h-screen flex-col bg-bg text-text">
      <header className="flex items-center justify-between border-b border-border bg-surface px-4 py-2">
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2">
            <img src="/logo.png" alt="GTIC" className="h-8 w-8 rounded-lg object-contain" />
            <span className="font-semibold">GTIC Trading Bot</span>
          </div>
          <nav className="flex items-center gap-1 text-sm">
            <Tab to="/">Chart</Tab>
            <Tab to="/trade">Trading</Tab>
            <Tab to="/orders">Orders</Tab>
            <Tab to="/backtest">Backtest</Tab>
            <Tab to="/scanner">Scanner</Tab>
            <Tab to="/audit">Audit</Tab>
          </nav>
        </div>
        <div className="flex items-center gap-3 text-xs">
          <button
            onClick={toggleTheme}
            title={theme === "dark" ? "Chuyển sáng" : "Chuyển tối"}
            className="rounded-md p-1.5 text-muted hover:bg-surface-2 hover:text-text"
          >
            {theme === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
          </button>
          <div className="flex items-center gap-2">
            <span
              className={`h-2 w-2 rounded-full ${
                feed === "OK" ? "bg-up" : feed === "DOWN" ? "bg-down" : "bg-primary"
              }`}
            />
            <span className="text-muted">{feed}</span>
          </div>
        </div>
      </header>

      <FeedBanner />
      <Outlet />
    </div>
  );
}

function Tab({ to, children }: { to: string; children: React.ReactNode }) {
  return (
    <NavLink
      to={to}
      end={to === "/"}
      className={({ isActive }) =>
        `rounded-md px-3 py-1.5 font-medium transition ${
          isActive ? "bg-surface-2 text-text" : "text-muted hover:bg-surface-2 hover:text-text"
        }`
      }
    >
      {children}
    </NavLink>
  );
}
