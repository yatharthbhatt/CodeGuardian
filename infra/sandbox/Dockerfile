# CodeGuardian untrusted-code analysis sandbox image (PRD §9.4).
# Minimal, non-root, tool-only image. It NEVER runs the app or holds secrets; it only runs
# static analyzers over a read-only /work mount, launched with the hardened flags in
# app/core/security/sandbox.py (no network, cap-drop ALL, seccomp, resource + time limits).

FROM python:3.12-slim AS sandbox

# Pinned static-analysis tooling. (Versions are examples; pin by digest in real builds.)
RUN pip install --no-cache-dir \
      semgrep==1.90.0 \
      bandit==1.7.10 \
    && useradd --uid 10001 --create-home analyzer

# Drop to the unprivileged user; the runtime also enforces --user, --read-only, etc.
USER 10001
WORKDIR /work

# No ENTRYPOINT that phones home; the caller passes the analyzer + args explicitly.
CMD ["python", "-c", "print('codeguardian sandbox: pass an analyzer command')"]
