"""Password hashing — PBKDF2-HMAC-SHA256, from the standard library.

Deliberately dependency-free. Argon2id is the modern first choice, but it needs
a compiled extension; PBKDF2-HMAC-SHA256 at OWASP's recommended iteration count
is an approved alternative, ships with Python, and removes a build dependency
from a project meant to run locally on Windows without a toolchain.

Stored format is self-describing so the parameters can be raised later without
invalidating existing hashes:

    pbkdf2_sha256$<iterations>$<salt_b64>$<hash_b64>

Verification reads the iteration count from the stored hash rather than the
current constant, so old hashes keep verifying after ``_ITERATIONS`` increases.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

_ALGORITHM = "pbkdf2_sha256"
# OWASP Password Storage Cheat Sheet, PBKDF2-HMAC-SHA256.
_ITERATIONS = 600_000
_SALT_BYTES = 16
_HASH_BYTES = 32


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _unb64(value: str) -> bytes:
    return base64.b64decode(value.encode("ascii"))


def hash_password(password: str) -> str:
    """Hash a password with a fresh random salt."""
    salt = secrets.token_bytes(_SALT_BYTES)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, _ITERATIONS, dklen=_HASH_BYTES
    )
    return f"{_ALGORITHM}${_ITERATIONS}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, stored: str | None) -> bool:
    """Check a password against a stored hash.

    Returns False (never raises) for a missing or malformed hash, so a
    Google-only account — which has ``password_hash = NULL`` — simply fails
    password login instead of erroring.
    """
    if not stored:
        return False
    try:
        algorithm, iterations_raw, salt_b64, hash_b64 = stored.split("$")
        if algorithm != _ALGORITHM:
            return False
        iterations = int(iterations_raw)
        salt = _unb64(salt_b64)
        expected = _unb64(hash_b64)
    except (ValueError, TypeError):
        return False

    candidate = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, iterations, dklen=len(expected)
    )
    # Constant-time: a short-circuiting comparison leaks how many bytes matched.
    return hmac.compare_digest(candidate, expected)


def needs_rehash(stored: str | None) -> bool:
    """True when a stored hash uses weaker parameters than the current policy.

    Lets a successful login transparently upgrade an old hash.
    """
    if not stored:
        return False
    try:
        algorithm, iterations_raw, _, _ = stored.split("$")
    except ValueError:
        return True
    return algorithm != _ALGORITHM or int(iterations_raw) < _ITERATIONS
