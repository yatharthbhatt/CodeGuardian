# Demo repo — intentionally vulnerable

> ⚠️ **This code is deliberately insecure. Never deploy it.** It exists only so you can watch
> **CodeGuardian AI** review it and catch real issues.

## Planted issues (what the reviewer should find)

| File | Issue | CWE |
|---|---|---|
| `app.py` | Hardcoded secret (fake token) | CWE-798 |
| `app.py` | SQL injection via f-string | CWE-89 |
| `app.py` | `eval()` on user input | CWE-95 |
| `app.py` | Weak hash (MD5) | CWE-327 |
| `app.py` | TLS verification disabled (`verify=False`) | CWE-295 |
| `app.py` | Insecure deserialization (`yaml.load`) | CWE-502 |
| `app.py` | Debug mode enabled | CWE-489 |
| `Dockerfile` | Unpinned base image (`python:latest`) | CWE-1104 |

## Review it

```bash
cd ../backend
python -m examples.review_demo_repo      # reviews this folder and prints the findings
```

You'll see security findings (several with one-click **`​```suggestion`** auto-fixes, e.g.
`md5` → `hashlib.sha256`), a risk scorecard, and a blocking verdict — all offline, no API key.
