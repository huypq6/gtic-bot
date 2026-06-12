import { useEffect } from "react";
import { NavLink, Outlet } from "react-router";
import { useWsStore } from "../lib/ws";
import FeedBanner from "./FeedBanner";

export default function AppLayout() {
  const connect = useWsStore((s) => s.connect);
  const feed = useWsStore((s) => s.feed);

  useEffect(() => {
    connect();
  }, [connect]);

  return (
    <div className="flex h-screen flex-col bg-ink-950 text-ink-100">
      <header className="flex items-center justify-between border-b border-ink-700 bg-ink-900 px-4 py-2">
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2">
            <img src="/logo.png" alt="GTIC" className="h-8 w-8 rounded-lg object-contain" />
            <span className="font-semibold">GTIC Trading Bot</span>
          </div>
          <nav className="flex items-center gap-1 text-sm">
            <Tab to="/">Chart</Tab>
            <Tab to="/trade">Trading</Tab>
          </nav>
        </div>
        <div className="flex items-center gap-2 text-xs">
          <span
            className={`h-2 w-2 rounded-full ${
              feed === "OK" ? "bg-up" : feed === "DOWN" ? "bg-down" : "bg-brand-400"
            }`}
          />
          <span className="text-ink-400">{feed}</span>
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
          isActive ? "bg-ink-800 text-ink-100" : "text-ink-400 hover:bg-ink-850 hover:text-ink-100"
        }`
      }
    >
      {children}
    </NavLink>
  );
}
