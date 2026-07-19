"""Strict Pydantic models for the GitHub webhook payloads we accept (PRD §9.3).

We only model the fields we actually use and validate them tightly (bounded lengths,
allowed enum values). ``extra="ignore"`` lets GitHub add fields without breaking us,
while our own top-level envelope stays strict. Anything that fails validation is
rejected at the edge before it can reach the orchestrator.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

_Str = Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)]
_ShortStr = Annotated[str, StringConstraints(strip_whitespace=True, max_length=255)]
_Sha = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{7,64}$")]


class _Base(BaseModel):
    # Ignore unknown fields (GitHub sends many we don't need) but validate the ones we map.
    model_config = ConfigDict(extra="ignore", str_max_length=65_536)


class PullRequestAction(StrEnum):
    """The subset of PR actions that should trigger (or clean up) a review."""

    OPENED = "opened"
    REOPENED = "reopened"
    SYNCHRONIZE = "synchronize"
    EDITED = "edited"
    READY_FOR_REVIEW = "ready_for_review"
    CLOSED = "closed"


class GitHubUser(_Base):
    login: _ShortStr
    id: int = Field(ge=0)


class GitHubRepo(_Base):
    id: int = Field(ge=0)
    full_name: Annotated[str, StringConstraints(max_length=512, pattern=r"^[^/]+/[^/]+$")]
    private: bool = False


class GitHubInstallation(_Base):
    id: int = Field(ge=0)


class PullRequestRef(_Base):
    sha: _Sha
    ref: _ShortStr


class PullRequest(_Base):
    number: int = Field(ge=1)
    title: _Str
    body: Annotated[str | None, Field(max_length=65_536)] = None
    state: _ShortStr
    draft: bool = False
    head: PullRequestRef
    base: PullRequestRef
    user: GitHubUser


class PullRequestEvent(_Base):
    """The ``pull_request`` webhook event envelope."""

    action: PullRequestAction
    number: int = Field(ge=1)
    pull_request: PullRequest
    repository: GitHubRepo
    sender: GitHubUser
    installation: GitHubInstallation | None = None

    @property
    def should_review(self) -> bool:
        """Only run reviews for non-draft PRs on meaningful actions."""
        if self.pull_request.draft and self.action is not PullRequestAction.READY_FOR_REVIEW:
            return False
        return self.action in {
            PullRequestAction.OPENED,
            PullRequestAction.REOPENED,
            PullRequestAction.SYNCHRONIZE,
            PullRequestAction.READY_FOR_REVIEW,
        }
