"""Sandboxed analysis runner (PRD §9.4, rule #4).

CodeGuardian never executes untrusted PR code on the host. Any execution (or execution of
third-party analyzers over untrusted code) runs in an ephemeral container that is:

  * **no-egress** (``--network none``) — cannot exfiltrate or call home,
  * **non-root** (``--user`` a high uid) with **no new privileges**,
  * **read-only root FS** with a small **noexec/nosuid tmpfs** for scratch,
  * **capability-stripped** (``--cap-drop ALL``) + a restrictive **seccomp** profile,
  * **resource-bounded** (memory, pids, cpus) and **time-bounded** (wall-clock timeout),
  * optionally on the **gVisor** runtime (``runsc``) for kernel isolation.

This module builds the exact hardened command; a runner executes it. The command builder is
pure and unit-tested so the guarantees can't silently regress.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SandboxPolicy:
    memory_mb: int = 512
    pids_limit: int = 128
    cpus: float = 1.0
    timeout_seconds: int = 60
    uid: int = 10001
    use_gvisor: bool = True
    seccomp_profile: str = "infra/sandbox/seccomp.json"
    tmpfs_size_mb: int = 64


def build_sandbox_command(
    image: str,
    args: list[str],
    *,
    source_dir: str,
    policy: SandboxPolicy | None = None,
) -> list[str]:
    """Return a hardened ``docker run`` argv that analyzes ``source_dir`` (mounted read-only)."""
    p = policy or SandboxPolicy()
    if ";" in image or "&" in image:  # defense-in-depth: reject shell metacharacters
        raise ValueError("invalid image reference")

    cmd: list[str] = [
        # Wall-clock timeout; SIGKILL 5s after SIGTERM if it ignores it.
        "timeout",
        "--kill-after=5",
        str(p.timeout_seconds),
        "docker",
        "run",
        "--rm",
        "--network=none",  # no egress
        "--read-only",  # immutable root filesystem
        "--cap-drop=ALL",  # drop all Linux capabilities
        "--security-opt=no-new-privileges",
        f"--security-opt=seccomp={p.seccomp_profile}",
        f"--user={p.uid}:{p.uid}",  # non-root
        f"--memory={p.memory_mb}m",
        f"--memory-swap={p.memory_mb}m",  # disable swap (== memory)
        f"--pids-limit={p.pids_limit}",
        f"--cpus={p.cpus}",
        f"--tmpfs=/tmp:rw,noexec,nosuid,size={p.tmpfs_size_mb}m",
        "--workdir=/work",
        f"--volume={source_dir}:/work:ro",  # untrusted source is read-only
    ]
    if p.use_gvisor:
        cmd.append("--runtime=runsc")
    cmd.append(image)
    cmd.extend(args)
    return cmd


# Flags that MUST be present for a command to count as hardened (used by tests + a runtime
# self-check before any sandbox launch).
REQUIRED_HARDENING = (
    "--network=none",
    "--read-only",
    "--cap-drop=ALL",
    "--security-opt=no-new-privileges",
)


def is_hardened(cmd: list[str]) -> bool:
    if not all(flag in cmd for flag in REQUIRED_HARDENING):
        return False
    has_nonroot_user = any(f.startswith("--user=") and not f.endswith("=0:0") for f in cmd)
    has_timeout = "timeout" in cmd
    has_seccomp = any(f.startswith("--security-opt=seccomp=") for f in cmd)
    return has_nonroot_user and has_timeout and has_seccomp
