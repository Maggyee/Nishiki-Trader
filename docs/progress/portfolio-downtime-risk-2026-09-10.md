# Read-only downtime risk review — 2026-09-10

Status: **checkpoint-bound risk observation review and local CLI implemented**.
No credentials, network, market history downloads, orders or runtime configuration
changes. This follows the
[native adapter checkpoint increment](portfolio-adapter-checkpoint-2026-09-10.md).
It detects observed risk breaches without treating a recovered ending balance as
proof that the account stayed within limits during downtime.

## Inputs and ownership

`portfolio_downtime_risk.review_downtime_risk` takes selected original/reconciled
numeric-venue checkpoints, their expected SHA256s, an explicit source binding and
a serialized local observation bundle. Each observation contains a native
serialized `AccountState` and native `QuoteTick`, with its evaluation timestamp.
Nautilus deserializes these objects; the reviewer does not replay fabricated fills,
maintain an execution ledger or assign balances to a running account.

The reviewer requires:

- Checkpoint integrity, matching account anchor, preserved strategy state and a
  strictly later recovered native cursor. Both snapshots use the explicit isolated
  numeric mode; the same venue UID must match the selected source binding.
- A positive persisted day-open equity, consistent peak and boolean risk latch.
  The interval must remain in the same UTC day as the saved day-open baseline.
  Cross-day review is refused until a separately qualified new baseline exists;
  the first observation after midnight is never substituted automatically.
- Exact selected checkpoint digests and source fields in the history bundle.
  Between two and 10,000 ordered observations are accepted. Both exact checkpoint
  times must be present, with matching native total/free/locked endpoint balances.
- Native CASH snapshots for the same account, BTC/USDT balances only, positive
  ordered bid/ask prices and quantities for BTCUSDT.BINANCE. Duplicate assets,
  inconsistent balances, future/stale or regressing observations and conflicting
  reuse of an account event or quote identity are refused.

Account snapshots may be at most 60 seconds old. Quote age and reported sample-gap
threshold default to one second; the Python API permits an explicit positive gap
bound up to 60 seconds. These are audit freshness limits, not evidence of complete
exchange delivery. Reusing an unchanged account snapshot is permitted within its
age bound and does not prove no account event was missed.

## Equity and stop observations

For each native account/quote observation:

```text
equity = total USDT + total BTC × observed bid
daily loss = persisted day-open equity − equity
observed peak = max(persisted peak, all observed equity so far)
drawdown = observed peak − equity
```

The reviewer retains the first inclusive breach of each relevant bound:

- Day-open equity × **5%**, following ADR-001 and the existing baseline strategy's
  `on_account_update` semantics. Boundary tests also call that existing method.
- The unchanged offline planning daily loss, currently **50 USDT**.
- The unchanged offline planning peak drawdown loss, currently **250 USDT**.

These remain separate observations. At 500 USDT day-open equity, the 5% threshold
is **25 USDT**, so the 50 USDT planning amount cannot stand in for the runtime rule.
The reviewer reports this mismatch without changing either configuration. The
testnet telemetry path's starting-balance/daily-PnL mapping and real strategy policy
fingerprints still need qualification; this audit does not certify their equivalence.

A later rebound never erases a first breach. A prior risk latch or persisted halt
also requires incident review, even if every supplied sample looks acceptable.
No checkpoint, latch, decision, watermark or baseline is modified.

Native snapshots here establish recorded account valuations, not authenticated
trading PnL. Cash transfers, omitted account events and unqualified day-open sources
remain unresolved; the reviewer does not silently classify a withdrawal as a
trading loss or a deposit as profit. An observed equity decline requires review.

## Output boundary

The report includes input/history digests, source binding, observation gaps,
minimum/ending equity, observed peak, first breaches, both daily thresholds and
whether an observed or persisted stop requires incident review. It always retains:

```json
{
  "runtime_ready": false,
  "real_account_verified": false,
  "downtime_history_complete": false,
  "downtime_risk_review_required": true
}
```

Sparse observations can establish a conditional observed breach, never prove its
absence between samples. Even a dense sequence with no declared gaps remains
unqualified for lossless account/price coverage. No new caller or execution runner
consumes this report as a restart permit.

## Local command and schema

```bash
.venv/bin/python -m apps.ops.portfolio_downtime_risk_check \
  data/original.json data/reconciled.json data/downtime-observations.json \
  --source-binding data/account-source-binding.json \
  --before-sha256 <selected-original-sha256> \
  --after-sha256 <selected-reconciled-sha256>
```

The history object has exactly `schema_version="portfolio.downtime_risk.v1"`,
`input_sha256`, `output_sha256`, `source` and `observations`. The source object uses
the existing `SourceBinding` fields: `endpoint`, `account_uid`, `key_sha256`; it
contains no key/secret value. Each observation has exactly `ts_ns`, `account_event`
and `quote`. The latter two are native serializer JSON strings, as emitted by the
existing `portfolio_recovery.encode`. Duplicate JSON keys and unsupported fields,
including self-declared completeness flags, are rejected.

All input files are explicitly selected private local evidence and remain unchanged.
Exit 2 means invalid evidence or an observed/persisted stop. Exit 0 means the supplied
observations parsed without a detected breach; **it never means restart ready**.

## Acceptance and remaining work

The synthetic recovery fixture starts this scenario with its risk latch explicitly
false. Recorded equity moves from **499.95** to **473.35**, then recovers to
**499.75 USDT**. The reviewer retains a **26.65 USDT** daily loss, exceeding 25 USDT
while staying below the 50 USDT planning bound. Endpoint-only review would miss it.
These are synthetic account/price observations, not market performance evidence.

**33 tests pass**: rebound detection, exact inclusive 5% boundaries matched against
the existing baseline strategy, planning-limit separation, peak preservation,
prior latch preservation, sparse/dense history limits, source/checkpoint identity,
invalid balances/order/time/quotes, conflicting replay, missing day-open and UTC
rollover, and CLI exit codes plus input immutability.

Full offline suite: **2,151 passed**, 12 Postgres tests deselected without a
dedicated integration DSN. CLI help, Ruff, registry and whitespace checks pass.

Actual account credentials/environment, UID and independent baseline remain absent.
Next: qualify real source/permission evidence, account and price archive coverage,
cash flows, UTC day-open history and actual strategy policy state before any
execution bootstrap. No upstream source, SignalEvent v1, SourcePolicy, schedules,
allocations, promotion, 5% rule or existing runner changed.
