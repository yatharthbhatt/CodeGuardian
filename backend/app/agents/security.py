"""Security Agent (PRD §5.1).

Deterministic-first: runs a secret detector and a curated set of dangerous-pattern rules
(stand-ins for Semgrep/Bandit/Gitleaks, which are wired via the sandboxed tool-runner in
later phases), THEN optionally asks the LLM to triage/explain and surface subtler issues.
The LLM is never the sole source of a security claim.
"""

from __future__ import annotations

import re

from app.agents.base import (
    AgentContext,
    DeterministicRule,
    run_llm_enrichment,
    scan_rules,
)
from app.core.security.redaction import scan_secret_types
from app.domain.findings import (
    Dimension,
    Explanation,
    Finding,
    FindingSource,
    Severity,
)

_SYSTEM = (
    "You are a senior application security engineer reviewing a pull request. "
    "Focus on OWASP Top 10, injection, authn/authz, secrets, unsafe deserialization, "
    "SSRF, and insecure configuration. Only report issues you can justify from the diff."
)

_RULES: list[DeterministicRule] = [
    DeterministicRule(
        category="dangerous-eval",
        severity=Severity.HIGH,
        pattern=re.compile(r"\b(eval|exec)\s*\("),
        title="Use of eval/exec on dynamic input",
        why="eval/exec can execute arbitrary code if any input is attacker-influenced.",
        impact="Remote code execution / full compromise.",
        alternative="Parse explicitly (ast.literal_eval, json) or use a safe dispatch table.",
        cwe="CWE-95",
    ),
    DeterministicRule(
        category="shell-injection",
        severity=Severity.HIGH,
        pattern=re.compile(r"shell\s*=\s*True|os\.system\s*\(|subprocess\.\w+\([^)]*shell"),
        title="Shell execution with shell=True / os.system",
        why="Building shell commands from strings enables command injection.",
        impact="Command injection and remote code execution.",
        alternative="Pass an argv list and avoid shell=True.",
        cwe="CWE-78",
    ),
    DeterministicRule(
        category="insecure-deserialization",
        severity=Severity.HIGH,
        pattern=re.compile(r"pickle\.loads?\s*\(|yaml\.load\s*\((?![^)]*Safe)"),
        title="Insecure deserialization",
        why="pickle and yaml.load can construct arbitrary objects from untrusted data.",
        impact="Remote code execution via crafted payloads.",
        alternative="Use json, or yaml.safe_load; never unpickle untrusted data.",
        cwe="CWE-502",
    ),
    DeterministicRule(
        category="sql-injection",
        severity=Severity.HIGH,
        pattern=re.compile(
            r"(?i)(execute|cursor\.execute|query)\s*\(\s*[f\"'].*(select|insert|update|delete).*\{"
        ),
        title="Possible SQL injection via string interpolation",
        why="Interpolating variables into SQL allows injection.",
        impact="Data exfiltration, tampering, or auth bypass.",
        alternative="Use parameterized queries / bound parameters.",
        cwe="CWE-89",
    ),
    DeterministicRule(
        category="weak-hash",
        severity=Severity.MEDIUM,
        pattern=re.compile(r"\b(md5|sha1)\s*\("),
        title="Weak hashing algorithm",
        why="MD5/SHA-1 are broken for security use.",
        impact="Collision/pre-image attacks; weak password or integrity protection.",
        alternative="Use SHA-256+ for integrity; bcrypt/scrypt/argon2 for passwords.",
        cwe="CWE-327",
    ),
    DeterministicRule(
        category="tls-verification-disabled",
        severity=Severity.HIGH,
        pattern=re.compile(r"verify\s*=\s*False|rejectUnauthorized\s*:\s*false"),
        title="TLS certificate verification disabled",
        why="Disabling verification allows man-in-the-middle attacks.",
        impact="Interception of traffic and credentials.",
        alternative="Keep verification on; pin or provide the correct CA bundle.",
        cwe="CWE-295",
    ),
    DeterministicRule(
        category="xss-innerhtml",
        severity=Severity.MEDIUM,
        pattern=re.compile(r"\.innerHTML\s*=|dangerouslySetInnerHTML"),
        title="Potential DOM XSS via innerHTML",
        why="Assigning untrusted data to innerHTML can inject script.",
        impact="Cross-site scripting.",
        alternative="Use textContent or a sanitizer (DOMPurify).",
        cwe="CWE-79",
        languages=frozenset({"javascript", "typescript", "html"}),
    ),
    DeterministicRule(
        category="debug-enabled",
        severity=Severity.MEDIUM,
        pattern=re.compile(r"(?i)\bdebug\s*=\s*True\b"),
        title="Debug mode enabled",
        why="Debug mode can leak stack traces and enable dangerous tooling in production.",
        impact="Information disclosure / RCE via debuggers.",
        alternative="Drive debug from environment config; default to off.",
        cwe="CWE-489",
    ),
]


class SecurityAgent:
    name = "security"
    dimension = Dimension.SECURITY

    async def run(self, ctx: AgentContext) -> list[Finding]:
        findings = scan_rules(ctx.diff, _RULES, agent=self.name, dimension=self.dimension)
        findings.extend(self._scan_secrets(ctx))
        findings.extend(
            await run_llm_enrichment(
                ctx,
                agent=self.name,
                dimension=self.dimension,
                system=_SYSTEM,
                instruction="List concrete security issues in this diff.",
            )
        )
        return findings

    def _scan_secrets(self, ctx: AgentContext) -> list[Finding]:
        out: list[Finding] = []
        for file in ctx.diff.files:
            for line in file.added:
                for secret_type in scan_secret_types(line.text):
                    out.append(
                        Finding(
                            agent=self.name,
                            dimension=self.dimension,
                            category="hardcoded-secret",
                            severity=Severity.CRITICAL,
                            confidence=0.97,
                            title=f"Hardcoded secret detected ({secret_type})",
                            # NB: we never include the secret value itself.
                            message=(
                                f"A {secret_type} appears to be committed at "
                                f"{file.path}:{line.new_line}."
                            ),
                            file_path=file.path,
                            line=line.new_line,
                            cwe="CWE-798",
                            source=FindingSource.DETERMINISTIC,
                            explanation=Explanation(
                                why="Committed credentials are exposed to anyone with repo access "
                                "and leak into history permanently.",
                                impact="Account/service takeover.",
                                alternative="Move to a secret manager; rotate the value now.",
                                references=[
                                    "https://owasp.org/Top10/A07_2021-Identification_and_Authentication_Failures/"
                                ],
                                complexity="low",
                            ),
                        )
                    )
        return out
