# Native adapter checkpoint reconciliation — 2026-09-10

Status: **isolated numeric-venue checkpoint reconstruction, native reconciliation
and three-process replay acceptance implemented**. No real account, external HTTP
or WebSocket was accessed. This follows the
[read-only transport increment](portfolio-readonly-transport-2026-09-10.md).
Existing execution runners remain unchanged; this does not resume trading.

## Recovery entrypoint

`portfolio_adapter_checkpoint.reconcile_adapter_checkpoint` joins the existing
stream fence, native-event serializer, actual Binance report converters and exact
account comparator in one isolated operation:

1. Bind the supplied original bytes to the caller's expected SHA256 and verify
   native/state/generation digests. Match the independent account anchor, require
   a later recovery cursor, a persisted boolean risk latch and known intent map.
   An unresolved persisted halt still blocks recovery.
2. Require a collected source fence for the same UID and validate it against the
   current journal. Account evidence must cover the checkpoint cursor through its
   declared end, retain the original anchor and have fresh matching source receipts.
3. Reconstruct native account, orders and positions into a new disposable cache.
   The explicit `binance_numeric_offline_v1` snapshot mode allows numeric Binance
   venue IDs and native calculated CASH accounting. Events later than the saved
   cursor are rejected. This mode cannot enter default UUID simulation restoration.
4. Register only the fixture's native HEDGING management type. The evidence-only
   execution engine has a TestClock and rejects execution clients, commands and
   inferred fills. Native Binance reports resolve known orders from complete
   original trade history; Nautilus alone updates fills, positions and balances.
5. Require the existing exact account comparator to agree on totals, free/locked
   funds, orders, trades, fees and original sleeve links. Unknown prepared orders,
   incomplete history, changed historical fees, funded foreign assets and ambiguous
   ownership still fail. No remote balance is assigned to repair a discrepancy.
6. Preserve the entire opaque strategy-state value and its canonical SHA256,
   serialize updated native events, and recheck the stream fence before returning.
   Return input/output digests, logical account-evidence hashes and original
   collector wire hashes/source fence for review. Any failure discards the isolated
   cache; original checkpoint bytes are never modified by reconciliation.

The opaque state is **preserved, not policy-qualified or activated**. The new
acceptance uses `portfolio.adapter_checkpoint_fixture.v1`, not a live strategy
checkpoint schema. Signal decisions, watermarks, baselines and the preset risk
latch survive unchanged; this does not test resumed signal admission or validate
the strategy's policy fingerprint. Output always records:

```json
{
  "runtime_ready": false,
  "real_account_verified": false,
  "downtime_risk_review_required": true
}
```

Current code calls native reconciliation synchronously on the stream owner's
loop and rechecks observed state. It does not claim an exchange-atomic boundary,
globally lossless delivery or complete intraday risk history. Preserving a prior
risk latch cannot discover a loss-limit breach that happened during downtime.

## Checkpoint persistence boundary

`portfolio_recovery.capture_native` and `reconstruct_native` retain UUID simulation
defaults. Numeric snapshots require explicit mode selection and an explicit anchor
matching the initial native account event. Calculated account replay is enabled
only for the isolated numeric CASH mode. No existing simulation snapshot is
silently migrated, and no upstream serializer/account code is changed.

`write_new_checkpoint` verifies the combined checkpoint, writes/fsyncs a private
temporary file, publishes it with an exclusive hard link, then fsyncs the parent
directory. Existing files are never replaced. Temporary files are removed on
failure. A directory-fsync failure after publication may leave a complete but
unacknowledged output: inspect/verify it before another attempt; never overwrite
the original to hide that uncertainty. Digest validation detects accidental
corruption; it is not an independent signature or historical-provenance proof.
Keep checkpoints and account receipts in ignored private local data.

## Three-process acceptance

```bash
.venv/bin/python -m apps.strategies_nautilus.runners.portfolio_adapter_checkpoint_acceptance
```

The command uses temporary files and three actual Python processes:

- Producer builds a native v18 partial BUY of 0.000333 BTC with 0.00000050 BTC
  commission, followed by a pending cancel, plus an uncertain submitted v16 BUY.
  It persists both native events and a fixture intent/risk journal, then terminates
  with `os._exit(23)` without stop hooks. The risk latch is preset in this fixture;
  triggering the latch through market losses remains covered by prior acceptance.
- Consumer reconstructs the saved objects and applies independent fixed synthetic
  Binance bodies. V16 becomes FILLED at 0.001 BTC gross and 0.00099850 BTC net.
  A second v18 fill of 0.000333 BTC arrives during downtime; its order becomes
  CANCELED at 0.000666 BTC gross and 0.00066500 BTC net. Final account state is
  **333.4 USDT / 0.00166350 BTC**, with zero locked balance and original position IDs.
- Replay process reloads the new numeric snapshot and reconciles the same original
  fills against a fresh synthetic observation. Status, inventory, cash, fees and
  state digest stay unchanged. Original bytes remain intact and all PIDs differ.

The response bodies are fixed fixture data, independent of the consumer's resulting
cache; they are not authenticated Binance observations. Subscription acknowledgement
is supplied by the fixture journal. The prior native socket loopback tests remain
separate; this acceptance does not combine a real exchange connection and a crash.
It proves native reconstruction and exact economic replay, not full live-process
restart, market-data queue recovery or trading readiness.

## Verification and next step

**32 new tests passed**; combined adapter/checkpoint/prior-recovery regression:
102 passed. Tests cover exact balance and lock drift, missing/duplicate trades,
historical fees, foreign orders, anchor/hash/version/mode mismatches, future native
events, expired observations, stale/reconnected fences, persisted halts and risk
types, lineage conflicts, mid-reconciliation disconnects, exclusive publication,
file-fsync failure and the three-process scenario.

Full offline suite: **2,118 passed**, 12 Postgres tests deselected without a
dedicated integration DSN. Ruff, registry and whitespace checks pass.

```bash
.venv/bin/pytest -q tests/strategies_nautilus/test_portfolio_adapter_checkpoint.py tests/strategies_nautilus/test_portfolio_recovery.py tests/strategies_nautilus/test_portfolio_adapter_recovery.py
.venv/bin/pytest -q -m 'not network and not postgres'
.venv/bin/ruff check apps tests notebooks
.venv/bin/python -m apps.ops.research_family_registry --check
git diff --check
```

Next external acceptance still needs the explicit environment, existing credential
variable names/config path, expected UID and independent account baseline. Qualify
actual permissions/REST/stream evidence and downtime archive coverage, then test
that source against a dedicated numeric checkpoint. Before execution bootstrap,
validate real strategy state/policy fingerprints, complete downtime risk history
and resolve planning versus runtime risk limits. Existing schedules, SourcePolicy,
SignalEvent v1, upstream source and the 5% runtime loss rule are unchanged.
