import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Route, Routes } from "react-router";
import AppLayout from "./components/AppLayout";
import Dashboard from "./pages/Dashboard";
import Trading from "./pages/Trading";
import Backtest from "./pages/Backtest";
import Scanner from "./pages/Scanner";
import Audit from "./pages/Audit";
import "./index.css";

const queryClient = new QueryClient();

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route element={<AppLayout />}>
            <Route index element={<Dashboard />} />
            <Route path="trade" element={<Trading />} />
            <Route path="backtest" element={<Backtest />} />
            <Route path="scanner" element={<Scanner />} />
            <Route path="audit" element={<Audit />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
