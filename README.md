<div align="center">

# 🛡️ CodeGuardian AI

**An enterprise-grade, multi-agent, autonomous code-review & engineering-intelligence platform.**

*Every pull request, reviewed by a team of senior engineers — in seconds, with receipts.*

![tests](https://img.shields.io/badge/tests-198%20passing-brightgreen)
![type-check](https://img.shields.io/badge/mypy-strict%20clean-blue)
![lint](https://img.shields.io/badge/ruff-clean-blue)
![python](https://img.shields.io/badge/python-3.12%2B-blue)
![security](https://img.shields.io/badge/security-first-critical)
![license](https://img.shields.io/badge/license-Apache--2.0-lightgrey)

</div>

---

CodeGuardian AI replaces the "one tired reviewer" model with a **fleet of specialized AI agents** —
Security, Architecture, Performance, Testing, DevOps, Accessibility, Documentation, and a unique
**AI Reviewer** ("does this code actually solve the problem?"). They run **in parallel** through a
**LangGraph** orchestrator, reach a **weighted-consensus** verdict, score risk, generate **one-click
auto-fixes**, **remember the repository** over time, and post **explainable** feedback straight onto the
Pull Request — all built **security-first**, so the tool that reviews code for vulnerabilities has none
of its own.

> Think **GitHub Copilot + CodeRabbit + Snyk + SonarQube** inside one autonomous, observable,
> multi-tenant platform.

## ✨ See it work (offline, no API key)

Point it at the included intentionally-vulnerable [`demo-repo/`](demo-repo/):

```console
$ cd backend && python -m examples.review_demo_repo

========================================================================
CodeGuardian AI review of demo-repo/  —  15 findings
Overall Engineering Score: 86.7/100   Verdict: REQUEST_CHANGES
========================================================================
  [critical] hardcoded-secret           app.py:16
  [high    ] sql-injection              app.py:25
  [high    ] dangerous-eval             app.py:33
  [high    ] tls-verification-disabled  app.py:38 [auto-fix available]
  [high    ] insecure-deserialization   app.py:44 [auto-fix available]
  [medium  ] docker-unpinned-base       Dockerfile:2
  [medium  ] weak-hash                  app.py:27 [auto-fix available]
  [medium  ] debug-enabled              app.py:18 [auto-fix available]
  ...
========================================================================
Auto-fix suggestions generated: 4
```

Each finding ships with **Why · Impact · Alternative · References (CWE/OWASP) · Complexity · Confidence**,
and fixable ones include a GitHub **`​```suggestion`** block (e.g. `md5` → `hashlib.sha256`).

## 🚀 Key features

**Multi-agent review**
- 8 specialized agents + **Triage/Router** (runs only the relevant agents — cost/latency saver),
  **Consensus** (weighted confidence, not majority vote), and a **Golden-Path** feedback learner.
- **Deterministic-first**: every security claim starts from a scanner/AST rule; the LLM only adds
  capped-confidence suggestions and can *never* suppress a real finding.
- **Confidence-gated auto-approve** for trivial, clean PRs (docs, lockfile bumps).

**Intelligence**
- **Repository memory** — Neo4j-style knowledge graph + Qdrant-style vectors → **blast-radius**,
  **regression-risk**, and **circular-dependency** detection, plus RAG from past findings.
- **Auto-patch generator** (validated, never auto-applied), **PR chat** (injection-safe, rate-limited),
  **multi-model** adapters (Claude · OpenAI · Gemini · DeepSeek · Ollama) with cost routing + fallback.

**Operations**
- **Observability**: Prometheus metrics, OpenTelemetry tracing (one trace per PR), per-PR cost telemetry,
  Grafana dashboard.
- **Dashboard**: tenant-scoped API (OIDC + RBAC, 11 views) + a React/TS/Tailwind/Recharts UI (WCAG 2.2 AA).

**Security-first** (see [SECURITY.md](SECURITY.md))
- HMAC webhooks · GitHub App short-lived tokens · **prompt-injection defenses** · secret redaction before
  logs *and* before any LLM call · **no-egress sandbox** for untrusted code · multi-tenant isolation ·
  **hash-chained audit log** · per-PR token budget · SBOM + signed images.

## 🏗️ Architecture

```
GitHub ──webhook (HMAC)──▶ FastAPI gateway ──queue──▶ LangGraph orchestrator
                                                          │  (parallel fan-out)
        ┌────────────────────────────────────────────────┼───────────────────────────┐
        ▼                ▼            ▼           ▼        ▼         ▼        ▼          ▼
    Security       Architecture  Performance  Testing  DevOps  Accessibility  Docs  AI-Reviewer
        └────────────────────────── shared state ────────────────────────────────────┘
                                     │
                    Consensus (weighted) → Risk score → Auto-patch → Publish to PR
                                     │
     Repository memory (graph + vectors)   ·   Observability (Prom/OTel/cost)   ·   Audit log
```

## ▶️ How to run

### Prerequisites
- **Python 3.12+** (works on 3.14). No external services needed for tests/demos.
- Optional: **Docker** (full stack), **Node 18+** (frontend).

### 1. Quick start — tests & demos (offline, zero config)

```bash
cd backend
python -m venv .venv
source .venv/Scripts/activate        # macOS/Linux: source .venv/bin/activate
pip install -e ".[dev,postgres,phase1,phase3,phase5]"

pytest -q                            # ✅ 198 tests, no services required
python -m examples.review_demo_repo  # review the vulnerable demo repo
python -m examples.demo_review       # end-to-end review of a vulnerable diff
python -m examples.demo_memory       # repository memory learning across PRs
python -m evals                      # detection-quality eval harness (precision/recall/FPR)
```

> On Windows, if console output shows `?` for emoji, prefix with `PYTHONUTF8=1`.

### 2. Run it & open the homepage ⭐

```bash
cd backend
export CG_GITHUB_WEBHOOK_SECRET=dev-secret      # Windows PowerShell: $env:CG_GITHUB_WEBHOOK_SECRET="dev"
uvicorn app.main:app --reload
```
Then open **http://localhost:8000/** — a live landing page where you can **paste code or a public
GitHub PR link and watch it get reviewed** (security score, findings, one-click auto-fixes), fully
offline, no API key. Other endpoints on the same server:

```
GET  /                     the homepage (live "try it" demo)
POST /api/v1/analyze/code  review pasted code        POST /api/v1/analyze/pr   review a public PR
GET  /healthz              liveness                  GET  /metrics             Prometheus metrics
POST /webhooks/github      HMAC-verified PR webhook   GET  /api/v1/dashboard/*  dashboard API (bearer auth)
GET  /docs                 interactive API docs
```

### 3. Full stack (Docker Compose — Postgres, Redis, Neo4j, Qdrant, API)

```bash
cp backend/.env.example backend/.env           # dev only — never commit .env
docker compose -f infra/docker-compose.yml up --build
```

### 4. Frontend (optional — the internal React dashboard)

> The **homepage** (step 2) needs no build — it's served by the backend. This step is only for
> the separate **authenticated analytics dashboard** (11 views), which needs Node.

```bash
cd frontend
npm install
npm run dev                                     # http://localhost:5173 (proxies /api → :8000)
```

## 🧰 Tech stack

**Backend** Python 3.12 · FastAPI · LangGraph · Pydantic · SQLAlchemy + Alembic · Celery · Redis ·
PostgreSQL (RLS) · Neo4j · Qdrant · Prometheus · OpenTelemetry
**Agents/scanners** deterministic rule engine (Semgrep/Bandit/Gitleaks-style) + LLM enrichment
**LLMs** Claude · OpenAI · Gemini · DeepSeek · Ollama (adapter layer)
**Frontend** React · TypeScript · Tailwind · Recharts · TanStack Query
**Infra/CI** Docker · gVisor sandbox · GitHub Actions (ruff · mypy · pytest · Bandit · gitleaks · Trivy ·
OSV · ZAP DAST · SBOM/cosign)

## 📁 Project structure

```
.
├── backend/            FastAPI + LangGraph platform (105 modules, 198 tests)
│   ├── app/            agents · llm · memory · review · patch · chat · feedback · observability · dashboard
│   ├── evals/          detection-quality eval harness
│   ├── examples/       runnable offline demos
│   ├── migrations/     Alembic (+ Postgres row-level security)
│   └── tests/          security-first test suite
├── frontend/           React/TS/Tailwind/Recharts dashboard (WCAG 2.2 AA)
├── demo-repo/          intentionally-vulnerable sample app to review
├── infra/              docker-compose · sandbox (seccomp/Dockerfile) · Grafana dashboard
├── docs/               PRD · build prompts · threat model · security checklist
├── SECURITY.md         disclosure policy + posture
└── .github/            CI, release (SBOM+cosign), Dependabot
```

## 🔒 Security

Security is treated as a hard requirement, not a feature. Highlights: HMAC-verified webhooks,
prompt-injection defenses, secret redaction before logs and before any model call, a no-egress/non-root
sandbox for untrusted code, tenant isolation by construction, and a tamper-evident hash-chained audit log.

- **Posture & disclosure:** [SECURITY.md](SECURITY.md)
- **Threat model (STRIDE):** [docs/THREAT-MODEL.md](docs/THREAT-MODEL.md)
- **Acceptance checklist (§9.9), all green:** [docs/SECURITY-CHECKLIST.md](docs/SECURITY-CHECKLIST.md)

## 🗺️ Build roadmap (all phases complete)

| Phase | Scope | Status |
|---|---|---|
| 0 | Foundations & security baseline (HMAC webhook, redaction, RLS, CI) | ✅ |
| 1 | MVP — LangGraph + 3 agents + consensus + publish + prompt-injection defense | ✅ |
| 2 | Full agent fleet + Triage/Router + auto-approve | ✅ |
| 3 | Repository memory (graph + vectors, blast-radius/regression/cycles) | ✅ |
| 4 | Auto-patch · PR chat · multi-model · Golden-Path learner · explainability | ✅ |
| 5 | Observability (Prom/OTel/cost) + tenant-scoped dashboard API + React UI | ✅ |
| 6 | Enterprise hardening — audit log · RBAC/RLS · sandbox · evals · supply chain | ✅ |


<img width="1917" height="1078" alt="Screenshot 2026-07-15 175325" src="https://github.com/user-attachments/assets/bfdde673-02b9-4f23-87f6-d264c64252af" />
<img width="1917" height="1078" alt="Screenshot 2026-07-15 180332" src="https://github.com/user-attachments/assets/1fbc9d37-2fad-4439-b6ce-f2a36c4db64c" />
<img width="1917" height="1078" alt="Screenshot 2026-07-15 180345" src="https://github.com/user-attachments/assets/e95cd08a-1b65-480b-a2f9-c5ebbfe07a75" />
<img width="1917" height="1078" alt="Screenshot 2026-07-15 180354" src="https://github.com/user-attachments/assets/9768b2ec-b198-49f4-b479-cca364b397c4" />
<img width="1917" height="1078" alt="Screenshot 2026-07-15 180430" src="https://github.com/user-attachments/assets/7ba5253b-dfe5-4d1c-8c12-e7b5e7d2426c" />


## 📚 Docs

- [Full product & engineering spec (PRD)](docs/CodeGuardian-AI-PRD.md)

## 📄 License

Apache-2.0 (see `pyproject.toml`).

---

<div align="center"><sub>Built as a security-first, production-grade multi-agent system — 105 backend modules · 198 tests · 8 agents · 5 LLM providers.</sub></div>
