import { useQuery } from "@tanstack/react-query";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";
import { getCost } from "@/api/client";
import { StatCard } from "@/components/StatCard";

const usd = (micros: number) => `$${(micros / 1e6).toFixed(4)}`;

// Cost Analytics view (PRD §14) with a Recharts bar chart. The chart is decorative for
// screen readers; the same data is provided in an accessible table below.
export function CostAnalytics() {
  const { data, isLoading, error } = useQuery({ queryKey: ["cost"], queryFn: getCost });
  if (isLoading) return <p role="status">Loading cost analytics…</p>;
  if (error || !data) return <p role="alert">Could not load cost analytics.</p>;

  const chartData = data.by_repo.map((r) => ({ repo: r.repo, usd: r.cost_micros / 1e6 }));

  return (
    <section aria-labelledby="cost-heading">
      <h2 id="cost-heading" className="text-xl font-semibold">
        Cost Analytics
      </h2>
      <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-3">
        <StatCard label="Total cost" value={usd(data.total_cost_micros)} />
        <StatCard label="Total tokens" value={data.total_tokens.toLocaleString()} />
        <StatCard
          label="Cost / review"
          value={usd(data.reviews ? data.total_cost_micros / data.reviews : 0)}
        />
      </div>

      <div className="mt-6 h-64" role="img" aria-label="Cost by repository bar chart">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" className="stroke-slate-200 dark:stroke-slate-700" />
            <XAxis dataKey="repo" tick={{ fontSize: 12 }} />
            <YAxis tickFormatter={(v) => `$${v}`} tick={{ fontSize: 12 }} />
            <Tooltip formatter={(v: number) => `$${v.toFixed(4)}`} />
            <Bar dataKey="usd" fill="#2563eb" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>

      <table className="mt-4 w-full text-left text-sm">
        <caption className="sr-only">Cost by repository</caption>
        <thead>
          <tr className="border-b border-slate-300 dark:border-slate-700">
            <th scope="col" className="py-2 pr-4">Repository</th>
            <th scope="col" className="py-2 pr-4">Cost</th>
          </tr>
        </thead>
        <tbody>
          {data.by_repo.map((r) => (
            <tr key={r.repo} className="border-b border-slate-100 dark:border-slate-800">
              <th scope="row" className="py-2 pr-4 font-normal">{r.repo}</th>
              <td className="py-2 pr-4">{usd(r.cost_micros)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
