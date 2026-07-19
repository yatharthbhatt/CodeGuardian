"""Agent detection tests — deterministic-first (PRD §5, rule #8)."""

from __future__ import annotations

import pytest
from app.agents.architecture import ArchitectureAgent
from app.agents.base import AgentContext
from app.agents.documentation import DocumentationAgent
from app.agents.security import SecurityAgent
from app.domain.findings import Severity

from tests.conftest import diff_from_added, make_pr


def _ctx(path: str, lines: list[str]) -> AgentContext:
    # No router → deterministic-only (LLM enrichment disabled), so assertions are stable.
    return AgentContext(pr=make_pr(), diff=diff_from_added(path, lines), router=None)


async def test_security_detects_hardcoded_secret_without_leaking_value() -> None:
    secret = "ghp_" + "Z" * 36
    findings = await SecurityAgent().run(_ctx("app/s.py", [f"TOKEN = '{secret}'"]))
    secret_findings = [f for f in findings if f.category == "hardcoded-secret"]
    assert secret_findings
    assert secret_findings[0].severity is Severity.CRITICAL
    # The secret value must never appear in the finding output.
    assert all(secret not in f.message for f in findings)


async def test_security_detects_eval_and_sql_injection() -> None:
    findings = await SecurityAgent().run(
        _ctx(
            "app/s.py",
            [
                "eval(user_input)",
                'cursor.execute(f"SELECT * FROM t WHERE id={uid}")',
            ],
        )
    )
    cats = {f.category for f in findings}
    assert "dangerous-eval" in cats
    assert "sql-injection" in cats
    assert all(f.cwe and f.cwe.startswith("CWE-") for f in findings if f.cwe)


async def test_security_weak_hash_and_verify_false() -> None:
    findings = await SecurityAgent().run(
        _ctx("app/s.py", ["h = md5(x)", "requests.get(u, verify=False)"])
    )
    cats = {f.category for f in findings}
    assert "weak-hash" in cats
    assert "tls-verification-disabled" in cats


async def test_security_clean_code_has_no_findings() -> None:
    findings = await SecurityAgent().run(_ctx("app/s.py", ["def add(a, b):", "    return a + b"]))
    assert findings == []


async def test_architecture_flags_broad_except_and_wildcard_import() -> None:
    findings = await ArchitectureAgent().run(
        _ctx("app/a.py", ["from os import *", "try:", "    pass", "except:", "    pass"])
    )
    cats = {f.category for f in findings}
    assert "wildcard-import" in cats
    assert "broad-except" in cats


async def test_documentation_flags_missing_docstring_but_not_documented() -> None:
    undocumented = await DocumentationAgent().run(
        _ctx("app/d.py", ["def public_api():", "    return 1"])
    )
    assert any(f.category == "missing-docstring" for f in undocumented)

    documented = await DocumentationAgent().run(
        _ctx("app/d.py", ["def public_api():", '    """Does a thing."""', "    return 1"])
    )
    assert not any(f.category == "missing-docstring" for f in documented)


async def test_documentation_ignores_private_functions() -> None:
    findings = await DocumentationAgent().run(_ctx("app/d.py", ["def _private():", "    return 1"]))
    assert not any(f.category == "missing-docstring" for f in findings)


@pytest.mark.parametrize("agent", [SecurityAgent(), ArchitectureAgent(), DocumentationAgent()])
async def test_every_finding_has_full_explanation(agent) -> None:  # type: ignore[no-untyped-def]
    findings = await agent.run(_ctx("app/s.py", ["eval(x)", "def public_api():"]))
    for f in findings:
        assert f.explanation.why
        assert f.explanation.impact
        assert 0.0 <= f.confidence <= 1.0
