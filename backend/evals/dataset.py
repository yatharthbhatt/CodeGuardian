"""Labeled PR dataset for the eval harness.

Each case is a small diff with the SECURITY finding categories we expect (an empty set
means the change is clean and must NOT produce security findings — these double as
false-positive probes).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class LabeledPR:
    id: str
    title: str
    files: tuple[tuple[str, tuple[str, ...]], ...]
    expected_security: frozenset[str] = field(default_factory=frozenset)


DATASET: tuple[LabeledPR, ...] = (
    # --- true positives ----------------------------------------------------
    LabeledPR(
        "sql-injection",
        "Add user lookup",
        (("app/db.py", ('cursor.execute(f"SELECT * FROM users WHERE id={uid}")',)),),
        frozenset({"sql-injection"}),
    ),
    LabeledPR(
        "eval",
        "Evaluate expression",
        (("app/calc.py", ("result = eval(request.args.get('expr'))",)),),
        frozenset({"dangerous-eval"}),
    ),
    LabeledPR(
        "weak-hash",
        "Hash password",
        (("app/auth.py", ("digest = md5(password.encode())",)),),
        frozenset({"weak-hash"}),
    ),
    LabeledPR(
        "hardcoded-secret",
        "Wire API client",
        (("app/client.py", ("API_TOKEN = 'ghp_AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA'",)),),
        frozenset({"hardcoded-secret"}),
    ),
    LabeledPR(
        "tls-disabled",
        "Call upstream",
        (("app/http.py", ("resp = requests.get(url, verify=False)",)),),
        frozenset({"tls-verification-disabled"}),
    ),
    LabeledPR(
        "insecure-deser",
        "Load config",
        (("app/cfg.py", ("data = yaml.load(open('c.yml'))",)),),
        frozenset({"insecure-deserialization"}),
    ),
    # --- clean / false-positive probes (expected: no security findings) -----
    LabeledPR(
        "clean-math",
        "Add helper",
        (("app/util.py", ('"""Add two numbers."""', "def add(a, b):", "    return a + b")),),
        frozenset(),
    ),
    LabeledPR(
        "fp-probe-names",
        "Rename config keys",
        (("app/cfg.py", ("hash_algo = 'sha256'", "verify_email = True", "password_label = 'x'")),),
        frozenset(),
    ),
)
