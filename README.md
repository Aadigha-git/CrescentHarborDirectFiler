# Crescent Harbor Direct Filer

This implementation is intentionally opinionated: correctness before throughput, explicit policy before clever abstractions, and auditable behavior before "smart" automation.

## What I Built

I built a deterministic filing pipeline for one document type (Cargo Arrival Manifest), from scenario input to final authority disposition:

- `builder` constructs a complete manifest from scenario input plus filer identity and signer metadata.
- `validation` applies JSON Schema (`draft 2020-12`) with normalized, actionable error codes.
- `rules` enforces cross-field business rules from `rules/rules.json` and returns structured rejects/warnings.
- `client` signs every request with HMAC-SHA256 per spec and submits/polls the mock authority.
- `polling` enforces protocol behavior (minimum poll interval, terminal-state timeout).
- `pipeline` orchestrates single-file and batch execution.
- `batch_runner` iterates every `scenarios/*.json`, classifies outcomes dynamically, and writes `results.json` in Format B.

The core decision: **treat schema, business rules, and transport as separate gates**. That separation gives us clean ownership and cleaner incident debugging.

## What I Cut (and Why)

I intentionally did not build several things, because they are expensive and distract from proving filing correctness:

1. **Persistent amendment state store**
   - I did not add DB-backed state for `amendmentSequence` lineage.
   - Why: the case study does not require full amendment history persistence; local context is enough to validate pipeline behavior.

2. **Rich observability stack**
   - No OpenTelemetry traces, log shipping, or metrics backend.
   - Why: until throughput and SLO targets are explicit, high-fidelity telemetry is premature optimization.

3. **Secret manager integration**
   - The HMAC secret is loaded from env or local secrets file.
   - Why: acceptable for local/dev grading environment; production secret lifecycle belongs to platform integration.

4. **Parallel filing workers**
   - Batch run is sequential.
   - Why: regulator endpoints usually rate-limit and sequence matters for debugging; optimize only after proving stable correctness.

5. **Automatic retry orchestration beyond simple loop control**
   - No queue-based idempotency/replay framework.
   - Why: good retry semantics require stronger idempotency contracts than this mock exposes.

## How This Scales to 5 Document Types Across 3 Regulators

My stance: **you do not scale by copying pipelines; you scale by standardizing contracts and plugging regulator/document adapters into them.**

### Architecture direction

- Keep one shared execution model:
  `build -> schema -> rules -> transmit -> poll -> normalize outcome`.
- Introduce explicit interfaces:
  - `DocumentBuilder`
  - `SchemaValidator`
  - `RulesEngine`
  - `TransportClient`
  - `AckPoller`
  - `OutcomeMapper`
- Create a registry keyed by `(regulator, document_type)` that wires concrete modules.

### Non-negotiables for multi-regulator scale

1. **Canonical internal domain model per document family**
   - Regulator payload shape is a rendering concern, not your source-of-truth model.

2. **Rules as policy packages, not if/else sprawl**
   - Versioned rulesets (e.g., `regA/v1`, `regB/v3`) with strict compatibility tests.

3. **Transport isolation**
   - HMAC today, mTLS/JWS tomorrow: transport auth must remain swappable without touching builder/rules.

4. **Unified outcome taxonomy**
   - Keep categories stable (`rejected_by_schema`, `rejected_by_rules`, etc.) and map each regulator's native errors into that taxonomy.

5. **Per-regulator compliance evidence**
   - Every run should produce a machine-readable run report + immutable audit event stream.

The anti-pattern to avoid: building one "god orchestrator" with regulator-specific branching spread everywhere.

## What I'd Do Differently With Unlimited Time

If schedule were unconstrained, I would invest in reliability and compliance depth, not just more code:

1. **Move rules into a declarative policy engine**
   - Keep Python for orchestration; externalize policies for traceability and non-engineering review.

2. **Add a durable filing ledger**
   - Immutable append-only events (`built`, `validated`, `submitted`, `acked`) with deterministic replay.

3. **Implement true idempotency and replay controls**
   - Correlation IDs, dedupe windows, and poison-message handling.

4. **Bring in secret management and key rotation**
   - Runtime key fetch, short-lived credentials, and automated rotation tests.

5. **Harden operational controls**
   - Backpressure, circuit breaking, regulator-specific rate governors, and chaos tests.

6. **Compliance-grade observability**
   - Structured logs with PII-safe redaction, audit exports, and dashboarded SLOs by regulator/doc type.

Bottom line: this build is intentionally "correct and inspectable" rather than "feature-rich." That is the right tradeoff at this stage.
