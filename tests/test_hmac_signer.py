from __future__ import annotations

from crescent_filer.client.hmac_signer import build_signature_headers, verify_signature_local


def test_hmac_matches_mock_customs_canonical() -> None:
    secret = "case-study-shared-secret-do-not-use-in-production-zX4qP9rL"
    body = b'{"manifestId":"TEST"}'
    path = "/v3/manifests"
    headers = build_signature_headers("CHC100001", secret, "POST", path, body)
    assert verify_signature_local(secret, "POST", path, body, headers)

def test_get_ack_empty_body_digest() -> None:
    secret = "x" * 32
    body = b""
    path = "/v3/acks/ABCD1234"
    headers = build_signature_headers("CHC100001", secret, "GET", path, body)
    assert verify_signature_local(secret, "GET", path, body, headers)
