from __future__ import annotations

import hashlib
import hmac
import time
from typing import Any


def body_sha256_hex(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def canonical_string(method: str, path: str, timestamp: str, body: bytes) -> str:
    """§10.3: CHCAv3, method, path, timestamp, lowercase hex SHA-256 of body (GET uses empty body)."""
    digest = body_sha256_hex(body)
    return "\n".join(["CHCAv3", method, path, timestamp, digest])


def sign_request(secret: str, method: str, path: str, body: bytes) -> dict[str, str]:
    ts = str(int(time.time()))
    canonical = canonical_string(method, path, ts, body)
    sig = hmac.new(secret.encode("utf-8"), canonical.encode("utf-8"), hashlib.sha256).hexdigest()
    return {
        "X-Crescent-Timestamp": ts,
        "X-Crescent-Signature": sig,
    }


def build_signature_headers(
    filer_id: str,
    secret: str,
    method: str,
    path: str,
    body: bytes,
) -> dict[str, str]:
    headers = sign_request(secret, method, path, body)
    headers["X-Crescent-FilerId"] = filer_id
    return headers


def verify_signature_local(
    secret: str,
    method: str,
    path: str,
    body: bytes,
    headers: dict[str, Any],
) -> bool:
    """Match mock-customs verification (tests)."""
    ts = str(headers.get("X-Crescent-Timestamp", "")).strip()
    sig = str(headers.get("X-Crescent-Signature", "")).strip().lower()
    expected = hmac.new(
        secret.encode("utf-8"),
        canonical_string(method, path, ts, body).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, sig)
