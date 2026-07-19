import { useQuery } from "@tanstack/react-query";
import { getOverview } from "@/api/client";
import { StatCard } from "@/components/StatCard";

// Repository Overview view (PRD §14). Data table is keyboard-navigable and has a caption
// + scope'd headers for screen readers.
export function Overview() {
  const { data, isLoading, error } = useQuery({ queryKey: ["overview"], queryFn: getOverview });

  if (isLoading) return <p role="status">Loading repositories…</p>;
  if (error) return <p role="alert">Could not load repositories.</p>;

  const repos = data ?? [];
  const totalReviews = repos.reduce((n, r) => n + r.reviews, 0);
  const openPrs = repos.reduce((n, r) => n + r.open_prs, 0);

  return (
    <section aria-labelledby="overview-heading">
      <h2 id="overview-heading" className="text-xl font-semibold">
        Repository Overview
      </h2>
      <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-3">
        <StatCard label="Repositories" value={repos.length} />
        <StatCard label="Reviews (total)" value={totalReviews} />
        <StatCard label="Open PRs" value={openPrs} />
      </div>

      <div className="mt-6 overflow-x-auto">
        <table className="w-full border-collapse text-left text-sm">
          <caption className="sr-only">Per-repository review summary</caption>
          <thead>
            <tr className="border-b border-slate-300 dark:border-slate-700">
              <th scope="col" className="py-2 pr-4">Repository</th>
              <th scope="col" className="py-2 pr-4">Reviews</th>
              <th scope="col" className="py-2 pr-4">Avg score</th>
              <th scope="col" className="py-2 pr-4">Open PRs</th>
            </tr>
          </thead>
          <tbody>
            {repos.map((r) => (
              <tr key={r.repo} className="border-b border-slate-100 dark:border-slate-800">
                <th scope="row" className="py-2 pr-4 font-normal">{r.repo}</th>
                <td className="py-2 pr-4">{r.reviews}</td>
                <td className="py-2 pr-4">{r.avg_overall}/100</td>
                <td className="py-2 pr-4">{r.open_prs}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
