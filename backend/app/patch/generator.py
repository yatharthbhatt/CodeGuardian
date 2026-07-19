"""Auto-Patch Generator (PRD §8.6).

For findings with a well-understood, mechanical fix, produce a one-line replacement as a
unified diff + a GitHub ``suggestion`` block the developer can apply with one click. We
**never auto-apply** — a human accepts the suggestion. Every generated patch is validated
(balanced delimiters, and for Python it must still parse) so we never post a patch that
would break the file.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass

from app.domain.findings import Finding
from app.review.diff import NormalizedDiff

# category -> ordered (pattern, replacement) mechanical fixes. Each preserves surrounding
# code and only swaps the unsafe token, so syntax is preserved by construction.
_PATCH_RULES: dict[str, list[tuple[re.Pattern[str], str]]] = {
    "weak-hash": [
        (re.compile(r"\bmd5\b"), "sha256"),
        (re.compile(r"\bsha1\b"), "sha256"),
    ],
    "tls-verification-disabled": [
        (re.compile(r"verify\s*=\s*False"), "verify=True"),
        (re.compile(r"rejectUnauthorized\s*:\s*false"), "rejectUnauthorized: true"),
    ],
    "debug-enabled": [
        (re.compile(r"(?i)(\bdebug\b\s*=\s*)True"), r"\1False"),
    ],
    "insecure-deserialization": [
        (re.compile(r"\byaml\.load\("), "yaml.safe_load("),
    ],
    "xss-innerhtml": [
        (re.compile(r"\.innerHTML(\s*)="), r".textContent\1="),
    ],
}


@dataclass
class SuggestedPatch:
    file_path: str
    line: int
    original: str
    fixed: str
    unified_diff: str
    category: str

    def suggestion_block(self) -> str:
        """GitHub applies the fenced ``suggestion`` block to the commented line."""
        return f"```suggestion\n{self.fixed}\n```"


def _delimiters_balanced(text: str) -> bool:
    pairs = {")": "(", "]": "[", "}": "{"}
    stack: list[str] = []
    in_str: str | None = None
    for ch in text:
        if in_str:
            if ch == in_str:
                in_str = None
            continue
        if ch in ("'", '"'):
            in_str = ch
        elif ch in "([{":
            stack.append(ch)
        elif ch in ")]}" and (not stack or stack.pop() != pairs[ch]):
            return False
    return in_str is None and not stack


def _python_still_parses(original: str, fixed: str) -> bool:
    """A Python patch must not turn a parseable line into an unparseable one."""

    def parses(s: str) -> bool:
        try:
            ast.parse(s.strip())
            return True
        except SyntaxError:
            return False

    # If the original line doesn't parse standalone (e.g. it's part of a block), we can't
    # validate via ast; fall back to the delimiter check only.
    if not parses(original):
        return True
    return parses(fixed)


def _validate(original: str, fixed: str, language: str) -> bool:
    if fixed == original or not fixed.strip():
        return False
    if not _delimiters_balanced(fixed):
        return False
    if language == "python":
        return _python_still_parses(original, fixed)
    return True


def _unified_diff(path: str, line: int, original: str, fixed: str) -> str:
    return f"--- a/{path}\n+++ b/{path}\n@@ -{line},1 +{line},1 @@\n-{original}\n+{fixed}\n"


def generate_patch(finding: Finding, diff: NormalizedDiff) -> SuggestedPatch | None:
    """Produce a validated patch for a finding, or None if not mechanically fixable."""
    rules = _PATCH_RULES.get(finding.category)
    if rules is None or finding.file_path is None or finding.line is None:
        return None

    file = next((f for f in diff.files if f.path == finding.file_path), None)
    if file is None:
        return None
    added = next((ln for ln in file.added if ln.new_line == finding.line), None)
    if added is None:
        return None

    original = added.text
    fixed = original
    for pattern, repl in rules:
        new = pattern.sub(repl, fixed)
        if new != fixed:
            fixed = new
            break
    if not _validate(original, fixed, file.language):
        return None
    return SuggestedPatch(
        file_path=finding.file_path,
        line=finding.line,
        original=original,
        fixed=fixed,
        unified_diff=_unified_diff(finding.file_path, finding.line, original, fixed),
        category=finding.category,
    )


def generate_patches(findings: list[Finding], diff: NormalizedDiff) -> list[SuggestedPatch]:
    """Generate patches for all fixable findings and stamp them onto the findings."""
    patches: list[SuggestedPatch] = []
    for finding in findings:
        patch = generate_patch(finding, diff)
        if patch is not None:
            finding.suggested_patch = patch.unified_diff
            patches.append(patch)
    return patches
