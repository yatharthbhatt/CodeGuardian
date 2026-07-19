"""Typed findings — the structured output every agent must produce (PRD §5, §8.5).

Agents never return free-form text. They return validated :class:`Finding` objects with
a full :class:`Explanation` (Why / Impact / Alternative / References / Complexity /
Confidence), so downstream consensus, scoring, and publishing are deterministic.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

_Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=200)]
_Text = Annotated[str, StringConstraints(max_length=8000)]


class Severity(StrEnum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

    @property
    def weight(self) -> float:
        return {
            Severity.INFO: 0.0,
            Severity.LOW: 1.0,
            Severity.MEDIUM: 3.0,
            Severity.HIGH: 7.0,
            Severity.CRITICAL: 12.0,
        }[self]


class Dimension(StrEnum):
    """Quality dimension an agent owns (maps to the risk scorecard)."""

    SECURITY = "security"
    ARCHITECTURE = "architecture"
    PERFORMANCE = "performance"
    DOCUMENTATION = "documentation"
    TESTING = "testing"
    DEVOPS = "devops"
    ACCESSIBILITY = "accessibility"
    CORRECTNESS = "correctness"


class FindingSource(StrEnum):
    """Provenance — deterministic tools are trusted more than the LLM (PRD rule #8)."""

    DETERMINISTIC = "deterministic"  # scanner/AST rule
    LLM = "llm"  # model-only claim
    HYBRID = "hybrid"  # scanner-detected, LLM-explained


class Explanation(BaseModel):
    """Mandatory explainability payload (PRD §8.5)."""

    model_config = ConfigDict(extra="forbid")

    why: _Text
    impact: _Text
    alternative: _Text = ""
    references: list[Annotated[str, StringConstraints(max_length=500)]] = Field(
        default_factory=list, max_length=20
    )
    complexity: Annotated[str, StringConstraints(max_length=40)] = "unknown"


class Finding(BaseModel):
    """A single, validated review finding."""

    model_config = ConfigDict(extra="forbid")

    agent: Annotated[str, StringConstraints(max_length=64)]
    dimension: Dimension
    category: Annotated[str, StringConstraints(max_length=64)]
    severity: Severity
    confidence: float = Field(ge=0.0, le=1.0)
    title: _Title
    message: _Text
    file_path: Annotated[str | None, StringConstraints(max_length=1024)] = None
    line: int | None = Field(default=None, ge=1)
    cwe: Annotated[str | None, StringConstraints(pattern=r"^CWE-\d+$")] = None
    source: FindingSource = FindingSource.DETERMINISTIC
    explanation: Explanation
    suggested_patch: Annotated[str | None, StringConstraints(max_length=20000)] = None

    def dedupe_key(self) -> tuple[str, str, str, int]:
        """Identity for consensus dedupe: same place + same category = same issue."""
        return (self.dimension.value, self.category, self.file_path or "", self.line or 0)


class LLMFinding(BaseModel):
    """Schema the LLM must fill (a narrower, model-facing view of a finding).

    LLM output is validated against THIS before it is ever trusted (PRD rule #3).
    """

    model_config = ConfigDict(extra="ignore")  # tolerate stray keys, validate the rest

    category: Annotated[str, StringConstraints(max_length=64)]
    severity: Severity
    confidence: float = Field(ge=0.0, le=1.0)
    title: _Title
    message: _Text
    file_path: Annotated[str | None, StringConstraints(max_length=1024)] = None
    line: int | None = Field(default=None, ge=1)
    why: _Text
    impact: _Text
    alternative: _Text = ""
