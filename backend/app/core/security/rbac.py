"""Roles and rank ordering (PRD §9.2).

Central definition so both the dashboard API (Phase 5) and full RBAC enforcement
(Phase 6) share one source of truth.
"""

from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    MAINTAINER = "maintainer"
    MEMBER = "member"
    READ_ONLY = "read_only"
    SERVICE = "service"  # machine principal (webhooks/workers)


# Higher rank = more privilege. SERVICE is treated as high-trust internal.
_RANK: dict[Role, int] = {
    Role.READ_ONLY: 0,
    Role.MEMBER: 1,
    Role.MAINTAINER: 2,
    Role.ADMIN: 3,
    Role.OWNER: 4,
    Role.SERVICE: 4,
}


def rank(role: Role) -> int:
    return _RANK[role]


def at_least(role: Role, minimum: Role) -> bool:
    return rank(role) >= rank(minimum)
