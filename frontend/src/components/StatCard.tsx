import type { ReactNode } from "react";

// An accessible KPI tile. Uses a <figure>/<figcaption> so screen readers announce the
// label with the value, and colors meet AA contrast in both themes.
export function StatCard({
  label,
  value,
  hint,
  children,
}: {
  label: string;
  value: ReactNode;
  hint?: string;
  children?: ReactNode;
}) {
  return (
    <figure className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-700 dark:bg-slate-900">
      <figcaption className="text-sm font-medium text-slate-600 dark:text-slate-300">
        {label}
      </figcaption>
      <div className="mt-1 text-3xl font-bold text-slate-900 dark:text-slate-50">{value}</div>
      {hint && <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{hint}</p>}
      {children}
    </figure>
  );
}
