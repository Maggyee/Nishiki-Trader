# ADR-017 native session ledger and process recovery — 2026-09-11

The bounded engineering session now has an **offline durable intent ledger,
full-account native reconstruction and crash/replay acceptance**. This follows
the [successful non-matching TRADE validation](portfolio-testnet-engineering-session-2026-09-11.md).
The current increment uses synthetic data and native Nautilus engines only;
there were no new network requests, credentials loaded, matching orders or cancellations.

## Durable session boundary

`portfolio_session_ledger.SessionLedger` fixes the ADR-017 10 test-USDT allocation,
one 0.0001 BTC BUY, one possible owned cleanup SELL and 180-second new-order bound.
It preserves the full initial native account, including pre-existing BTC and all
unrelated assets. The native baseline here is a prospective numerical anchor for
serialization/conservation, **not** ADR-015's independently qualified UTC baseline.

A prepared intent stores the exact native OrderInitialized event, deterministic
session/client/position IDs, SignalEvent identity, quantity, price and deadline
before a future strategy may submit. A prepared BUY consumes the one-BUY allowance
and reserves its entire limit notional even when no order has reached the native
cache. Rejection/cancellation, sale proceeds, reload, a new clock day or a price
rebound cannot restore that allowance. Known cancellation intent is also persisted
once before a future cancellation call; it requires an acknowledged order and
the two-second delay.

Only the explicit `rule_testnet_engineering_fixture / testnet-engineering-lifecycle-v1`
identity is accepted by this offline consumer. It revalidates SignalEvent v1,
venue, symbol, freshness, chronology, confidence and duplicate IDs. Signals contain
no sizes or order instructions. Native initialized orders must match the deterministic
IDs/tags and effective zero-fee filters. This consumer is **not** installed in a
trading strategy or SignalStore; no research SourcePolicy is promoted.

The ledger derives ownership, quote spent, fees, proceeds and reservations from
complete native OrderFilled events. It does not apply fills or assign exchange
balances. Complete native order/position lineage and full-account conservation
are checked before checkpoints. An unexpected supported nonzero fee remains
accounted exactly and persists a halt in the nominally zero-fee session. Unsupported
or inconsistent events fail closed; they are not repaired with remote balances.

Cleanup quantity must be the whole effective order steps of owned net BTC.
Pre-existing BTC cannot be sold. A below-minimum cleanup is refused, with exact
residual ownership retained. Expiry prevents new orders; a known cancellation
may still be recorded after expiry to reduce outstanding risk, without replenishing
either submission allowance. A cancellation acknowledgement is never assumed.

Each checkpoint contains native serialized events and state digests. The writer
holds a nonblocking private file lock, fsyncs a private temporary file, publishes
it atomically and fsyncs the parent directory. Creation is exclusive; updates
verify that the previously acknowledged bytes have not changed. A failed file or
directory fsync poisons the in-process writer and returns no successful preparation.
A directory-fsync failure may leave the new consumed intent visible on disk;
it is never overwritten with the prior free budget. Reload requires an explicit
selected hash. The lock is per selected checkpoint, not a global exchange lease;
the future runner must use one fixed account/session location and prohibit new-ID
restarts of the same authorized experiment.

## Native account and report recovery

`portfolio_session_recovery` restores the original native account/order/position
events in a disposable cache, registers explicit stored precision for every
account currency and uses the existing native Binance report converters and
`EvidenceOnlyExecutionEngine`. Native currency registration is process-global;
the acceptance runner performs this in separate short-lived processes. No client,
live clock, trading command or inferred fill is allowed by that engine.

The recovery observation must bind selected bytes, source, the original history
start, later receipt time, all known order reports, complete original trades and
account-wide open orders. All asset totals and free/locked quantities must agree
with native state and native fill conservation. Missing reports/trades, new foreign
orders, account/source changes, unrelated balance/lock drift and altered historical
fills fail without changing the original checkpoint. Receipt/hash agreement here
does not authenticate the synthetic source or establish a lossless stream cut.

The default report reconciler remains strict. A separate engineering opt-in can
adopt an exact persisted native initialization **only when authoritative fixture
reports show a terminal order**. Nautilus creates its own Accepted/Fill events;
no Submitted or Fill event is invented by project code. Nautilus's `Order.account_id`
is populated by Submitted, so terminal replays additionally verify the actual
account IDs on preserved Accepted/Fill events for this explicit fixture only.

An active NEW/PARTIALLY_FILLED order with no persisted native Submitted event is
explicitly **blocked**. It cannot be considered absent, have its budget released,
or be submitted again. An active partially filled order **with** its original
Submitted event does recover with exact remaining locks. The future submission
bridge must persist Submitted before any adapter send; that bridge is not yet wired.

### Partial-fill lock compatibility

The installed native `AccountsManager` calculates cash locks using original
`order.quantity`, even after partial fills. For a 0.0001 BTC BUY at 70,000,
after filling 0.00004 BTC, it retained 7 USDT locked instead of the 4.2 USDT
remaining reservation. Merely reinitializing the portfolio did not fix this.

The project-owned `SessionCashAccount` resolves the sole attributable native open
order and delegates locking of its **native leaves quantity** to CashAccount.
It neither changes total funds nor copies exchange balances. Missing/ambiguous
orders, a foreign strategy/account and inverse instruments are refused. This
extension is used only in the isolated offline session fixture/recovery, with no
global AccountFactory registration or upstream modification. It is not a change
to production account handling.

## Acceptance results

The executable acceptance uses **synthetic 502-asset accounts**, including 2 BTC
already present before the session. These are not the user's actual asset values.
Two scenarios each use three distinct processes: producer persists then terminates
with `os._exit(23)`; consumer reconciles fixed independent fixture reports; a third
process replays the result. Original intents, cancellation intent, ownership and
the consumed BUY allowance survive. No stop hook or graceful cleanup is used to
make the producer checkpoint recoverable.

| Scenario | Recovered session ownership | Session BUY debit | Full assets retained |
|---|---:|---:|---:|
| Crash after durable preparation; terminal fill report | 0.0001 BTC | 7 USDT | 502 |
| Partial 0.00004 BTC, pending cancel, another 0.00004 BTC during downtime, then canceled | 0.00008 BTC | 5.6 USDT | 502 |

Additional native checks cover active partial-order recovery, full cleanup returning
exactly to the pre-existing 2 BTC, and a partial 0.000075 BTC followed by a whole-step
0.00007 BTC cleanup that retains **0.000005 BTC** as owned dust. A 0.000035 BTC
partial fill cannot be sold below the 5-USDT minimum at the fixture price; ownership
remains recorded. Positive fee settlement is preserved and halts further orders.

**47 new tests** cover these native scenarios, fixture authorization, order budget
and effective limits, timeout/clock rollback, exclusive creation/writer locks,
checkpoint hash/privacy checks, file/directory-fsync failure, external replacement,
missing/conflicting recovery evidence and default-adapter isolation.
Full offline regression: **2,433 passed**, 12 PostgreSQL integration tests deselected
because no dedicated integration DSN was supplied. Full application/test/notebook
Ruff, the family registry and whitespace checks pass.

```bash
.venv/bin/python -m apps.strategies_nautilus.runners.portfolio_session_acceptance
.venv/bin/pytest -q tests/strategies_nautilus/test_portfolio_session_ledger.py
.venv/bin/pytest -q -m 'not network and not postgres'
.venv/bin/ruff check apps tests notebooks
.venv/bin/python -m apps.ops.research_family_registry --check
git diff --check
```

## Next integration

Wire the ledger into a dedicated Nautilus Strategy -> RiskEngine -> ExecutionEngine
testnet session, including synchronous Submitted/PendingCancel persistence before
the adapter's outbound request, fixed session ownership across restarts, actual
signed report collection and native stream callbacks. Exercise that bridge through
transport failure before running the bounded matching trial. No legacy runner may
stand in for this missing integration.

The existing key and prior zero-fee TRADE validation are already recorded. They
need fresh fee/filter checks at eventual session start, not another permissions
questionnaire. Actual business-event delivery and adapter process recovery remain
unqualified; full-account UTC/valuation qualification remains separate. No matching
test, production path, SourcePolicy, schedule or 14-day continuity gate was enabled.

Changed files are the session ledger, session CASH extension, session recovery and
acceptance runner, the narrowly scoped native report opt-in and new tests; ADR-017's
implementation addendum, this report, application README, reading list and project
status. No upstream source was touched.
