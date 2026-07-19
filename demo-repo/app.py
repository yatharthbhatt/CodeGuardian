"""Intentionally VULNERABLE sample app — for demonstrating CodeGuardian AI only.

⚠️  DO NOT DEPLOY. Every "issue" below is planted on purpose so the reviewer can catch it.
"""

import hashlib
import sqlite3

import requests
import yaml
from flask import Flask, request

app = Flask(__name__)

# ❌ Hardcoded secret (FAKE token — not a real credential).
API_TOKEN = "ghp_FAKEFAKEFAKEFAKEFAKEFAKEFAKEFAKE01"
# ❌ Debug mode enabled.
DEBUG = True


def login(username, password):
    conn = sqlite3.connect("app.db")
    cur = conn.cursor()
    # ❌ SQL injection via string interpolation.
    cur.execute(f"SELECT * FROM users WHERE name='{username}'")
    # ❌ Weak password hashing (MD5).
    return hashlib.md5(password.encode()).hexdigest()


@app.route("/run")
def run_expr():
    # ❌ Arbitrary code execution from user input.
    return str(eval(request.args.get("expr", "0")))


def fetch(url):
    # ❌ TLS certificate verification disabled.
    return requests.get(url, verify=False)


def load_config(path):
    # ❌ Insecure deserialization.
    with open(path) as fh:
        return yaml.load(fh)
