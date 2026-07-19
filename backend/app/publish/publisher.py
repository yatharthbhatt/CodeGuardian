"""Render a review result into a GitHub PR review + inline comments (PRD §4).

Security note: finding messages can contain snippets of *untrusted* PR code. Before it goes
into PR markdown we sanitize it (escape HTML/backticks, neutralize @mentions) so a crafted
snippet cannot inject HTML, break layout, forge an "approved" banner, or mass-ping people.
"""

from __future__ import annotations

from app.github.client import (
    CheckConclusion,
    GitHubReviewClient,
    ReviewComment,
    ReviewEvent,
    ReviewRequest,
)
from app.patch.generator import SuggestedPatch
from app.review.consensus import ConsensusResult, Gate
from app.review.graph import ReviewResult

_SEVERITY_EMOJI = {
    "critical": "🔴",
    "high": "🟠",
    "medium": "🟡",
    "low": "🔵",
    "info": "⚪",
}


def sanitize(text: str, *, limit: int = 4000) -> str:
    """Neutralize untrusted content for safe embedding in PR markdown."""
    cleaned = (
        text.replace("`", "'")  # no code-fence breakout
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("@", "@​")  # zero-width space defuses @mentions
    )
    return cleaned[:limit]


def build_summary_body(result: ReviewResult) -> str:
    r = result.risk
    c = result.consensus
    lines = [
        "## 🛡️ CodeGuardian AI review",
        "",
        f"**Overall Engineering Score: {r.get('overall', 0)}/100**",
        "",
        "| Dimension | Score |",
        "| --- | --- |",
        f"| Security | {r.get('security', 0)} |",
        f"| Architecture | {r.get('architecture', 0)} |",
        f"| Performance | {r.get('performance', 0)} |",
        f"| Maintainability | {r.get('maintainability', 0)} |",
        f"| Documentation | {r.get('documentation', 0)} |",
        f"| Technical Debt | {r.get('tech_debt', 0)} |",
        "",
        f"**Consensus:** {sanitize(c.reasoning, limit=600)}",
    ]
    if result.auto_approved:
        lines.append("")
        lines.append("> ✅ **Auto-approved:** trivial, low-risk change with a clean review.")
    if result.errors:
        agents = ", ".join(sorted({e.get("agent", "?") for e in result.errors}))
        lines.append("")
        lines.append(f"> ⚠️ Some agents degraded gracefully and were skipped: {agents}.")
    lines.append("")
    lines.append("<sub>Automated review. Every finding includes why/impact/alternative.</sub>")
    return "\n".join(lines)


def build_inline_comments(
    consensus: ConsensusResult, patches: list[SuggestedPatch] | None = None
) -> list[ReviewComment]:
    # Look up an auto-patch by (file, line) so we can append a one-click suggestion.
    by_loc = {(p.file_path, p.line): p for p in (patches or [])}
    comments: list[ReviewComment] = []
    for item in consensus.items:
        if item.gate is Gate.SUPPRESS:
            continue
        f = item.finding
        if f.file_path is None or f.line is None:
            continue
        emoji = _SEVERITY_EMOJI.get(f.severity.value, "•")
        prefix = "" if item.gate is Gate.POST else "<sub>(low-confidence, consider)</sub> "
        refs = f.explanation.references
        parts = [
            f"{prefix}{emoji} **{sanitize(f.title, limit=200)}** "
            f"({f.dimension.value} · {f.severity.value} · "
            f"conf {item.weighted_confidence:.0%})",
            "",
            f"**Why:** {sanitize(f.explanation.why, limit=500)}",
            f"**Impact:** {sanitize(f.explanation.impact, limit=500)}",
        ]
        if f.explanation.alternative:
            parts.append(f"**Alternative:** {sanitize(f.explanation.alternative, limit=500)}")
        if refs:
            parts.append("**References:** " + ", ".join(sanitize(r, limit=200) for r in refs[:3]))
        if f.cwe:
            parts.append(f"**CWE:** {f.cwe}")
        # Auto-patch suggestion (the developer applies it — never auto-applied).
        patch = by_loc.get((f.file_path, f.line))
        if patch is not None:
            parts.append("")
            parts.append("**Suggested fix:**")
            parts.append(patch.suggestion_block())
        parts.append(
            f"<sub>agent: {f.agent} · source: {f.source.value} · "
            f"complexity: {f.explanation.complexity}</sub>"
        )
        comments.append(ReviewComment(path=f.file_path, line=f.line, body="\n".join(parts)))
    return comments


def build_review_request(result: ReviewResult) -> ReviewRequest:
    if result.auto_approved:
        event = ReviewEvent.APPROVE
    elif result.consensus.blocking:
        event = ReviewEvent.REQUEST_CHANGES
    else:
        event = ReviewEvent.COMMENT
    return ReviewRequest(
        repo_full_name=result.pr.repo_full_name,
        pr_number=result.pr.number,
        head_sha=result.pr.head_sha,
        event=event,
        body=build_summary_body(result),
        comments=build_inline_comments(result.consensus, result.patches),
    )


async def publish_review(client: GitHubReviewClient, result: ReviewResult) -> ReviewRequest:
    """Post the review + a status check. Returns the request (useful for logging/tests)."""
    req = build_review_request(result)
    await client.create_review(req)
    conclusion = CheckConclusion.FAILURE if result.consensus.blocking else CheckConclusion.SUCCESS
    await client.create_check_run(
        result.pr.repo_full_name,
        result.pr.head_sha,
        conclusion,
        f"Overall {result.risk.get('overall', 0)}/100 — {len(result.consensus.posted)} issue(s).",
    )
    return req
