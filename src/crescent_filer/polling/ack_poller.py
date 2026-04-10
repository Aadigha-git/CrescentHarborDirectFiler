from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable

from crescent_filer.client.http_client import CustomsHttpClient


@dataclass
class AckPollResult:
    status: str
    body: dict[str, Any]


def poll_until_terminal(
    client: CustomsHttpClient,
    receipt_id: str,
    *,
    min_interval_seconds: float = 2.0,
    max_wait_seconds: float = 60.0,
    fetch_ack: Callable[[str], dict[str, Any]] | None = None,
) -> AckPollResult:
    """
    §11.2: poll GET /v3/acks/{receiptId} at least 2s apart; §11.3: treat >60s pending as error.
    """
    fetch = fetch_ack or client.fetch_ack
    deadline = time.monotonic() + max_wait_seconds
    last_poll: float | None = None
    while True:
        if last_poll is not None:
            wait = min_interval_seconds - (time.monotonic() - last_poll)
            if wait > 0:
                time.sleep(wait)
        last_poll = time.monotonic()
        body = fetch(receipt_id)
        status = str(body.get("status", ""))
        if status in ("ACCEPTED", "REJECTED"):
            return AckPollResult(status=status, body=body)
        if status != "PENDING":
            return AckPollResult(status=status, body=body)
        if time.monotonic() >= deadline:
            raise TimeoutError(
                f"ack still PENDING after {max_wait_seconds}s (§11.3: contact support if >60s)"
            )
