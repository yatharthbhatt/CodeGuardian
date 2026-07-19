# CodeGuardian AI — Product & Engineering Specification

> **An Enterprise-Grade Multi-Agent Autonomous Code Review & Engineering Intelligence Platform.**
> Not just a PR reviewer — a complete engineering assistant that understands repositories,
> architecture, security, performance, documentation, coding standards, and business logic.
>
> Think: *GitHub Copilot + CodeRabbit + Snyk + SonarQube + Linear AI + Architecture Review*
> inside one autonomous, secure, observable multi-agent platform.

**Product name:** CodeGuardian AI
**Tagline:** *"Every pull request, reviewed by a team of senior engineers — in seconds, with receipts."*
**Status:** Vision / Spec (v1.0)
**Owner:** Yatharth

---

## 0. Table of Contents

1. [Vision & Positioning](#1-vision--positioning)
2. [Who It's For (Personas)](#2-who-its-for-personas)
3. [The Original Resume Bullets (Preserved)](#3-the-original-resume-bullets-preserved)
4. [System Architecture](#4-system-architecture)
5. [The Agent Fleet](#5-the-agent-fleet)
6. [Orchestration: LangGraph State Machine](#6-orchestration-langgraph-state-machine)
7. [Consensus Engine & Risk Scoring](#7-consensus-engine--risk-scoring)
8. [Unique / Differentiating Features](#8-unique--differentiating-features)
9. [Security — First-Class Concern](#9-security--first-class-concern)
10. [Data Model](#10-data-model)
11. [Repository Memory (Knowledge Graph + Vector)](#11-repository-memory-knowledge-graph--vector)
12. [Multi-Model Abstraction Layer](#12-multi-model-abstraction-layer)
13. [MLOps, Observability & Cost Control](#13-mlops-observability--cost-control)
14. [Frontend Dashboard](#14-frontend-dashboard)
15. [Tech Stack](#15-tech-stack)
16. [API Surface](#16-api-surface)
17. [Non-Functional Requirements](#17-non-functional-requirements)
18. [Delivery Roadmap (Phased)](#18-delivery-roadmap-phased)
19. [Testing & Quality Strategy](#19-testing--quality-strategy)
20. [Success Metrics](#20-success-metrics)
21. [Resume / Portfolio Framing](#21-resume--portfolio-framing)

---

## 1. Vision & Positioning

Modern code review is the single biggest bottleneck in software delivery. It is slow, inconsistent,
reviewer-dependent, and biased toward style over substance. Security issues, architectural drift, and
performance regressions routinely slip through because a human reviewer cannot hold the entire
repository, its history, and every best-practice framework in their head at 11pm on a Friday.

**CodeGuardian AI** replaces the "one tired reviewer" model with a **fleet of specialized, parallel AI
agents** that each own one dimension of engineering quality, collaborate through **shared state**, reach
**weighted consensus**, and post **structured, explainable, auto-fixable feedback** directly onto the
Pull Request — while remembering everything about the repository over time.

**What makes it different from every existing tool:**

| Existing tool | What it does | What it misses |
|---|---|---|
| CodeRabbit | LLM PR summaries | No consensus, weak security, forgets everything |
| Snyk | Dependency/CVE scanning | No architecture/perf/docs, not conversational |
| SonarQube | Static analysis rules | Rigid, no reasoning, no "does this solve the problem?" |
| Copilot | Autocomplete | Not a reviewer, no cross-file/architecture view |
| **CodeGuardian AI** | **All of the above, unified, with memory + consensus + explainability + auto-patch + security-first design** | — |

**Design principles**
- **Autonomous but accountable** — every decision is explainable and auditable.
- **Security is a feature, not an afterthought** — the platform that reviews code must itself be unhackable.
- **Signal over noise** — fewer, higher-confidence comments beat 200 nitpicks.
- **Memory beats amnesia** — the system gets smarter about *your* repo with every PR.
- **Model-agnostic** — never locked to one LLM vendor.

---

## 2. Who It's For (Personas)

- **Solo dev / OSS maintainer** — wants a tireless senior reviewer for free-tier repos.
- **Startup eng team (5–50)** — wants to enforce standards without a dedicated staff engineer.
- **Enterprise platform team** — wants org-wide governance, audit trails, compliance, and dashboards.
- **Security team** — wants shift-left vulnerability detection wired into every PR.
- **Engineering manager** — wants the Quality Timeline and Technical Debt trends for planning.

---

## 3. The Original Resume Bullets (Preserved)

> These are kept verbatim as the seed of the project and remain 100% accurate for the finished system.

**Autonomous Agentic PR Reviewer | Python, LangGraph, GitHub Webhooks, OpenAI API — Apr 2026 – Present**
A multi-agent LLM system that automates code quality control through parallelized, consensus-driven
review across security, architecture, and documentation dimensions.

- Orchestrated a LangGraph-powered multi-agent system to automate end-to-end code quality control,
  reducing manual code review cycle time by 75% via parallelized static analysis across concurrently
  running specialized agents.
- Built dedicated Security, Architect, and Documentation agents that collaborate through shared state
  context in LangGraph, delivering consensus-based, structured feedback directly to GitHub Pull Requests
  via webhook integration.
- Enforced production-grade code compliance by embedding automated vulnerability scanning and dependency
  analysis into the CI/CD pipeline using the OpenAI API, ensuring consistent code quality standards across
  all PRs.

*Everything below is additive — it expands this seed into a full product without removing anything above.*

---

## 4. System Architecture

```
                         ┌──────────────────────────────────────────────┐
                         │                 GitHub / GitLab               │
                         │   PR opened / synced / comment / re-review    │
                         └───────────────────────┬──────────────────────┘
                                                 │ webhook (HMAC-signed)
                                                 ▼
                    ┌──────────────────────────────────────────────────────┐
                    │   API Gateway (FastAPI)                               │
                    │   • HMAC SHA-256 signature verification               │
                    │   • Payload schema validation (Pydantic)             │
                    │   • Rate limiting + abuse detection                   │
                    │   • AuthN (GitHub App JWT) / AuthZ (RBAC)             │
                    └───────────────────────┬──────────────────────────────┘
                                            │ enqueue job
                                            ▼
                    ┌──────────────────────────────────────────────────────┐
                    │   Task Queue (Celery/Temporal + Redis)               │
                    │   • Idempotency keys • Retries • Dead-letter queue    │
                    └───────────────────────┬──────────────────────────────┘
                                            ▼
       ┌──────────────────────────────────────────────────────────────────────────────┐
       │                       LangGraph Orchestrator                                   │
       │                                                                                │
       │   [Ingest] → [Triage/Router] → ┌─ Security Agent ─┐                            │
       │        │                        ├─ Architecture  ─┤                            │
       │        │  (fan-out, parallel)   ├─ Performance   ─┤ ── shared state ──►        │
       │        │                        ├─ Documentation ─┤   [Consensus Engine]       │
       │        │                        ├─ Testing       ─┤        │                    │
       │        │                        ├─ DevOps        ─┤        ▼                    │
       │        │                        ├─ Accessibility ─┤   [Risk Scorer]             │
       │        │                        └─ AI Reviewer   ─┘        │                    │
       │        │                                                    ▼                    │
       │        └──────────────► [Auto-Patch Gen] ◄──── [Explainability] ──► [Publish]  │
       └──────────────────────────────────┬───────────────────────────────────────────┘
                                           │
        ┌──────────────────────────────────┼───────────────────────────────────┐
        ▼                                   ▼                                    ▼
 ┌─────────────┐               ┌────────────────────────┐             ┌──────────────────┐
 │ PostgreSQL  │               │ Repository Memory       │             │ Sandbox Runner   │
 │ (metadata,  │               │  • Neo4j (knowledge     │             │ (isolated, no    │
 │  findings,  │               │     graph)              │             │  network egress, │
 │  audit log) │               │  • Qdrant (vectors)     │             │  ephemeral)      │
 └─────────────┘               └────────────────────────┘             └──────────────────┘
        │
        ▼
 ┌──────────────────────────────────────────────────────────────────────────┐
 │ Observability: Prometheus • Grafana • OpenTelemetry • structured JSON logs │
 └──────────────────────────────────────────────────────────────────────────┘
        │
        ▼
 ┌──────────────────────────────────────────────┐
 │ React + TypeScript Dashboard (risk heatmap,   │
 │ quality timeline, cost analytics, knowledge   │
 │ graph, agent decisions, audit)                │
 └──────────────────────────────────────────────┘
```

**Flow summary**
1. GitHub App fires a webhook → Gateway verifies HMAC, validates payload, enforces RBAC & rate limits.
2. Job is enqueued (idempotent) → orchestrator ingests the diff, PR metadata, and repo memory.
3. **Triage/Router** decides *which* agents are relevant (cost optimization — don't run the Accessibility
   agent on a backend-only Go PR).
4. Relevant agents run **in parallel**, reading shared state (repo conventions, past findings, diff).
5. **Consensus Engine** merges findings with **weighted confidence**; **Risk Scorer** computes scores.
6. **Auto-Patch Generator** produces suggested diffs; **Explainability** attaches rationale.
7. Results are **published** as a structured PR review + inline comments + a status check; memory is updated.

---

## 5. The Agent Fleet

> Every agent below is preserved from the original vision and expanded with concrete detection rules,
> inputs, outputs, and guardrails. Each agent returns a **typed `Finding[]`** into shared state.

### 5.1 Security Agent
**Owns:** vulnerabilities, secrets, supply chain, infra misconfig.
**Detects:** Secret detection · Dependency vulnerability analysis · CVE lookup · OWASP Top 10 ·
SQL injection · XSS · CSRF · SSRF · Auth review (authN) · Authorization review (authZ) · Broken access
control · Rate-limiting suggestions · JWT validation flaws · Insecure deserialization · Path traversal ·
API security · Docker security · Kubernetes manifest review · IaC / Terraform misconfiguration · Hardcoded
credentials · Weak crypto · PII/PHI exposure (GDPR/HIPAA) · License compliance.
**Tooling under the hood (deterministic + LLM):** Semgrep/Bandit/Gitleaks/Trivy/Grype/OSV-Scanner feed
findings to the LLM for triage, severity, and explanation. **Never trusts the LLM alone for security.**
**Output extras:** CVSS-style severity, CWE id, exploitability, and a suggested fix diff.

### 5.2 Architecture Agent
**Owns:** structural quality and long-term maintainability.
**Detects:** SOLID violations · Clean Architecture adherence · DDD suggestions · Modularization ·
Circular dependency detection · Design-pattern suggestions · Refactoring suggestions · Microservice
boundary review · Event-driven suggestions · God objects / high coupling / low cohesion · Layering
violations · Blast-radius analysis (what this change ripples into).

### 5.3 Performance Agent
**Owns:** runtime efficiency and scalability.
**Detects:** N+1 query detection · Memory leak detection · CPU-intensive logic · Async opportunities ·
Cache suggestions · Redis suggestions · DB optimization · Index recommendations · Thread-safety ·
Unbounded loops/allocations · Inefficient data structures · Blocking I/O on hot paths.

### 5.4 Documentation Agent
**Owns:** clarity, onboarding, knowledge capture.
**Detects/Generates:** Missing README · Missing API docs · Function/docstring documentation · Missing
examples · Changelog generation · Release notes · **ADR (Architecture Decision Record) generation** ·
Stale docs vs. code drift · Inline comment quality.

### 5.5 Testing Agent
**Owns:** test coverage and correctness confidence.
**Detects/Generates:** Missing unit tests · Missing integration tests · Edge cases · Coverage
suggestions · Mock suggestions · Property-based tests · Test-impact analysis (which tests this diff
affects) · Flaky-test heuristics · Assertion quality.

### 5.6 DevOps Agent
**Owns:** delivery pipeline and infrastructure hygiene.
**Detects:** Dockerfile review · Kubernetes review · Terraform review · CI/CD review · GitHub Actions
review · Environment-variable hygiene · Secrets management · Non-pinned base images · Missing health
checks · Overly-broad IAM.

### 5.7 Accessibility Agent
**Owns:** inclusive UX (frontend PRs).
**Detects:** WCAG 2.2 compliance · Semantic HTML · Keyboard navigation · Color contrast · ARIA
correctness · Focus management · Alt text.

### 5.8 AI Reviewer Agent *(the unique one)*
**Owns:** semantic correctness — the question no linter can answer.
Instead of checking syntax, it asks: **"Does this code actually solve the stated problem?"**
It reads the PR title, description, linked issue, and the diff, then reasons about intent vs.
implementation: logic errors, off-by-one, wrong edge handling, mismatched requirements, silent behavior
changes, and regression risk based on the repo's historical bug patterns.

### 5.9 New supporting agents (added to make it production-grade)
- **Triage/Router Agent** — classifies the diff (languages, surfaces touched, size, risk) and selects the
  minimal set of agents to run → **major cost + latency saver.**
- **Consensus/Aggregator Agent** — dedupes overlapping findings, resolves conflicts, ranks by severity.
- **Feedback/Learning Agent** — records which suggestions developers accept/reject and adapts thresholds
  and prompts per repo over time (the "golden path" learner).
- **Compliance Agent** *(enterprise)* — SBOM generation, license policy enforcement, SOC2/GDPR checks.

---

## 6. Orchestration: LangGraph State Machine

**Shared State (typed, immutable-per-node)**

```python
class ReviewState(TypedDict):
    pr: PullRequestMeta            # title, body, author, base/head SHA, linked issues
    diff: NormalizedDiff          # AST-aware, file-scoped hunks
    repo_memory: RepoContext      # conventions, past findings, architecture graph slice
    routing: RoutingDecision      # which agents to run + why
    findings: list[Finding]       # append-only, each tagged with agent + confidence
    consensus: ConsensusResult    # merged, weighted, deduped
    risk: RiskScorecard           # per-dimension + overall
    patches: list[SuggestedPatch] # unified diffs
    audit: list[AuditEvent]       # every state transition, immutable
    budget: TokenBudget           # tokens/cost remaining for this PR
```

**Graph topology**
- `ingest → triage → (fan-out: selected agents in parallel) → join → consensus → risk → patch → explain → publish`
- **Conditional edges:** skip agents the router deemed irrelevant; short-circuit to `publish` for trivial
  PRs (docs-only, dependency bumps with green scans) via a **confidence-gated auto-approve**.
- **Checkpointing:** LangGraph checkpointer persists state to Postgres so a crashed review resumes, and so
  the **PR Chat** feature can replay context.
- **Human-in-the-loop:** high-risk findings can pause the graph for maintainer approval before auto-actions.

---

## 7. Consensus Engine & Risk Scoring

**Not majority voting — weighted confidence.** Each agent emits a confidence per finding; the engine
combines them with per-agent, per-dimension weights (tunable per repo via the Feedback Agent).

```
Example PR:
  Security      confidence 95%  (weight 1.30)
  Architecture  confidence 88%  (weight 1.00)
  Performance   confidence 72%  (weight 0.90)
  ─────────────────────────────────────────
  Final blended confidence ≈ 91%
  + Consensus reasoning (natural-language justification of the merged verdict)
```

**Risk Scorecard** — every PR gets:
- Security Risk · Architecture Risk · Performance Risk · Maintainability · Technical Debt · Documentation ·
  **Overall Engineering Score** (e.g. **94/100**).
- Each score has a **breakdown, trend arrow, and the findings that moved it**.

**Confidence gating (noise control)**
- `≥ threshold` → posted as a blocking/inline comment.
- `mid` → posted as a collapsed "consider" note.
- `< threshold` → suppressed (kept in the dashboard, not on the PR) to prevent reviewer fatigue.

---

## 8. Unique / Differentiating Features

> These are the "recruiters love this" features. All original ones preserved; new ones marked ★NEW.

1. **Repository Memory** — every repo gets long-term memory (architecture, past PRs, coding style,
   conventions, naming, past bugs, prior discussions) via **Neo4j** (knowledge graph) + **Qdrant/vector DB**,
   instead of forgetting every PR.
2. **Consensus Engine** — weighted confidence + consensus reasoning (see §7).
3. **Risk Score** — multi-dimensional scorecard + overall engineering score (see §7).
4. **Code Quality Timeline** — dashboard trend of PR quality over weeks (improving / declining?).
5. **AI Explainability** — every suggestion must include: **Why · Impact · Alternative · References ·
   Complexity · Confidence.**
6. **Auto-Patch Generator** — instead of "this is vulnerable," it emits a `- vulnerable / + fixed` unified
   diff the developer can apply with one click (GitHub suggestion block).
7. **PR Chat** — developer replies "Why is this bad?" on the PR; the agent answers with full repo context
   (LangGraph checkpoint replay). Threaded, context-aware.
8. **Multi-Model Support** — OpenAI · Claude · Gemini · DeepSeek · local Ollama via a clean **adapter
   layer** (see §12). Route by cost/latency/capability.
9. ★NEW **Blast-Radius Analysis** — uses the knowledge graph to show every downstream module/service a
   change can break.
10. ★NEW **Confidence-Gated Auto-Approve** — trivial, low-risk PRs (docs, safe dependency bumps) are
    auto-approved to save human time, fully audited.
11. ★NEW **Regression-Risk Prediction** — flags diffs that touch historically bug-prone files/functions.
12. ★NEW **Golden-Path Learner** — adapts to each team's accepted/rejected suggestions over time.
13. ★NEW **Semantic Diff** — reasons over AST/control-flow, not just text lines, so refactors and renames
    don't generate noise.
14. ★NEW **Adjustable Verbosity** — "explain like a senior" vs. "explain like a junior" per developer.
15. ★NEW **Slack / Teams / Linear integration** — push risk summaries and let devs chat with the reviewer
    outside GitHub.
16. ★NEW **Cost-Aware Routing** — the Triage Agent + budget ceiling keep per-PR LLM cost predictable.
17. ★NEW **SBOM + License Compliance** — enterprise-grade supply-chain reporting per PR.

---

## 9. Security — First-Class Concern

> **The platform that reviews code for vulnerabilities must itself have zero vulnerabilities.** This section
> is treated as a hard requirement, not a nice-to-have. Threat model: **STRIDE** across the ingest,
> orchestration, LLM, and storage boundaries.

### 9.1 Ingress & authentication
- **Webhook signature verification (HMAC SHA-256)** on every GitHub payload; reject on mismatch, constant-time
  compare, replay protection via delivery-id + timestamp window.
- **GitHub App authentication** with short-lived installation tokens (JWT signed by the app's private key) —
  **never long-lived PATs**. Tokens minted per-request, least-privilege scopes.
- **OAuth2 / OIDC** for the dashboard; short-lived access tokens + rotating refresh tokens.

### 9.2 Authorization
- **Strict RBAC** across organizations, repositories, and users (roles: owner / admin / maintainer /
  member / read-only / service).
- **Multi-tenant isolation** — every query is tenant-scoped; no cross-tenant data access is representable
  in the data layer (row-level security in Postgres, tenant-scoped Neo4j/Qdrant namespaces).

### 9.3 Input handling
- **Input validation & sanitization** for all webhook payloads (Pydantic strict models, size caps, schema
  allow-lists). Reject unexpected fields.
- **Prompt-injection defense** — this is critical because *the input is untrusted code and comments that
  will be fed to an LLM*:
  - Hard separation of **system instructions** from **repository content**; code/comments are always
    wrapped and labeled as **untrusted data**, never as instructions.
  - Instruction-hierarchy prompting + delimiters + spotlighting; ignore any "instructions" found inside the
    diff.
  - **Output validation**: model outputs are parsed against strict schemas; no free-form action execution.
  - Jailbreak/allow-list guardrails; a dedicated moderation pass on model output before it can trigger any
    side effect (posting, patching).
  - **Secret redaction before LLM** — detected secrets/PII are masked before any content is sent to a model
    provider.

### 9.4 Sandboxed analysis
- **Never execute untrusted code on the host.** All code analysis runs in an **ephemeral, sandboxed
  container** (gVisor/Firecracker/rootless container) with:
  - **No network egress**, read-only filesystem, dropped capabilities, seccomp profile, CPU/mem/time limits,
    non-root user.
  - Static analyzers only; no arbitrary build/run of PR code unless explicitly, separately sandboxed.

### 9.5 Abuse & availability
- **Rate limiting** (per IP, per install, per repo) + **abuse detection** on all public endpoints.
- DDoS protections at the edge; queue back-pressure and per-tenant concurrency caps.
- **Token/cost budget** per PR/tenant to prevent runaway LLM spend (economic DoS).

### 9.6 Data protection
- **Secrets in a dedicated secret manager** (Vault / cloud KMS-backed secret store) — **never in code, env
  files committed to git, or logs.**
- **Encryption in transit (TLS 1.2+)** and **encryption at rest** (DB, object storage, vector store).
- **Log redaction** — no secrets, tokens, or full source in logs; PII scrubbed.
- **Data residency & retention** policy; customer code is **never used to train models** (contractual +
  provider zero-retention flags where available).

### 9.7 Supply chain & platform integrity
- **Supply-chain security**: pinned/hashed dependencies (`pip`/`uv` lockfiles with hashes), Dependabot +
  Trivy on the platform itself, signed container images (cosign), SBOM published per release.
- **Signed commits + branch protection + required reviews** on the CodeGuardian repo itself.
- **SAST/DAST/secret-scan in CodeGuardian's own CI** — it eats its own dog food.

### 9.8 Auditing & compliance
- **Immutable, append-only audit log** of every event (who/what/when, agent decisions, publishes,
  auto-approvals, config changes). Tamper-evident (hash-chained).
- Compliance posture aimed at **SOC 2 / GDPR** readiness; DPA-friendly data flows.

### 9.9 Security acceptance checklist (must all pass before "done")
- [ ] All webhooks HMAC-verified with constant-time compare + replay window.
- [ ] Zero long-lived tokens; all secrets from the secret manager.
- [ ] Every DB/graph/vector query is tenant-scoped; verified by tests.
- [ ] Prompt-injection test suite passes (adversarial diffs cannot alter agent behavior or exfiltrate).
- [ ] Untrusted code analyzed only in a no-egress sandbox.
- [ ] No secret/PII/source in logs (verified by log-scan test).
- [ ] TLS enforced; at-rest encryption on all stores.
- [ ] Rate limiting + per-tenant cost ceilings active.
- [ ] CodeGuardian's own CI runs SAST + dependency scan + secret scan and is green.
- [ ] Immutable audit log covers all state-changing actions.

---

## 10. Data Model

**PostgreSQL (source of truth for metadata, findings, audit) — row-level security by `tenant_id`.**

- `tenants`, `users`, `memberships(role)`, `installations`, `repositories`
- `pull_requests(pr_id, repo_id, head_sha, base_sha, state, ...)`
- `reviews(review_id, pr_id, model_used, cost_tokens, latency_ms, status)`
- `findings(finding_id, review_id, agent, category, severity, cwe, confidence, file, line, message, references[])`
- `patches(patch_id, finding_id, unified_diff, applied_bool)`
- `risk_scorecards(review_id, security, architecture, performance, maintainability, tech_debt, docs, overall)`
- `feedback(finding_id, action: accepted|rejected|edited, actor, ts)`
- `audit_events(event_id, tenant_id, actor, action, payload_hash, prev_hash, ts)` — hash-chained
- `budgets(tenant_id, period, tokens_used, cost_used, ceiling)`

**Neo4j** — repository knowledge graph (see §11).
**Qdrant** — embeddings of code symbols, past findings, PR discussions for semantic recall.
**Redis** — queue broker, rate-limit counters, short-lived caches, idempotency keys.

---

## 11. Repository Memory (Knowledge Graph + Vector)

**Neo4j graph nodes/edges (example):**
```
(Repo)-[:HAS]->(Module)-[:CONTAINS]->(File)-[:DEFINES]->(Symbol:Function|Class)
(Symbol)-[:CALLS]->(Symbol)                # for blast-radius
(File)-[:DEPENDS_ON]->(File)               # circular-dependency detection
(PR)-[:TOUCHED]->(File)
(Finding)-[:AGAINST]->(Symbol)
(Convention)-[:APPLIES_TO]->(Repo)         # learned team norms
(Bug)-[:INTRODUCED_IN]->(PR)-[:FIXED_IN]->(PR)  # regression-risk history
```

**Qdrant collections:** `symbols`, `past_findings`, `pr_discussions`, `docs` — used for
retrieval-augmented context so agents "remember" prior decisions and match established style.

**How memory is used**
- Triage uses the graph to compute blast radius and pick agents.
- Architecture agent detects circular deps and boundary violations from `DEPENDS_ON`.
- AI Reviewer + Feedback agents recall prior discussions and accepted conventions (RAG).
- Regression-risk prediction reads `Bug`→`PR` history for touched files.

---

## 12. Multi-Model Abstraction Layer

A single `LLMProvider` interface with adapters — **no vendor lock-in**, route by cost/latency/capability.

```python
class LLMProvider(Protocol):
    async def complete(self, req: LLMRequest) -> LLMResponse: ...
    def count_tokens(self, text: str) -> int: ...
    @property
    def capabilities(self) -> ModelCapabilities: ...  # ctx window, tools, JSON mode, cost

# Adapters: OpenAIAdapter, ClaudeAdapter, GeminiAdapter, DeepSeekAdapter, OllamaAdapter
# Router: pick provider per task (e.g., cheap model for triage, strong model for AI Reviewer),
#         with automatic fallback on rate-limit/outage, and a hard per-PR token budget.
```

- **Structured outputs** enforced everywhere (JSON schema / tool-calling) so findings are always typed.
- **Prompt caching** where the provider supports it (repo context reused across agents) to cut cost.
- **Deterministic tools first** — Semgrep/Trivy/etc. run before the LLM; the LLM triages/explains rather
  than being the sole source of truth for security-critical claims.

---

## 13. MLOps, Observability & Cost Control

*(Most people forget this — including it is a differentiator.)*

- **Prometheus metrics** — request rate, queue depth, agent latency, error rates, agent success rate.
- **Grafana dashboards** — service health + per-agent + cost.
- **OpenTelemetry tracing** — one trace per PR spanning webhook → agents → publish.
- **Structured JSON logging** — correlation ids, tenant/PR ids, redacted.
- **LLM cost telemetry** — token usage, **cost per PR**, cost per agent, per-tenant spend vs. budget.
- **Quality telemetry** — suggestion acceptance rate (the north-star model-quality metric), false-positive
  rate, time-to-first-comment.
- **Evals** — an offline eval harness with a labeled dataset of PRs to catch regressions in agent quality
  when prompts/models change (LLM-as-judge + golden findings).

---

## 14. Frontend Dashboard

Beautiful **React + TypeScript + Tailwind + Recharts** dashboard. Views:

- **Repository Overview** — health, active installs, config.
- **Open PRs** — live status of reviews in flight.
- **Risk Heatmap** — files/modules colored by aggregated risk.
- **Agent Decisions** — drill into each agent's findings + reasoning + confidence.
- **Cost Analytics** — cost per PR/repo/tenant, tokens, model mix, budget burn.
- **Latency** — per-agent and end-to-end.
- **Repository Knowledge Graph** — interactive Neo4j visualization.
- **Technical Debt** — hotspots and trend.
- **Quality Trend / Code Quality Timeline** — weekly PR quality, improving vs. declining.
- **Audit Log** — immutable event trail (admin).
- **Settings** — thresholds, agent toggles, model routing, RBAC, budgets.

Accessibility: the dashboard itself meets WCAG 2.2 AA (dark/light themes, keyboard-navigable, contrast-safe).

---

## 15. Tech Stack

**Backend:** Python 3.12 · FastAPI · LangGraph · Celery **or** Temporal · Redis · PostgreSQL · Neo4j · Qdrant · Pydantic · `uv`/Poetry
**Static-analysis tooling:** Semgrep · Bandit · Gitleaks · Trivy · Grype · OSV-Scanner · Syft (SBOM)
**Frontend:** React · TypeScript · Tailwind CSS · Recharts · TanStack Query
**Infra:** Docker · Docker Compose (dev) · Kubernetes (prod) · GitHub Actions · Terraform
**Observability:** Prometheus · Grafana · OpenTelemetry · Loki (logs)
**Secrets/Security:** Vault or cloud KMS-backed secret manager · cosign (image signing) · gVisor/Firecracker (sandbox)
**LLMs:** OpenAI · Claude · Gemini · DeepSeek · Ollama (via adapter layer)
**Cloud:** GCP **or** AWS

---

## 16. API Surface (representative)

```
POST /webhooks/github                # HMAC-verified ingress (primary entrypoint)
GET  /api/v1/repos/{id}/reviews      # list reviews
GET  /api/v1/reviews/{id}            # review detail + findings + scorecard
POST /api/v1/reviews/{id}/rerun      # re-review
POST /api/v1/reviews/{id}/chat       # PR Chat message → agent answer
POST /api/v1/findings/{id}/feedback  # accept/reject/edit (feeds Golden-Path Learner)
POST /api/v1/patches/{id}/apply      # apply suggested patch as a GitHub suggestion/commit
GET  /api/v1/repos/{id}/graph        # knowledge-graph slice for dashboard
GET  /api/v1/repos/{id}/metrics      # quality timeline, cost, latency
GET  /api/v1/audit                   # admin, tenant-scoped, immutable
```
All endpoints: OIDC-authenticated, RBAC-authorized, tenant-scoped, rate-limited, request-id traced.

---

## 17. Non-Functional Requirements

- **Latency:** median PR review < 60s for typical diffs; triage short-circuit < 5s for trivial PRs.
- **Throughput:** horizontal scale via stateless workers + queue; per-tenant concurrency caps.
- **Availability:** 99.9% target; graceful degradation (if one agent fails, others still publish).
- **Resilience:** retries with backoff, idempotent webhook processing, dead-letter queue, checkpointed graph.
- **Cost:** predictable per-PR ceiling; cheap-model triage; prompt caching.
- **Privacy:** zero-retention model calls where possible; customer code never trains models.

---

## 18. Delivery Roadmap (Phased)

- **Phase 0 — Foundations:** repo, CI (lint/type/test/security scan), Docker Compose, secrets management,
  FastAPI skeleton, HMAC webhook, Pydantic schemas, Postgres + migrations, structured logging.
- **Phase 1 — MVP (matches original bullets):** LangGraph orchestrator + Security/Architecture/Documentation
  agents, consensus (weighted), publish structured PR comments, GitHub App auth. *Ship this first.*
- **Phase 2 — Fleet + Consensus:** add Performance, Testing, DevOps, Accessibility, AI Reviewer, Triage/Router;
  risk scorecard; confidence gating.
- **Phase 3 — Memory:** Neo4j knowledge graph + Qdrant, RAG context, blast-radius, regression-risk.
- **Phase 4 — Auto-Patch + PR Chat + Multi-Model:** suggestion diffs, threaded chat, adapter layer + routing.
- **Phase 5 — Observability + Dashboard:** Prometheus/Grafana/OTel, React dashboard, cost analytics, quality timeline.
- **Phase 6 — Enterprise/Security hardening:** RBAC, multi-tenancy, audit log, SBOM/compliance, sandbox hardening, evals.

Each phase ends with the **security acceptance checklist (§9.9)** re-run.

---

## 19. Testing & Quality Strategy

- **Unit tests** for every agent's deterministic logic and parsers (≥80% coverage on core).
- **Contract tests** for the `LLMProvider` adapters (mocked providers).
- **Integration tests** for the LangGraph flow end-to-end with recorded fixtures.
- **Adversarial/security tests** — prompt-injection corpus, malicious webhook payloads, tenant-isolation
  probes, log-leak scans.
- **Eval harness** — labeled PR dataset; track suggestion precision/recall and false-positive rate across
  prompt/model changes.
- **Load tests** — queue back-pressure, concurrency caps, cost ceilings.

---

## 20. Success Metrics

- **75%+ reduction in review cycle time** (original claim — measured via time-to-first-review).
- **Suggestion acceptance rate** (north star) trending up per repo.
- **False-positive rate** trending down (noise control working).
- **Cost per PR** within budget.
- **Escaped-defect rate** (bugs that reached main despite green review) trending down.
- **Coverage of PRs auto-reviewed** approaching 100%.

---

## 21. Resume / Portfolio Framing

**Product name (use this, not "Autonomous Agentic PR Reviewer"):** **CodeGuardian AI**.
A memorable product name makes it read like a real product, not a class assignment. (Alternatives you had:
MergeMind, PR Sentinel, CodeForge AI, ReviewPilot, CodeSage, GuardianPR, MergeLens, Sentinel Review, ReviewOS.)

**Upgraded resume bullets (keep the originals; these are the "grown-up" version):**
- Architected **CodeGuardian AI**, a secure, multi-agent (LangGraph) autonomous code-review platform with
  8+ specialized agents reaching **weighted-consensus verdicts**, cutting review cycle time ~**75%**.
- Built a **security-first** ingestion pipeline: HMAC-verified GitHub App webhooks, prompt-injection
  defenses, sandboxed (no-egress) static analysis, tenant isolation, and an immutable audit log.
- Added **repository long-term memory** (Neo4j knowledge graph + Qdrant vectors) enabling blast-radius and
  regression-risk analysis, plus a **multi-model adapter layer** (OpenAI/Claude/Gemini/DeepSeek/Ollama).
- Shipped **auto-patch generation, PR chat, explainable findings**, and full **observability** (Prometheus,
  Grafana, OpenTelemetry) with per-PR **cost analytics**.

---

*This document is additive to the original vision — nothing was removed.*
