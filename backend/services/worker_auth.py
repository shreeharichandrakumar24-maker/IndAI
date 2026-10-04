"""Worker login helpers (prototype/testing mechanism ONLY). Standard library
only: hashlib scrypt with random salt + constant-time compare, plus short
HMAC-SHA256 Bearer tokens (12 h TTL) minted by mint_token and checked by
verify_token / get_current_worker. No new dependencies.

Prototype/testing mechanism ONLY. The admin app and every other endpoint
keep their existing Supabase auth; only POST /api/worker-auth/login is
public and /api/worker/* rely on the worker Bearer token (see
backend/core/auth_middleware.py).
"""
import hashlib
import hmac
import os
import time
from collections import defaultdict, deque

SCRYPT_N = 2 ** 14
SCRYPT_R = 8
SCRYPT_P = 1
DKLEN = 64

# username -> deque[timestamps of failures]; 10 per 5 min -> 429.
_failures: defaultdict = defaultdict(deque)
MAX_FAILURES = 10
WINDOW_S = 5 * 60


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.scrypt(password.encode("utf-8"), salt=salt,
                        n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=DKLEN)
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, n, r, p, salt_hex, dk_hex = stored.split("$")
        if algo != "scrypt":
            return False
        dk = hashlib.scrypt(password.encode("utf-8"), salt=bytes.fromhex(salt_hex),
                            n=int(n), r=int(r), p=int(p), dklen=len(bytes.fromhex(dk_hex)))
        return hmac.compare_digest(dk.hex(), dk_hex)
    except Exception:
        return False


def rate_limited(username: str) -> bool:
    now = time.time()
    q = _failures[username]
    while q and now - q[0] > WINDOW_S:
        q.popleft()
    return len(q) >= MAX_FAILURES


def record_failure(username: str) -> None:
    _failures[username].append(time.time())


def clear_failures(username: str) -> None:
    _failures.pop(username, None)


# ---- prototype tokens (HMAC-SHA256, stdlib only) ----
# header.payload.signature, base64url, no padding. Payload: employee_id,
# iat, exp (12 h), version. Secret from WORKER_TOKEN_SECRET; if missing, an
# ephemeral secret is generated at startup (one warning) and tokens die on
# restart. Verification is constant-time; failures all look identical.
import base64
import json as _json

TOKEN_TTL_S = 12 * 3600
TOKEN_VERSION = 1

_ephemeral_secret: bytes | None = None
_warned_ephemeral = False


def _secret() -> bytes:
    global _ephemeral_secret, _warned_ephemeral
    try:
        from backend.core.config import settings
        configured = (settings.WORKER_TOKEN_SECRET or "").strip()
    except Exception:
        configured = ""
    if configured:
        return configured.encode("utf-8")
    if _ephemeral_secret is None:
        _ephemeral_secret = os.urandom(32)
    if not _warned_ephemeral:
        _warned_ephemeral = True
        print("WARNING: WORKER_TOKEN_SECRET is not set - using an ephemeral "
              "secret; worker tokens will die on restart.")
    return _ephemeral_secret


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _b64d(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def mint_token(employee_id: str) -> str:
    header = _b64e(_json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    now = int(time.time())
    payload = _b64e(_json.dumps({"employee_id": employee_id, "iat": now,
                                 "exp": now + TOKEN_TTL_S,
                                 "v": TOKEN_VERSION}).encode())
    sig = hmac.new(_secret(), f"{header}.{payload}".encode(),
                   hashlib.sha256).digest()
    return f"{header}.{payload}.{_b64e(sig)}"


def verify_token(token: str) -> str | None:
    """Returns the employee_id, or None for any bad/expired token."""
    try:
        header, payload, sig = token.split(".")
        expected = hmac.new(_secret(), f"{header}.{payload}".encode(),
                            hashlib.sha256).digest()
        if not hmac.compare_digest(_b64e(expected), sig):
            return None
        data = _json.loads(_b64d(payload))
        if data.get("v") != TOKEN_VERSION:
            return None
        if int(data.get("exp", 0)) < int(time.time()):
            return None
        eid = str(data.get("employee_id") or "")
        return eid or None
    except Exception:
        return None
