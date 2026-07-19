from __future__ import annotations

from app.review.diff import parse_unified_diff

_SAMPLE = """diff --git a/app/x.py b/app/x.py
new file mode 100644
--- /dev/null
+++ b/app/x.py
@@ -0,0 +1,3 @@
+import os
+
+def hello():
diff --git a/app/y.js b/app/y.js
--- a/app/y.js
+++ b/app/y.js
@@ -10,2 +10,3 @@
 context line
-old = 1
+const token = 'x'
+el.innerHTML = user
"""


def test_parses_files_and_added_lines() -> None:
    d = parse_unified_diff(_SAMPLE)
    paths = {f.path for f in d.files}
    assert paths == {"app/x.py", "app/y.js"}
    assert d.total_added == 5


def test_new_file_flagged_and_line_numbers() -> None:
    d = parse_unified_diff(_SAMPLE)
    x = next(f for f in d.files if f.path == "app/x.py")
    assert x.is_new_file
    assert x.added[0].new_line == 1
    assert x.added[2].text == "def hello():"


def test_language_detection() -> None:
    d = parse_unified_diff(_SAMPLE)
    assert {f.language for f in d.files} == {"python", "javascript"}


def test_removed_lines_counted_not_added() -> None:
    d = parse_unified_diff(_SAMPLE)
    y = next(f for f in d.files if f.path == "app/y.js")
    assert y.removed_count == 1
    assert any("innerHTML" in ln.text for ln in y.added)
