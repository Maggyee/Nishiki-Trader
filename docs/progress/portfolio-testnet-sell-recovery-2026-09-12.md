# Interrupted cleanup SELL recovery acceptance — 2026-09-12

The existing cancellation-only runtime now has explicit native acceptance for a
**completed BUY plus an interrupted owned cleanup SELL**. The original recovery
implementation passes these scenarios without an application-code change. This
increment adds tests and evidence, not a new order permission or recovery mode.

## Fixture and native lifecycle

A LiveClock/native fixture starts with 2 BTC, 100 test USDT and 5 ETH. Its sole
0.0001 BTC BUY fills at 70,000 USDT. Before the original-process cleanup, a fresh
synthetic effective quantity step changes to 0.00003 BTC. Native Strategy therefore
prepares the allowed 0.00009 BTC SELL, retaining 0.00001 BTC as session-owned dust.
Both original orders traverse the native Strategy, RiskEngine, execution queue and
signed fixture HTTP boundary with durable Submitted/dispatch receipts.

The process is interrupted after the SELL's acknowledgement or partial fill, or
with its acknowledgement/fill missing locally. The recovery collector queries
**both** original client order IDs and both venue IDs' trades. Independent fixture
account arithmetic and venue rows are checked against native reconstruction; no
balance, fill, timestamp or order allowance is patched from an expectation.

At 0.00003 BTC sold, native owned BTC is 0.00007, while 0.00006 remains reserved
for the outstanding SELL. Original 2 BTC and retained 0.00001 BTC are free. Recovery
preserves that distinction; reservation does not transfer ownership to the venue.

## Acceptance coverage

- Restore an acknowledged or partially filled SELL, including a missing native
  acknowledgement or missing local SELL fill, alongside the completed BUY history.
- Cancel only the original SELL ID/venue ID. Native PendingCancel and its sole
  dispatch receipt are durable before the synthetic DELETE boundary.
- Replay exact historical BUY and SELL callbacks without double settlement.
  Another 0.00003 BTC SELL fill during cancellation leaves 0.00004 BTC owned and
  4.2 USDT total sale proceeds; acknowledgement releases the remaining base lock.
- A full 0.00009 BTC SELL fill before cancellation causes no DELETE and retains
  exactly 0.00001 BTC dust. Recovery cannot sell or sweep it again.
- An unexpected 0.00000001 USDT fee on a late SELL fill settles exactly to
  4.19999999 USDT sale proceeds, preserves the fee halt, and permits no new cleanup.
- Missing BUY/SELL trades, incorrect base locks, unrelated ETH drift, missing
  original SELL submit dispatch and an already prepared SELL cancellation all
  block recovery publication without outbound cancellation.
- An uncertain DELETE retains PendingCancel and all three consumed dispatches.
  Subsequent active-order reconciliation fails closed; no second DELETE is sent.
  This is not proof that the venue has canceled the order.
- Actual atomic-writer fsync failure at PendingCancel or dispatch blocks the
  adapter send. The failed writer stays poisoned.
- The full `--recover-cancel` CLI handles the same two-order SELL scenario, performs
  final signed-fixture account reconciliation and then returns terminal no-action
  on a second invocation, preserving the original checkpoint bytes.

New-order signal/ledger paths remain forbidden after restoration. Original BUY and
SELL allowances, deadline, intents, signal history and transport halt history are
preserved. No new BUY, replacement SELL, cancellation retry or budget recycling is
introduced. Fresh source/receipt checks and the original recovery profile remain.

## Abrupt exit and independent processes

A separate producer process exits with code 27 **inside the recovered SELL DELETE
transport**, after durable cancellation dispatch. Independent venue evidence records
a late SELL fill and a terminal CANCELED order, neither delivered to the old runtime.
Two new processes then collect and reconcile the same fixture evidence. Both return
terminal no-action with identical views: 0.00004 owned BTC, 2.00004 total BTC, 97.2
USDT, 5 ETH, three exact fills and three original dispatch receipts. They preserve
all allowances/halts and leave the fixed fixture checkpoint bytes unchanged.

These are synthetic signed-I/O tests using a public test key, three fixture assets
and real native engines/processes. They do not verify actual exchange active-order
recovery, fills or fees. No real credential or exchange endpoint is accessed.
The actual completed 502-asset testnet scope remains consumed and untouched.
Its checkpoint hash remains
`08995a8289a99b88e02f87c9c07387302c8f74ed006e5a2a33ddf1932d0b1a5f`.

## Files, verification and next step

- `tests/strategies_nautilus/test_portfolio_session_sell_recovery.py`: native SELL
  restoration, admission refusals, late fills/fees, durability, timeout and subprocess fixtures.
- `tests/ops/test_portfolio_session_run.py`: parameterize the existing whole recovery
  CLI test for original BUY and cleanup SELL.
- Project status, agent reading list, ADR-017 evidence reference and this report.

No application or upstream source, production/live order path, dependency, service,
schedule, source policy or actual session state changed.

```bash
.venv/bin/pytest -q tests/strategies_nautilus/test_portfolio_session_sell_recovery.py tests/ops/test_portfolio_session_run.py
.venv/bin/pytest -q -m 'not network and not postgres'
```

Verification: **17 additional tests** and **29 passing tests** across the two
focused files. Final full offline regression: **2,603 passed, 12 deselected** in
171.65 seconds. The 12 Postgres integration tests require an unavailable dedicated
DSN. Ruff, registry and whitespace checks pass.

Next make unresolved-order operator handling explicit: distinguish a confirmed
terminal state from an uncertain/blocked cancellation; surface consumed attempts
and exact retained ownership without suggesting a retry or scope reset. Actual
fill/cleanup acceptance remains absent; a synthetic pass cannot qualify those
claims, portfolio equity, 14-day continuity or real-money admission.
