# Owned cleanup admission and fee recovery acceptance — 2026-09-12

The bounded session runner no longer applies the **new BUY** prerequisites to
its owned cleanup SELL. Previously `fresh_terms` always called `validation_price`:
an account starting with exactly 10 free test USDT could buy about 7 USDT of BTC,
then incorrectly fail cleanup because its remaining quote cash was below 10 USDT.
An unrelated BUY price-band failure could also reject a valid SELL reduction.

## Fix and unchanged admission boundaries

`cleanup_price` shares the original complete-account stability, account trading
flag, empty account-wide orders and exact-zero commission checks. It parses fresh
effective rules and validates the current BTCUSDT best bid, positive bid quantity,
price tick/min/max and **SELL** price bands. Capability hashes, parameter sequence,
selected source and five-second rule/quote freshness remain required. The initial
BUY and non-matching validation retain their existing 10-USDT and BUY filter gates.

This helper returns a quote, not an order or execution permission. In the original
matching process, signed native account reconciliation, SignalEvent v1, Strategy,
RiskEngine, durable intent/dispatch and the guarded native adapter still control
the sole owned cleanup. Quantity remains the whole effective steps of actual net
session fills. Below-minimum quantity/notional retains the entire holding. The
original deadline, unused SELL allowance, halt state and all effective quantity,
notional and account constraints still apply. No proceeds replenish the BUY budget.

Cancellation recovery stays cancellation-only. This fix neither removes its
persistent marker nor adds recovered SELL admission. No checkpoint schema,
session-contract hash, scope, original IDs or policy limit changes.

## Synthetic acceptance

The whole CLI fixture now stubs capability collection rather than `fresh_terms`,
so the actual BUY/SELL capability gates run alongside LiveClock, native queued
Strategy/RiskEngine/adapter, signed fixture requests and full native reconciliation.
Fixed independent venue rows/trades and account arithmetic provide the comparison;
they are not derived from the native ledger's calculated balances.

Eleven matching scenarios plus the existing cancellation-recovery CLI case cover:

- Unfilled BUY/cancel and a full BUY/SELL round trip, including exactly 10 starting USDT.
- Partial BUY/cancel followed by the owned whole-step SELL.
- A 0.000085 BTC BUY fill, 0.000080 BTC cleanup and exact 0.000005 BTC residual.
- 0.000040 BTC below minimum notional and 0.000005 BTC below one effective step:
  retain all owned BTC without preparing or consuming a SELL.
- Partial cleanup SELL/cancel: retain the unsold inventory and consumed SELL allowance.
- Unexpected one-satoshi BTC BUY fee, one-quantum USDT BUY fee and USDT SELL fee:
  settle exact native balances, then persist the fee halt and refuse further trading.
- Separate GET-only CLI restoration reproduces every terminal native view and
  preserves the original checkpoint bytes and request count. Terminal
  `--recover-cancel` additionally preserves residuals/fee halts without any new send.
- A later `--execute` remains rejected in every consumed fixture scope.

Capability regressions also reject account drift, foreign open orders, unavailable
trading, standard/special/tax fees, stale inputs, wrong symbols, empty bids, invalid
price ticks and SELL price bands. A valid SELL quote remains available when the
same capture cannot authorize another BUY.

## Actual evidence and next step

All new fill, fee and cleanup evidence is synthetic. No real credential was loaded and
no actual exchange request was made this increment. The completed real session
still has zero fills/owned BTC, a consumed BUY allowance and an expired new-order
deadline. Its original private checkpoint is not modified. It cannot be restarted
or replaced merely to obtain fill evidence; the collector's history bound is not relaxed.

Next qualify interrupted **cleanup SELL** outcomes through the existing
cancellation-only recovery: durable original SELL receipts, partial/late fills,
uncertain cancellation, exact remaining ownership and no retry. Any future recovered
new SELL would require a separately defined admission path preserving the original
deadline/allowance, zero fees and native reconciliation; it is not implemented here.
Actual active recovery, fills, fee settlement and cleanup remain unverified.
Full-account portfolio qualification, strict 0/14 continuity and real-money gates
remain unchanged.

## Files and verification

- `apps/strategies_nautilus/portfolio_testnet_session.py`: separate cleanup quote gate.
- `apps/ops/portfolio_session_run.py`: select it only for original-process cleanup.
- `tests/ops/test_portfolio_session_run.py` and `test_portfolio_testnet_capabilities.py`:
  whole CLI/native/recovery scenarios and capability refusals.
- ADR-017, agent reading list, project status and this report: current boundaries/results.

No upstream source, production runner, dependency, service or schedule changed.
This changes the bounded **testnet** cleanup path; no real-money path is enabled.

Reproduce without credentials or exchange access:

```bash
.venv/bin/pytest -q tests/ops/test_portfolio_session_run.py tests/ops/test_portfolio_testnet_capabilities.py
.venv/bin/pytest -q -m 'not network and not postgres'
.venv/bin/python -m apps.ops.research_family_registry --check
```

The fixed actual checkpoint still hashes to
`08995a8289a99b88e02f87c9c07387302c8f74ed006e5a2a33ddf1932d0b1a5f`,
identical to the prior completed real-session evidence.

Verification: **23 additional tests**; the two focused files contain **71 passing
tests**. Final full offline regression: **2,586 passed, 12 deselected** in
145.95 seconds. The 12 Postgres integration tests require an unavailable dedicated
DSN. Ruff, research-family registry and whitespace checks pass.
