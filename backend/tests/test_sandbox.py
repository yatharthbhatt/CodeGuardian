"""Sandbox hardening tests (PRD §9.4) — the command must be locked down by construction."""

from __future__ import annotations

import pytest
from app.core.security.sandbox import (
    SandboxPolicy,
    build_sandbox_command,
    is_hardened,
)


def _cmd() -> list[str]:
    return build_sandbox_command("semgrep:1.2.3", ["scan", "/work"], source_dir="/repos/x")


def test_command_is_hardened() -> None:
    cmd = _cmd()
    assert is_hardened(cmd)
    # Explicit checks for the critical guarantees.
    assert "--network=none" in cmd  # no egress
    assert "--read-only" in cmd
    assert "--cap-drop=ALL" in cmd
    assert "--security-opt=no-new-privileges" in cmd
    assert any(f.startswith("--user=") for f in cmd)
    assert "timeout" in cmd  # wall-clock bound


def test_resource_limits_applied() -> None:
    cmd = build_sandbox_command(
        "img", [], source_dir="/x", policy=SandboxPolicy(memory_mb=256, pids_limit=64, cpus=0.5)
    )
    assert "--memory=256m" in cmd
    assert "--memory-swap=256m" in cmd  # swap disabled
    assert "--pids-limit=64" in cmd
    assert "--cpus=0.5" in cmd


def test_source_is_mounted_read_only() -> None:
    cmd = build_sandbox_command("img", [], source_dir="/repos/untrusted")
    assert "--volume=/repos/untrusted:/work:ro" in cmd


def test_gvisor_runtime_toggle() -> None:
    assert "--runtime=runsc" in build_sandbox_command("i", [], source_dir="/x")
    off = build_sandbox_command("i", [], source_dir="/x", policy=SandboxPolicy(use_gvisor=False))
    assert "--runtime=runsc" not in off


def test_rejects_image_with_shell_metacharacters() -> None:
    with pytest.raises(ValueError):
        build_sandbox_command("img; rm -rf /", [], source_dir="/x")


def test_is_hardened_rejects_root_or_networked_command() -> None:
    assert not is_hardened(["docker", "run", "--user=0:0"])  # root
    assert not is_hardened(["docker", "run", "--read-only"])  # missing egress/caps
