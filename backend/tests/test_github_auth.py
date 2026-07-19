"""GitHub App JWT auth tests (PRD §9.1) — short-lived, correctly signed, no PATs."""

from __future__ import annotations

import time

import jwt
import pytest
from app.github.auth import GitHubAppAuth
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


@pytest.fixture(scope="module")
def keypair() -> tuple[str, str]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    public_pem = (
        key.public_key()
        .public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode()
    )
    return private_pem, public_pem


def test_app_jwt_is_valid_and_has_expected_claims(keypair: tuple[str, str]) -> None:
    private_pem, public_pem = keypair
    now = int(time.time())
    token = GitHubAppAuth("123456", private_pem).app_jwt(now=now)
    decoded = jwt.decode(token, public_pem, algorithms=["RS256"], options={"verify_exp": True})
    assert decoded["iss"] == "123456"
    assert decoded["iat"] <= now  # backdated for clock skew
    assert decoded["exp"] > now


def test_app_jwt_lifetime_never_exceeds_10_minutes(keypair: tuple[str, str]) -> None:
    private_pem, _ = keypair
    now = int(time.time())
    # Even if we ask for an hour, it is clamped to <= 10 minutes.
    token = GitHubAppAuth("1", private_pem).app_jwt(now=now, ttl=3600)
    decoded = jwt.decode(
        token, key=private_pem, algorithms=["RS256"], options={"verify_signature": False}
    )
    assert decoded["exp"] - now <= 600


def test_app_jwt_signature_is_required(keypair: tuple[str, str]) -> None:
    private_pem, _ = keypair
    token = GitHubAppAuth("1", private_pem).app_jwt()
    # A different key must fail verification.
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    other_pub = (
        other.public_key()
        .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        .decode()
    )
    with pytest.raises(jwt.InvalidSignatureError):
        jwt.decode(token, other_pub, algorithms=["RS256"])
