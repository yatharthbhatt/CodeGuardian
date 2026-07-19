"""Extract graph facts (symbols + dependencies) from a file diff.

Deterministic, regex-based. Python import resolution maps dotted modules to repo-relative
paths so DEPENDS_ON edges line up with actual file nodes (enabling blast-radius). Other
languages contribute symbols; their dependency resolution is added in later phases.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.review.diff import FileDiff

_PY_SYMBOL = re.compile(r"^\s*(?:async\s+)?def\s+(\w+)|^\s*class\s+(\w+)")
_PY_FROM = re.compile(r"^\s*from\s+([\w.]+)\s+import\b")
_PY_IMPORT = re.compile(r"^\s*import\s+([\w.]+)")
_JS_SYMBOL = re.compile(r"\b(?:function|class)\s+(\w+)|\bconst\s+(\w+)\s*=\s*(?:async\s*)?\(")


@dataclass
class FileFacts:
    path: str
    module: str
    symbols: list[str] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)


def _module_of(path: str) -> str:
    return path.rsplit("/", 1)[0] if "/" in path else "."


def _resolve_python_import(dotted: str) -> str:
    """`app.services.auth` -> `app/services/auth.py` (best-effort, deterministic)."""
    return dotted.replace(".", "/") + ".py"


def extract_file_facts(file: FileDiff) -> FileFacts:
    facts = FileFacts(path=file.path, module=_module_of(file.path))
    is_python = file.language == "python"
    for line in file.added:
        text = line.text
        if is_python:
            m = _PY_SYMBOL.match(text)
            if m:
                facts.symbols.append(m.group(1) or m.group(2))
            fm = _PY_FROM.match(text)
            if fm and not fm.group(1).startswith("."):
                facts.depends_on.append(_resolve_python_import(fm.group(1)))
            im = _PY_IMPORT.match(text)
            if im:
                facts.depends_on.append(_resolve_python_import(im.group(1)))
        elif file.language in {"javascript", "typescript"}:
            for jm in _JS_SYMBOL.finditer(text):
                name = jm.group(1) or jm.group(2)
                if name:
                    facts.symbols.append(name)
    # De-dupe while preserving order.
    facts.symbols = list(dict.fromkeys(facts.symbols))
    facts.depends_on = list(dict.fromkeys(facts.depends_on))
    return facts
