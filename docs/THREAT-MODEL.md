# CodeGuardian AI — Threat Model (STRIDE)

Scope: the review pipeline (webhook → orchestrator → agents → LLM → publish), the
dashboard API, repository memory, and the platform's own supply chain. Trust boundaries:

```
[GitHub] --webhook--> (B1) [API Gateway] --queue--> (B2) [Orchestrator/Agents]
                                   |                          |
                              (B4) [Dashboard API/OIDC]   (B3) [LLM providers]  (B5) [Sandbox]
                                   |                          |
                              [Datastores: Postgres/Neo4j/Qdrant/Redis]  <-- (B6) tenant boundary
```

Assets: source code/diffs (untrusted, confidential), secrets, findings, tenant data,
model API keys, the audit log, the platform's build artifacts.

## STRIDE analysis

### Spoofing
- **Forged webhooks / spoofed GitHub.** → HMAC-SHA256 verification over raw bytes, constant-time
  compare, replay guard (B1). GitHub App JWT (short-lived) for outbound calls — no PATs.
- **Impersonating a dashboard user/tenant.** → OIDC/bearer auth; tenant is derived from the
  token, never client input; RBAC via `require_role` (B4).

### Tampering
- **Mutating the audit trail.** → append-only, **hash-chained** audit log; `verify()` detects any
  insert/delete/reorder/mutation (B1/B4).
- **Tampering with data in transit / at rest.** → TLS in transit; at-rest encryption on datastores.
- **Malicious auto-patch corrupting a repo.** → patches are validated (AST/delimiter) and only
  *suggested*; the platform never writes to the repo (B2).

### Repudiation
- **"I didn't submit that feedback / trigger that action."** → every state-changing action is
  audited with actor + hash-chained integrity (B1/B4).

### Information Disclosure
- **Secrets leaking to logs.** → structured logging with a redaction filter; `SecretStr` (B1).
- **Secrets/PII exfiltrated to an LLM provider.** → secret redaction *before* any content leaves;
  zero-retention provider flags; code never used for training (B3).
- **Cross-tenant data exposure.** → tenant scoping by construction in every store + Postgres RLS;
  verified by isolation tests (B6).
- **Prompt injection exfiltrating context / changing behavior.** → untrusted PR content is
  delimited/labeled as data, system carries an override directive, model output is schema-validated
  and constrained to files in the diff; deterministic findings can't be suppressed by text (B2/B3).

### Denial of Service
- **Oversized/looping webhooks.** → body-size cap, strict validation, queue back-pressure (B1).
- **Economic DoS (runaway LLM spend).** → hard per-PR `TokenBudget` + cost telemetry/alerts (B3).
- **Chat abuse.** → per-thread token-bucket rate limiting (B4).
- **Malicious code exhausting resources.** → sandbox memory/pids/cpu + wall-clock limits (B5).

### Elevation of Privilege
- **Untrusted code escaping to the host.** → no code execution on host; ephemeral **no-egress,
  non-root, read-only, cap-dropped, seccomp, gVisor** sandbox (B5).
- **Under-privileged role accessing sensitive views/actions.** → RBAC rank checks (e.g. Audit Log
  requires maintainer+); feedback requires member+ (B4).
- **Compromised dependency / build.** → pinned+hashed deps, Dependabot, Trivy/OSV/Grype, SBOM
  (syft), signed images (cosign), branch protection + required reviews on the platform repo.

## Residual risks / follow-ups
- LLM providers are external trust dependencies — mitigated by redaction, zero-retention, and
  multi-provider fallback, but not eliminated.
- Deterministic rules are regex/heuristic (not full dataflow) — the eval harness tracks precision/
  recall so regressions are caught; deeper SAST engines (Semgrep) run in the sandbox.
- The in-memory stores are reference implementations; production uses Postgres RLS / Neo4j / Qdrant
  with the same tenant-isolation contract (enforced + tested).
