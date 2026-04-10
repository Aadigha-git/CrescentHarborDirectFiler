from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import httpx

from crescent_filer.client.hmac_signer import build_signature_headers


@dataclass
class SubmitResult:
    receipt_id: str
    manifest_id: str
    status: str
    raw: dict[str, Any]


class CustomsHttpClient:
    def __init__(
        self,
        base_url: str,
        filer_id: str,
        shared_secret: str,
        *,
        timeout: float = 60.0,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._filer_id = filer_id
        self._secret = shared_secret
        self._timeout = timeout

    def submit_manifest(self, manifest: dict[str, Any]) -> SubmitResult:
        body_bytes = json.dumps(manifest, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        path = "/v3/manifests"
        headers = build_signature_headers(self._filer_id, self._secret, "POST", path, body_bytes)
        url = f"{self._base}{path}"
        with httpx.Client(timeout=self._timeout) as client:
            r = client.post(url, content=body_bytes, headers={**headers, "Content-Type": "application/json"})
        if r.status_code == 401:
            raise httpx.HTTPStatusError(
                f"transport auth failed: {r.text}",
                request=r.request,
                response=r,
            )
        if r.status_code == 409:
            raise httpx.HTTPStatusError("duplicate manifestId", request=r.request, response=r)
        r.raise_for_status()
        data = r.json()
        return SubmitResult(
            receipt_id=str(data["receiptId"]),
            manifest_id=str(data["manifestId"]),
            status=str(data.get("status", "")),
            raw=data,
        )

    def fetch_ack(self, receipt_id: str) -> dict[str, Any]:
        path = f"/v3/acks/{receipt_id}"
        headers = build_signature_headers(self._filer_id, self._secret, "GET", path, b"")
        url = f"{self._base}{path}"
        with httpx.Client(timeout=self._timeout) as client:
            r = client.get(url, headers=headers)
        if r.status_code in (401, 403, 404):
            r.raise_for_status()
        r.raise_for_status()
        return r.json()
