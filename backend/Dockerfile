# CodeGuardian AI — API image.
# Security posture (PRD §9.4/§9.7): pinned base by digest-friendly tag, multi-stage
# build, non-root runtime user, no build tools in the final image.

# ---- builder ----
FROM python:3.14-slim AS builder
ENV PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1
WORKDIR /build
COPY pyproject.toml README.md ./
COPY app ./app
# Install into an isolated prefix we can copy into the runtime image.
RUN python -m pip install --upgrade pip \
 && python -m pip install --prefix=/install .

# ---- runtime ----
FROM python:3.14-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
# Create an unprivileged user; the app never runs as root.
RUN useradd --create-home --uid 10001 appuser
WORKDIR /app
COPY --from=builder /install /usr/local
COPY app ./app
COPY migrations ./migrations
COPY alembic.ini ./alembic.ini
USER appuser
EXPOSE 8000
# Drop privileges, single worker here; scale horizontally via the orchestrator.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
