"""Public "try it" analysis endpoints backing the homepage (offline, no API key).

Runs the deterministic review pipeline over pasted code or a **public** GitHub PR diff and
returns findings + score + auto-fixes. Static analysis only (no code execution). Hardened:
strict input validation, body-size caps, a rate limiter, and **SSRF-safe** PR fetching (the
URL is parsed and the diff URL is rebuilt from owner/repo/number — the user's raw URL is
never fetched).
"""

from __future__ import annotations

import re
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, StringConstraints

from app.domain.findings import Finding
from app.review.diff import AddedLine, FileDiff, NormalizedDiff, parse_unified_diff
from app.review.graph import run_review
from app.review.state import PRMeta

router = APIRouter(prefix="/api/v1/analyze", tags=["analyze"])

_MAX_CODE = 100_000  # 100 KB paste cap
_PR_URL = re.compile(r"^https?://github\.com/([\w.-]{1,100})/([\w.-]{1,100})/pull/(\d{1,12})")


class CodeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    filename: Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)] = (
        "snippet.py"
    )
    code: Annotated[str, StringConstraints(max_length=_MAX_CODE)]


class PrIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    url: Annotated[str, StringConstraints(strip_whitespace=True, max_length=300)]


def _rate_limit(request: Request) -> None:
    limiter = getattr(request.app.state, "analyze_limiter", None)
    if limiter is None:
        return
    client = request.client.host if request.client else "anon"
    if not limiter.allow(client):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "slow down — rate limit")


async def _review(pr: PRMeta, diff: NormalizedDiff) -> dict[str, Any]:
    result = await run_review(pr, diff, use_llm=False)
    patches = {(p.file_path, p.line): p for p in result.patches}

    def _suggestion(f: Finding) -> dict[str, str] | None:
        if f.file_path is None or f.line is None:
            return None
        patch = patches.get((f.file_path, f.line))
        return {"original": patch.original, "fixed": patch.fixed} if patch else None

    findings = [
        {
            "severity": f.severity.value,
            "dimension": f.dimension.value,
            "category": f.category,
            "title": f.title,
            "file": f.file_path,
            "line": f.line,
            "why": f.explanation.why,
            "impact": f.explanation.impact,
            "alternative": f.explanation.alternative,
            "cwe": f.cwe,
            "confidence": round(f.confidence, 2),
            "suggestion": _suggestion(f),
        }
        for f in sorted(result.findings, key=lambda x: -x.severity.weight)
    ]
    verdict = (
        "REQUEST_CHANGES"
        if result.consensus.blocking
        else ("APPROVE" if result.auto_approved else "COMMENT")
    )
    return {
        "overall": result.risk.get("overall", 0.0),
        "verdict": verdict,
        "blocking": result.consensus.blocking,
        "risk": result.risk,
        "findings": findings,
        "counts": {
            "total": len(findings),
            "critical": sum(1 for f in findings if f["severity"] == "critical"),
            "high": sum(1 for f in findings if f["severity"] == "high"),
            "fixes": sum(1 for f in findings if f["suggestion"]),
        },
    }


def _diff_from_code(filename: str, code: str) -> NormalizedDiff:
    lines = code.splitlines()
    return NormalizedDiff(
        files=[
            FileDiff(
                path=filename or "snippet.py",
                is_new_file=True,
                added=[AddedLine(new_line=i + 1, text=t) for i, t in enumerate(lines)],
            )
        ]
    )


def _pr(repo: str = "you/snippet", number: int = 1, title: str = "Pasted snippet") -> PRMeta:
    return PRMeta(
        tenant_id="public",
        repo_full_name=repo,
        number=number,
        title=title,
        body="",
        author="anon",
        head_sha="0" * 40,
        base_sha="0" * 40,
    )


@router.post("/code")
async def analyze_code(body: CodeIn, request: Request) -> dict[str, Any]:
    _rate_limit(request)
    if not body.code.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "no code provided")
    return await _review(_pr(), _diff_from_code(body.filename, body.code))


@router.post("/pr")
async def analyze_pr(body: PrIn, request: Request) -> dict[str, Any]:
    _rate_limit(request)
    m = _PR_URL.match(body.url)
    if not m:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "expected a github.com pull-request URL")
    owner, repo, number = m.group(1), m.group(2), int(m.group(3))
    # SSRF-safe: rebuild the diff URL from validated parts; never fetch the raw input URL.
    diff_url = f"https://github.com/{owner}/{repo}/pull/{number}.diff"

    import httpx

    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as http:
            resp = await http.get(diff_url, headers={"Accept": "text/plain"})
    except httpx.HTTPError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "could not reach GitHub") from exc
    if resp.status_code == 404:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "PR not found or not public")
    if resp.status_code != 200:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "GitHub returned an error")

    diff = parse_unified_diff(resp.text[: 2 * _MAX_CODE])
    return await _review(_pr(f"{owner}/{repo}", number, f"PR #{number}"), diff)
