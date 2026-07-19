# CodeGuardian AI — Backend

FastAPI + LangGraph backend for the multi-agent autonomous code-review platform.
See [`../docs/CodeGuardian-AI-PRD.md`](../docs/CodeGuardian-AI-PRD.md) for the full spec.

## Layout

```
backend/
├── app/
│   ├── main.py                 # FastAPI app factory
│   ├── config.py               # Pydantic Settings (no secrets in code)
│   ├── logging_config.py       # structured JSON logging + redaction
│   ├── api/
│   │   ├── deps.py             # shared DI providers
│   │   └── routes/             # health, webhooks (Phase 1: reviews, chat, feedback)
│   ├── core/security/          # webhook HMAC/replay, redaction
│   ├── middleware/             # request-id correlation
│   ├── schemas/                # strict Pydantic models (GitHub payloads)
│   └── db/                     # SQLAlchemy base, models (§10), session (RLS)
├── migrations/                 # Alembic (+ Postgres row-level security)
└── tests/                      # security-first test suite
```

## Quick start (local)

```bash
cd backend
python -m venv .venv && source .venv/Scripts/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev,postgres]"
cp .env.example .env            # dev only — never commit .env
pytest -q                       # 45+ tests, no external services needed (SQLite/in-memory)
uvicorn app.main:app --reload   # http://localhost:8000/docs
```

Full stack (Postgres/Redis/Neo4j/Qdrant + API): `docker compose -f ../infra/docker-compose.yml up`.

## Database migrations

```bash
# URL is read from CG_DATABASE_URL (secret-manager sourced); never stored in alembic.ini
alembic upgrade head       # creates schema + enables RLS on Postgres
```

## Security invariants enforced here (PRD §9)

| Concern | Where |
|---|---|
| Webhook authenticity (HMAC-SHA256, constant-time) | `app/core/security/webhook.py` |
| Replay protection (per-delivery-id) | `InMemoryReplayGuard` (Redis-backed in Phase 1) |
| Strict input validation | `app/schemas/github.py`, endpoint order-of-checks |
| No secrets in code | `app/config.py` (`SecretStr`, env-only) |
| No secrets/PII in logs | `app/logging_config.py` + `redaction.py` |
| Tenant isolation | `db/base.py` (`tenant_id`), migration RLS, `db/session.py` |
| Fail-closed webhook | size cap → HMAC → replay → validate → enqueue |

## Env vars

All are `CG_`-prefixed and documented in [`.env.example`](.env.example). Unknown vars are
rejected at startup (fail-fast). Secrets use `SecretStr` and never appear in logs/reprs.
