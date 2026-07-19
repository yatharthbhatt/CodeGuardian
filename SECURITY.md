# Security Policy — CodeGuardian AI

Security is a first-class feature of CodeGuardian AI: *the tool that reviews code for
vulnerabilities must itself have none.* This document covers reporting, our security
posture, and where to find the details.

## Reporting a vulnerability

- **Do not** open a public issue for security reports.
- Email **security@codeguardian.example** (or use GitHub private vulnerability reporting).
- Include reproduction steps and impact. We acknowledge within **2 business days** and aim
  to remediate critical issues within **7 days**.
- We support coordinated disclosure and will credit reporters who wish to be named.

## Security posture (summary)

| Area | Control |
|---|---|
| Webhook authenticity | HMAC-SHA256, constant-time compare, per-delivery replay guard |
| Auth | GitHub App short-lived tokens (no PATs); OIDC/bearer + RBAC for the API |
| Multi-tenancy | Tenant taken from the token; every store tenant-scoped; Postgres RLS |
| Untrusted input | Strict Pydantic validation; **prompt-injection defenses** (data/instruction separation, output validation, diff-constrained findings) |
| Untrusted code | Analyzed only in a **no-egress, non-root, read-only, seccomp, resource+time-bounded** sandbox (gVisor) |
| Secrets | From a secret manager; `SecretStr`; **redacted before logs and before any LLM call** |
| Auto-fixes | Validated (AST/delimiter) and offered as suggestions — **never auto-applied** |
| Audit | Immutable, **hash-chained**, tamper-evident audit log |
| Cost / abuse | Hard per-PR token budget; rate limiting; cost telemetry |
| Supply chain | Pinned deps, Dependabot, Trivy/OSV/Grype, **SBOM (syft)** + **signed images (cosign)** |
| CI (dog-food) | Ruff (bandit rules), mypy strict, pytest, Bandit SAST, gitleaks, DAST (ZAP), eval gate |

Full, phase-by-phase status: [`docs/SECURITY-CHECKLIST.md`](docs/SECURITY-CHECKLIST.md) (PRD §9.9).
Threat model (STRIDE): [`docs/THREAT-MODEL.md`](docs/THREAT-MODEL.md).

## Handling of your code

Customer code is treated as untrusted input, is never executed on the host, and is **never
used to train models**. Secrets found in a diff are redacted before any content leaves our
trust boundary.

## Supported versions

The latest released minor version receives security updates.
