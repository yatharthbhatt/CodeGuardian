"""Minimal unified-diff parser → NormalizedDiff.

Turns a raw unified diff (from the GitHub compare/PR API) into a structured, per-file
view of the *added* lines with their new line numbers, which is what the deterministic
agent rules operate on. Intentionally dependency-free and bounded.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")

# Coarse language guess from extension — good enough to route agents in Phase 1.
_LANG_BY_EXT = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".jsx": "javascript",
    ".go": "go",
    ".rb": "ruby",
    ".java": "java",
    ".rs": "rust",
    ".php": "php",
    ".cs": "csharp",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".tf": "terraform",
    ".md": "markdown",
    ".html": "html",
    ".css": "css",
    ".sql": "sql",
}


@dataclass(frozen=True)
class AddedLine:
    new_line: int
    text: str


@dataclass
class FileDiff:
    path: str
    is_new_file: bool = False
    added: list[AddedLine] = field(default_factory=list)
    removed_count: int = 0

    @property
    def language(self) -> str:
        idx = self.path.rfind(".")
        return _LANG_BY_EXT.get(self.path[idx:].lower(), "other") if idx != -1 else "other"

    @property
    def added_text(self) -> str:
        return "\n".join(line.text for line in self.added)


@dataclass
class NormalizedDiff:
    files: list[FileDiff] = field(default_factory=list)

    @property
    def total_added(self) -> int:
        return sum(len(f.added) for f in self.files)

    @property
    def languages(self) -> set[str]:
        return {f.language for f in self.files}


def parse_unified_diff(diff_text: str, *, max_lines: int = 200_000) -> NormalizedDiff:
    """Parse a unified diff. Bounded by ``max_lines`` to cap work on huge diffs."""
    result = NormalizedDiff()
    current: FileDiff | None = None
    new_lineno = 0
    pending_new_file = False  # `new file mode` precedes the `+++` header in git output

    for raw in diff_text.splitlines()[:max_lines]:
        if raw.startswith("diff --git"):
            current = None
            pending_new_file = False
            continue
        if raw.startswith("new file mode"):
            pending_new_file = True
            continue
        if raw.startswith("+++ "):
            path = raw[4:].strip()
            path = path[2:] if path.startswith("b/") else path
            if path == "/dev/null":
                current = None
                continue
            current = FileDiff(path=path, is_new_file=pending_new_file)
            pending_new_file = False
            result.files.append(current)
            continue
        if raw.startswith("--- "):
            continue
        m = _HUNK.match(raw)
        if m:
            new_lineno = int(m.group(1))
            continue
        if current is None:
            continue
        if raw.startswith("+"):
            current.added.append(AddedLine(new_line=new_lineno, text=raw[1:]))
            new_lineno += 1
        elif raw.startswith("-"):
            current.removed_count += 1
        else:  # context line
            new_lineno += 1

    return result
