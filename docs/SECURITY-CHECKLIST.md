# Security Acceptance Checklist (PRD §9.9) — Live Status

Re-run at the end of every phase. ✅ done · 🟡 partial/scaffolded · ⬜ not yet (later phase).
**Last run: end of Phase 6 — FINAL** (198 tests green; ruff + mypy strict clean; eval harness passing).

| # | Requirement | Status | Where / Notes |
|---|---|---|---|
| 1 | All webhooks HMAC-verified, constant-time compare + replay window | ✅ | `core/security/webhook.py` (+ Redis guard `replay_redis.py`); `test_webhook_security.py` |
| 2 | Zero long-lived tokens; secrets from secret manager | ✅ | `config.py` `SecretStr`/env only; **GitHub App short-lived JWT** `github/auth.py` (≤10 min); `test_github_auth.py` |
| 3 | Every DB/graph/vector query tenant-scoped; verified by tests | ✅ | Tenant scoping by construction in every store + **RLS-coverage test** (`test_rbac_and_isolation.py`: migration RLS list == all `tenant_id` tables) + consolidated cross-store isolation test |
| 4 | Prompt-injection test suite passes | ✅ | `llm/prompting.py` (system/data separation + spotlighting), pre-LLM redaction, output validation; `test_prompt_injection.py` (5 adversarial cases) |
| 5 | Untrusted code analyzed only in no-egress sandbox | ✅ | `core/security/sandbox.py` (no-egress, non-root, read-only, cap-drop ALL, seccomp, mem/pids/cpu + wall-clock limits, gVisor) + `infra/sandbox/{seccomp.json,Dockerfile}`; `test_sandbox.py` |
| 6 | No secret/PII/source in logs (log-scan test) | ✅ | `logging_config.py` RedactionFilter + `redaction.py`; `test_redaction.py` |
| 7 | TLS enforced; at-rest encryption on all stores | 🟡 | Deployment-level control (TLS at ingress; at-rest via datastore/KMS). Documented in `SECURITY.md` — not code-enforceable in this repo |
| 8 | Rate limiting + per-tenant cost ceilings active | ✅ | Per-PR `TokenBudget` (router) + PR-chat token-bucket (`chat/ratelimit.py`) + webhook body cap + cost telemetry/alerts; Triage cuts spend |
| 9 | Own CI runs SAST + dependency + secret scan, green | ✅ | `.github/workflows/ci.yml`: ruff (bandit rules) + **Bandit SAST** + mypy strict + pytest + **eval gate** + gitleaks + trivy + osv + **DAST (ZAP)** |
| 10 | Immutable audit log covers state-changing actions | ✅ | **Hash-chained `HashChainedAuditLog`** (tamper/reorder-evident) wired into feedback + webhook; `test_audit.py` |

**Phase 6 security controls added (final)**
- **Immutable, hash-chained audit log** (`sha256(prev || payload)`) that detects any insert/delete/reorder/mutation, wired into every state-changing action (feedback, webhook); tenant-scoped.
- **Full RBAC enforced**: feedback requires member+, Audit Log requires maintainer+, tenant is derived from the token (never a client param). RBAC rank matrix + cross-store tenant isolation + Postgres-RLS-coverage all tested.
- **Untrusted-code sandbox** hardened by construction: no egress, non-root, read-only FS, cap-drop ALL, seccomp allowlist, mem/pids/cpu + wall-clock limits, gVisor runtime — command builder unit-tested so the guarantees can't silently regress.
- **Supply chain**: Dependabot, SBOM (syft) + image signing (cosign, keyless) on release, Bandit SAST + OWASP ZAP DAST + the eval-quality gate added to CI.
- **Threat model (STRIDE)** in `docs/THREAT-MODEL.md`; disclosure policy + posture in `SECURITY.md`.

**Verdict:** all code-enforceable items ✅. The single 🟡 (item 7, TLS/at-rest) is a deployment-layer control, documented and not enforceable from application code.

**Phase 5 security controls added**
- **Dashboard API is authenticated + RBAC + tenant-scoped by the token:** every endpoint requires a bearer/OIDC principal (`require_role`), the tenant is taken from the *token* (never a query param), and a maintainer+ role is required for the Audit Log. Verified by `test_dashboard.py` (401 without token, 403 on under-privileged role, cross-tenant returns empty).
- **Telemetry carries no secrets/PII:** Prometheus labels are ids/enums only (provider, agent, tenant id, route *template*); the `/metrics` endpoint exposes counts only and is documented as monitoring-network-restricted.
- **Cost is a first-class guard signal:** per-PR/agent/tenant cost is metered alongside the hard `TokenBudget`, so economic-DoS is observable and alertable.

**Phase 4 security controls added**
- **Auto-patches are validated, never auto-applied:** every generated fix must pass balanced-delimiter + (for Python) AST parse checks before it's offered, and it's posted as a GitHub *suggestion* a human must accept — the platform never writes to the repo itself.
- **PR Chat is injection-safe by construction:** the developer's message is wrapped/labeled as untrusted data with an override directive in the system prompt; the answer is plain text with no side effects; it's rate-limited per thread (abuse/cost guard) and always falls back to a deterministic answer.
- **Multi-model resilience without weakening the budget:** provider fallback covers rate-limits/outages, but the per-review `TokenBudget` is a hard, non-recoverable limit that fallback never bypasses (verified by `test_multimodel_router.py`).
- **Feedback is strictly validated + tenant-scoped:** the `/api/v1/feedback` endpoint uses a strict Pydantic model (`extra="forbid"`, enum action) and records into a tenant-scoped store; the Golden-Path learner only *lowers* noise (down-weights rejected categories) and never auto-approves.

**Phase 3 security controls added**
- **Tenant isolation by construction** in repository memory: the in-memory graph/vector stores key all state under `tenant_id` (cross-tenant reads are unrepresentable); the Neo4j adapter filters every Cypher query on a `tenant` property and the Qdrant adapter applies a `tenant` payload filter on every search. Verified by dedicated isolation tests.
- **Trusted/untrusted separation preserved under RAG:** memory-derived context (blast radius, regression, similar findings) is injected only into the *trusted* instruction, never mixed into the untrusted PR block — so memory can't become a new prompt-injection channel.
- **Optional-dependency isolation:** Neo4j/Qdrant drivers are lazily imported, so the offline test suite runs with no network and no extra attack surface.

**Phase 1 security controls added**
- **Prompt-injection defense:** untrusted PR content is redacted, delimiter-neutralized, fenced, and labeled as data; system instructions carry an override directive; model output is validated against a strict schema and **constrained to files in the diff** (the model cannot invent/redirect findings).
- **Deterministic-first:** every security claim originates from a deterministic rule; the LLM only adds capped-confidence suggestions and can never *suppress* a real finding (proved by `test_prompt_injection.py`).
- **Secret handling:** secrets are detected (type only, never value) and redacted before any content leaves for the LLM; findings never echo the secret.
- **Publish sanitization:** untrusted snippets are HTML/backtick-escaped and @mentions defused before entering PR markdown (no HTML injection / forged approvals / mass-pings).
- **Economic-DoS guard:** hard per-PR token budget with pre-check.
- **Graceful degradation:** a failing agent is recorded and skipped, never failing the whole review.

**Phase 0 hardening (still in force)**
- Fail-closed webhook ordering: size cap → HMAC → replay → strict validation → enqueue.
- Never parse unsigned/untrusted JSON before signature verification. No signature oracles.
- `extra="forbid"` settings + strict Pydantic models; request-id sanitized (log-injection guard).
- Docker image non-root; compose services drop capabilities / `no-new-privileges`.

**Phase 1 verdict:** all Phase-0 and Phase-1-scoped items ✅; remaining 🟡 items have a clear owner phase.
