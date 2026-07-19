"""Offline end-to-end demo of a CodeGuardian review.

Runs the full LangGraph pipeline on a deliberately vulnerable diff using the offline
FakeProvider (no network / no API key), then prints the exact PR review that would be
posted. Run: `python -m examples.demo_review`
"""

from __future__ import annotations

import asyncio

from app.github.client import FakeGitHubReviewClient
from app.llm.providers.fake import FakeProvider
from app.llm.router import LLMRouter
from app.review.diff import parse_unified_diff
from app.review.state import PRMeta
from app.worker.pipeline import process_pull_request

_VULNERABLE_DIFF = """diff --git a/app/auth.py b/app/auth.py
new file mode 100644
--- /dev/null
+++ b/app/auth.py
@@ -0,0 +1,9 @@
+import hashlib
+API_TOKEN = "ghp_AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
+def login(username, password, db):
+    query = f"SELECT * FROM users WHERE name='{username}'"
+    db.execute(query)
+    digest = hashlib.md5(password.encode()).hexdigest()
+    if eval(request.args.get("expr", "0")):
+        pass
+    return digest
"""


async def main() -> None:
    pr = PRMeta(
        tenant_id="demo-tenant",
        repo_full_name="acme/webapp",
        number=101,
        title="Add login endpoint",
        body="Implements user login.",
        author="dev",
        head_sha="a" * 40,
        base_sha="b" * 40,
    )
    diff = parse_unified_diff(_VULNERABLE_DIFF)
    client = FakeGitHubReviewClient()
    result = await process_pull_request(
        pr, diff, client=client, router=LLMRouter(FakeProvider()), use_llm=True
    )

    print("=" * 70)
    if result.routing is not None:
        print(f"Triage selected agents: {result.routing.selected}")
        print(
            f"Trivial: {result.routing.is_trivial} | auto-approve eligible: "
            f"{result.routing.auto_approve_eligible}"
        )
    print("=" * 70)
    print(f"Overall Engineering Score: {result.risk['overall']}/100")
    print(f"Blocking: {result.consensus.blocking}  | tokens used: {result.tokens_used}")
    print(f"Findings: {len(result.findings)}  | consensus: {result.consensus.reasoning}")
    print("=" * 70)
    print("RISK SCORECARD:", result.risk)
    print("=" * 70)
    review = client.reviews[0]
    print(f"PR review event: {review.event.value}")
    print(review.body)
    print("-" * 70)
    for c in review.comments:
        print(f"\n# {c.path}:{c.line}\n{c.body}")
    print("=" * 70)
    print(f"Status check: {client.checks[0][2].value}")


if __name__ == "__main__":
    asyncio.run(main())
