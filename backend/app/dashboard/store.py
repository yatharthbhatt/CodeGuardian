"""Dashboard analytics store (PRD §14).

Records a compact :class:`ReviewSummary` per review and serves the aggregations behind the
dashboard views (overview, open PRs, risk heatmap, agent decisions, cost, latency, quality
timeline, tech debt). **Tenant-scoped by construction** — all data lives under
``self._data[tenant_id]`` so one tenant can never read another's analytics.

In-memory here; the durable production store is Postgres (the ``reviews``/``findings``
tables, PRD §10). This is intentionally read-model shaped for fast dashboard queries.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from app.review.graph import ReviewResult


@dataclass
class AgentDecision:
    agent: str
    dimension: str
    severity: str
    gate: str
    title: str
    weighted_confidence: float
    file_path: str | None
    line: int | None


@dataclass
class ReviewSummary:
    review_id: str
    repo: str
    pr_number: int
    head_sha: str
    overall: float
    risk: dict[str, float]
    blocking: bool
    auto_approved: bool
    tokens: int
    cost_micros: int
    latency_ms: int
    decisions: list[AgentDecision] = field(default_factory=list)
    state: str = "open"
    created_at: dt.datetime = field(default_factory=lambda: dt.datetime.now(dt.UTC))


class AnalyticsStore(Protocol):
    def record(self, tenant_id: str, summary: ReviewSummary) -> None: ...
    def repo_overview(self, tenant_id: str) -> list[dict[str, Any]]: ...
    def open_prs(self, tenant_id: str, repo: str | None = None) -> list[dict[str, Any]]: ...
    def risk_heatmap(self, tenant_id: str, repo: str) -> list[dict[str, Any]]: ...
    def agent_decisions(self, tenant_id: str, review_id: str) -> list[dict[str, Any]]: ...
    def cost_analytics(self, tenant_id: str) -> dict[str, Any]: ...
    def latency(self, tenant_id: str) -> dict[str, Any]: ...
    def quality_timeline(self, tenant_id: str, repo: str) -> list[dict[str, Any]]: ...
    def tech_debt(self, tenant_id: str, repo: str) -> dict[str, Any]: ...


_SEVERITY_SCORE = {"info": 0, "low": 1, "medium": 3, "high": 7, "critical": 12}


class InMemoryAnalyticsStore:
    def __init__(self) -> None:
        self._data: dict[str, list[ReviewSummary]] = defaultdict(list)

    def record(self, tenant_id: str, summary: ReviewSummary) -> None:
        self._data[tenant_id].append(summary)

    def _all(self, tenant_id: str) -> list[ReviewSummary]:
        return self._data.get(tenant_id, [])

    def _latest_per_pr(self, tenant_id: str, repo: str | None = None) -> list[ReviewSummary]:
        latest: dict[tuple[str, int], ReviewSummary] = {}
        for s in self._all(tenant_id):
            if repo is not None and s.repo != repo:
                continue
            key = (s.repo, s.pr_number)
            if key not in latest or s.created_at >= latest[key].created_at:
                latest[key] = s
        return list(latest.values())

    def repo_overview(self, tenant_id: str) -> list[dict[str, Any]]:
        by_repo: dict[str, list[ReviewSummary]] = defaultdict(list)
        for s in self._all(tenant_id):
            by_repo[s.repo].append(s)
        out = []
        for repo, summaries in sorted(by_repo.items()):
            latest = self._latest_per_pr(tenant_id, repo)
            avg = round(sum(s.overall for s in summaries) / len(summaries), 1)
            out.append(
                {
                    "repo": repo,
                    "reviews": len(summaries),
                    "avg_overall": avg,
                    "open_prs": sum(1 for s in latest if s.state == "open"),
                }
            )
        return out

    def open_prs(self, tenant_id: str, repo: str | None = None) -> list[dict[str, Any]]:
        return [
            {
                "repo": s.repo,
                "pr_number": s.pr_number,
                "overall": s.overall,
                "blocking": s.blocking,
                "auto_approved": s.auto_approved,
                "review_id": s.review_id,
            }
            for s in self._latest_per_pr(tenant_id, repo)
            if s.state == "open"
        ]

    def risk_heatmap(self, tenant_id: str, repo: str) -> list[dict[str, Any]]:
        by_file: dict[str, int] = defaultdict(int)
        counts: dict[str, int] = defaultdict(int)
        for s in self._latest_per_pr(tenant_id, repo):
            for d in s.decisions:
                if d.file_path is None:
                    continue
                by_file[d.file_path] += _SEVERITY_SCORE.get(d.severity, 0)
                counts[d.file_path] += 1
        return sorted(
            ({"file": f, "risk": score, "findings": counts[f]} for f, score in by_file.items()),
            key=lambda r: r["risk"],
            reverse=True,
        )

    def agent_decisions(self, tenant_id: str, review_id: str) -> list[dict[str, Any]]:
        for s in self._all(tenant_id):
            if s.review_id == review_id:
                return [vars(d) for d in s.decisions]
        return []

    def cost_analytics(self, tenant_id: str) -> dict[str, Any]:
        summaries = self._all(tenant_id)
        by_repo: dict[str, int] = defaultdict(int)
        for s in summaries:
            by_repo[s.repo] += s.cost_micros
        return {
            "total_cost_micros": sum(s.cost_micros for s in summaries),
            "total_tokens": sum(s.tokens for s in summaries),
            "reviews": len(summaries),
            "by_repo": [{"repo": r, "cost_micros": c} for r, c in sorted(by_repo.items())],
        }

    def latency(self, tenant_id: str) -> dict[str, Any]:
        vals = sorted(s.latency_ms for s in self._all(tenant_id))
        if not vals:
            return {"count": 0, "avg_ms": 0, "p50_ms": 0, "max_ms": 0}
        return {
            "count": len(vals),
            "avg_ms": round(sum(vals) / len(vals)),
            "p50_ms": vals[len(vals) // 2],
            "max_ms": vals[-1],
        }

    def quality_timeline(self, tenant_id: str, repo: str) -> list[dict[str, Any]]:
        return [
            {"ts": s.created_at.isoformat(), "overall": s.overall, "pr": s.pr_number}
            for s in sorted(
                (s for s in self._all(tenant_id) if s.repo == repo),
                key=lambda s: s.created_at,
            )
        ]

    def tech_debt(self, tenant_id: str, repo: str) -> dict[str, Any]:
        latest = self._latest_per_pr(tenant_id, repo)
        if not latest:
            return {"avg_tech_debt": 100.0, "hotspots": []}
        avg = round(sum(s.risk.get("tech_debt", 100.0) for s in latest) / len(latest), 1)
        return {"avg_tech_debt": avg, "hotspots": self.risk_heatmap(tenant_id, repo)[:10]}


def summarize(result: ReviewResult, *, latency_ms: int = 0, state: str = "open") -> ReviewSummary:
    """Build a :class:`ReviewSummary` from a completed review."""
    decisions = [
        AgentDecision(
            agent=i.finding.agent,
            dimension=i.finding.dimension.value,
            severity=i.finding.severity.value,
            gate=i.gate.value,
            title=i.finding.title,
            weighted_confidence=round(i.weighted_confidence, 3),
            file_path=i.finding.file_path,
            line=i.finding.line,
        )
        for i in result.consensus.items
    ]
    return ReviewSummary(
        review_id=str(uuid.uuid4()),
        repo=result.pr.repo_full_name,
        pr_number=result.pr.number,
        head_sha=result.pr.head_sha,
        overall=result.risk.get("overall", 0.0),
        risk=result.risk,
        blocking=result.consensus.blocking,
        auto_approved=result.auto_approved,
        tokens=result.tokens_used,
        cost_micros=result.cost_micros,
        latency_ms=latency_ms,
        decisions=decisions,
        state=state,
    )
