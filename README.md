# Crescent Harbor Direct Filer
## Running

This repo assumes **Python 3.11+**. On Windows, make sure you run `pip` and `python` from the **same interpreter**.

### 1) Install

PowerShell:

```powershell
cd c:\Users\baaad\Desktop\CrescentHarborDirectFiler
py -3.11 -m pip install -e ".[dev]"
```

bash:

```bash
cd /path/to/CrescentHarborDirectFiler
python3 -m pip install -e ".[dev]"
```

### 2) Start the mock Authority (terminal A)

PowerShell:

```powershell
$env:CUSTOMS_SCHEMA_PATH = "$pwd\schema\manifest.schema.json"
$env:CUSTOMS_SECRETS_PATH = "$pwd\mock-customs\secrets.json"
py -3.11 mock-customs\server.py
```

bash:

```bash
export CUSTOMS_SCHEMA_PATH="$PWD/schema/manifest.schema.json"
export CUSTOMS_SECRETS_PATH="$PWD/mock-customs/secrets.json"
python3 mock-customs/server.py
```

### 3) Run all scenarios and write `results.json` (terminal B)

PowerShell:

```powershell
$env:CRESCENT_HARBOR_ROOT = (Get-Location).Path
py -3.11 -m crescent_filer.pipeline.batch_runner
```

Output: `results.json` at the repo root (Format B).

## What I Built

I built a deterministic filing pipeline for one document type (Cargo Arrival Manifest), from scenario input to final authority disposition:

- `builder` constructs a complete manifest from scenario input plus filer identity and signer metadata.
- `validation` applies JSON Schema (`draft 2020-12`) with normalized, actionable error codes.
- `rules` enforces cross-field business rules from `rules/rules.json` and returns structured rejects/warnings.
- `client` signs every request with HMAC-SHA256 per spec and submits/polls the mock authority.
- `polling` enforces protocol behavior (minimum poll interval, terminal-state timeout).
- `pipeline` orchestrates single-file and batch execution.
- `batch_runner` iterates every `scenarios/*.json`, classifies outcomes dynamically, and writes `results.json` in Format B.

**Schema, business rules, and transport are treated as separate gates to give clean ownership and incident debugging**.

## What I Cut (and Why)

1. **Persistent amendment state store**
   - I did not add DB-backed state for `amendmentSequence` lineage.
   - Why: the case study does not require full amendment history persistence; local context is enough to validate pipeline behavior.

2. **Rich observability stack**
   - No OpenTelemetry traces, log shipping, or metrics backend.
   - Why: until throughput and SLO targets are explicit, high-fidelity telemetry is unnecessary optimization.

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

Ideally, copying and running multiple pipelines can become cumbersome. It would make better sense to standardize contracts to plug and play easier.

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
  
