import { useState } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider, useTheme } from "@/theme";
import { Overview } from "@/views/Overview";
import { CostAnalytics } from "@/views/CostAnalytics";

const queryClient = new QueryClient();

// The 11 dashboard views (PRD §14). Overview + Cost are implemented in this scaffold;
// the rest follow the same accessible pattern (query hook → table + Recharts).
const VIEWS = [
  { id: "overview", label: "Repository Overview", el: <Overview /> },
  { id: "cost", label: "Cost Analytics", el: <CostAnalytics /> },
  { id: "open-prs", label: "Open PRs" },
  { id: "risk", label: "Risk Heatmap" },
  { id: "agents", label: "Agent Decisions" },
  { id: "latency", label: "Latency" },
  { id: "graph", label: "Knowledge Graph" },
  { id: "debt", label: "Technical Debt" },
  { id: "quality", label: "Quality Timeline" },
  { id: "audit", label: "Audit Log" },
  { id: "settings", label: "Settings" },
] as const;

function ThemeToggle() {
  const { theme, toggle } = useTheme();
  return (
    <button
      type="button"
      onClick={toggle}
      aria-pressed={theme === "dark"}
      className="rounded-md border border-slate-300 px-3 py-1 text-sm dark:border-slate-600"
    >
      {theme === "dark" ? "☀️ Light" : "🌙 Dark"}
    </button>
  );
}

function Shell() {
  const [active, setActive] = useState<string>("overview");
  const view = VIEWS.find((v) => v.id === active);

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 dark:bg-slate-950 dark:text-slate-100">
      <a href="#main" className="skip-link rounded bg-brand px-3 py-2 text-white">
        Skip to content
      </a>
      <header className="flex items-center justify-between border-b border-slate-200 px-6 py-3 dark:border-slate-800">
        <h1 className="text-lg font-bold">🛡️ CodeGuardian AI</h1>
        <ThemeToggle />
      </header>
      <div className="flex">
        <nav aria-label="Dashboard sections" className="w-56 shrink-0 border-r border-slate-200 p-3 dark:border-slate-800">
          <ul className="space-y-1">
            {VIEWS.map((v) => (
              <li key={v.id}>
                <button
                  type="button"
                  onClick={() => setActive(v.id)}
                  aria-current={active === v.id ? "page" : undefined}
                  className={`w-full rounded-md px-3 py-2 text-left text-sm ${
                    active === v.id
                      ? "bg-brand text-white"
                      : "hover:bg-slate-100 dark:hover:bg-slate-800"
                  }`}
                >
                  {v.label}
                </button>
              </li>
            ))}
          </ul>
        </nav>
        <main id="main" className="flex-1 p-6" tabIndex={-1}>
          {view?.el ?? (
            <p className="text-slate-500">
              “{view?.label}” view — wired to <code>/api/v1/dashboard</code> using the same
              accessible query + chart pattern as Overview and Cost Analytics.
            </p>
          )}
        </main>
      </div>
    </div>
  );
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <Shell />
      </ThemeProvider>
    </QueryClientProvider>
  );
}
