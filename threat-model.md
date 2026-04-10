# Threat Model

This document is intentionally practical: what can go wrong in this filer, where sensitive data exists, and what evidence a security reviewer gets.

## Sensitive Data: Where It Lives

### At rest

- **Scenario/manifests** may contain personal data (crew names, passport numbers, dates of birth) and commercial shipment data.
- **`results.json`** stores outcomes and error payloads; this can include regulator rejection details that may contain sensitive fields.
- **HMAC secret** is read from environment (`CRESCENT_SHARED_SECRET`) or local file (`mock-customs/secrets.json` in this case-study setup).

### In memory / in transit

- Full manifest payloads are assembled in process memory before submission.
- HMAC canonical strings and signatures are computed in process memory.
- Manifest and ack traffic travels over HTTP to the mock service in this environment; production must enforce TLS/mTLS.

## HMAC Secret Handling

Current posture:

- Secret is **not hardcoded in code**; it is injected via env or loaded from a configured secrets file.
- Secret is used only to derive request signatures and is not written to output artifacts by design.

Gaps (known):

- No KMS/HSM integration.
- No automated key rotation.
- Local file fallback is acceptable for development but not production.

Production expectation:

- Retrieve secret at runtime from a managed secret store.
- Rotate keys on a schedule with dual-key overlap windows.
- Treat signature failures as security events, not just transport errors.

## Audit Trail Design

A useful audit trail is an immutable sequence of filing events with correlated IDs:

1. `manifest_built` (`manifestId`, scenario source, timestamp)
2. `schema_validated` (pass/fail + normalized errors)
3. `rules_evaluated` (rejects/warnings with rule IDs)
4. `transmitted` (`receiptId`, endpoint, timestamp, signer identity)
5. `ack_polled` (`PENDING/ACCEPTED/REJECTED`, final error catalog)
6. `run_report_written` (hash of `results.json`, actor, timestamp)

Current implementation already provides much of this in `results.json` (Format B), but a production trail should be append-only and tamper-evident.

## What a Security Reviewer Should See

A reviewer should be able to answer these quickly:

- **Data flow clarity**: exact boundaries where PII enters, is transformed, transmitted, and persisted.
- **Secret hygiene**: no plaintext secret in source, logs, or reports; clear secret source and rotation policy.
- **Control points**: schema gate, business-rule gate, and transport auth gate are separated and testable.
- **Failure behavior**: invalid documents are rejected early; unknown outcomes are surfaced as explicit `error`, never silently accepted.
- **Evidence quality**: deterministic `results.json` output per run, with per-scenario classification and error details.

Opinionated conclusion: the highest risk is not HMAC math; it is uncontrolled data sprawl (manifests/results in too many places) and weak operational discipline around secrets. Fix those first.
