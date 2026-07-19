"""CLI: `python -m evals` → run the harness and print the report."""

from __future__ import annotations

import asyncio
import json

from evals.runner import run_evals


def main() -> None:
    report = asyncio.run(run_evals())
    print(json.dumps(report.as_dict(), indent=2))
    print("\nPer-case:")
    for c in report.cases:
        status = "ok" if c.expected == c.predicted else "MISS"
        print(f"  [{status}] {c.id}: expected={sorted(c.expected)} predicted={sorted(c.predicted)}")


if __name__ == "__main__":
    main()
