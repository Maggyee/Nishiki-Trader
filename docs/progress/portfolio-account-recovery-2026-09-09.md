# Account reconciliation and native process recovery — 2026-09-09

Status: **signed read-only collector interface, exact account comparison and
synthetic cross-process recovery implemented**. No real account was accessed.
This follows the operator's request for authoritative account reconciliation and
full process recovery. The new acceptance actually terminates one process and
starts another; the previous warm strategy restart was insufficient evidence.
Real exchange bootstrap remains blocked on account qualification and a synchronized
user-stream boundary. `runtime_ready=false` throughout this increment.

## Read-only account source

`portfolio_account_collector.BinanceReadOnlyAccountCollector` accepts an explicitly
configured native `BinanceHttpClient` and a clock. It neither discovers credentials
nor loads secrets. All requests use the native client's signed **GET** interface:

1. `/sapi/v1/account/apiRestrictions`: require reading permission and record the
   actual trading permission. Read-only keys are supported; the collector does
   not require granting a key order-submission permission.
2. `/api/v3/account`: bind the returned UID to an explicit `AccountAnchor`.
3. `/api/v3/openOrders`: account-wide, without a symbol filter.
4. `/api/v3/allOrders` and `/api/v3/myTrades`: include terminal orders and fees,
   paginate full 1,000-row pages using advancing order/trade cursors.
5. Read account-wide open orders and account again; changed responses require
   recollection, not a fabricated consistent snapshot.

Only the explicit official production/testnet hosts are accepted. The collector
does not automatically select an environment or fall back between them. Endpoint
and permission availability, including SAPI support, have not been verified on an
actual account; unsupported responses fail closed. Transport errors do not echo
private signed URLs. Every raw wire response has a retained SHA256; aggregated
history and final response bodies are carried in the returned evidence.

Initial history is limited to a **24-hour anchor window** and at most 32 pages per
history endpoint. A full final page, duplicate/retrograde cursor or longer history
does not count as complete. A longer-running account needs a separately qualified
continuous archive; exchange retention is not assumed. No collector is scheduled
or wired into existing paper/testnet/live runners.

Usage from an explicitly authorized read-only integration is:

```python
source = BinanceReadOnlyAccountCollector(native_http_client, clock_ns=time.time_ns)
captured = await source.collect(anchor)
# Pass captured.evidence to reconcile_account with the native account state.
# captured.atomic_revision_verified is always False.
```

The two REST reads detect observed changes, but do not prove that nothing changed
and changed back between requests. They also cannot prove lossless user-stream
coverage. Thus even signed, matching REST evidence is **not an atomic live admission
permit**. A connected stream epoch/barrier, downtime reconciliation, authoritative
archive and effective venue references remain necessary before runtime integration.

## Exact comparison and attribution

`portfolio_account.reconcile_account` consumes independently supplied account,
allOrders, myTrades and account-wide openOrders captures, plus native objects and
the persisted intent map. Captured JSON alone does not authenticate its origin.
The signed collector is the source interface; tests use explicitly synthetic
responses. The initial baseline must be supplied, never inferred from today's
account value: expected venue UID, native account ID, start time, starting USDT
and zero BTC for this dedicated long/flat contract.

Checks include:

- Independent timestamps and account/request identities for every response,
  complete declared history coverage and SPOT account trading permissions.
- BTC/USDT total, free and locked balances exactly; duplicate assets and other
  funded assets are refused. A different free/locked split cannot pass simply
  because totals agree.
- Complete known native/venue order sets, including terminal orders; client and
  venue IDs, side, LIMIT/GTC, original/filled quantities, price, cumulative quote
  amount and status. Unknown account-wide orders block recovery.
- Every trade ID, order link, quantity, price, quote amount, commission amount,
  currency and direction. Missing or duplicate fills and BNB fees are refused.
- Native orders must retain the fixed fixture strategy, intent, signal tags and
  sleeve position links. Native position quantities must equal net fill evidence;
  native cash/base must equal the explicit baseline plus those fills and fees.
  This is a read-only conservation check, not a second execution ledger.
- Optional `VenueRulesEvidence` must attach to the same account/instrument and be
  fresh; its response hashes and oldest timestamp join the reconciliation result.
  This binding does not replace the existing full preflight on actual proposals.

The comparator is intentionally exact and narrowly scoped to the new portfolio
fixture strategy. Real venue rounding/payment conventions and runtime strategy
identity must be qualified before another consumer uses it. Failure returns a
reason and does not alter accounts, positions, orders, risk state or permissions.

## Native persistence and fresh-process restoration

The explicit `persist_native=True` simulation mode stores native serialized
account, order and position fill events alongside the existing strategy checkpoint.
The snapshot includes instrument configuration, Nautilus version, simulation
account anchor and native venue-ID mode. State and native payloads have individual
hashes plus one combined generation hash. Existing fsync, atomic replace and
single-writer locking apply to the entire generation.

Restoration uses **Nautilus MsgSpecSerializer, AccountFactory, OrderUnpacker and
Position replay**. Native code recalculates base-fee position adjustments; the
project does not invent or apply replacement fills. Native cache indexes are
rebuilt before engine startup. Nautilus's backtest startup restores known pending
orders to its matching engine; no SubmitOrder is reissued for those orders.

The new mode enables Nautilus's native random UUID venue order IDs. A fresh
process otherwise restarts the simulated venue's numeric counter and could reuse
an old venue order ID. This choice is included in recovery metadata/fingerprint;
old default fixtures keep their existing IDs and behavior. Native trade IDs remain
timestamp-based, and recovery requires advancing beyond the saved market cursor.

`recover_simulation` first verifies the complete generation, exact account anchor,
native version/configuration, persisted halt and independent account evidence.
It then constructs a fresh isolated engine. At actual startup, under the writer
lock, it checks that the loaded checkpoint bytes have not changed and rechecks
account agreement and freshness against the engine's actual clock. A delayed
start cannot reuse evidence that expired after construction. Only hashes and
timestamps of the reconciliation are added to the strategy audit.

Consumed signals, watermarks, order lineage, residual ownership, day/peak baseline
and loss latch survive. Default quote/exact-exit behavior remains unchanged.
Native recovery mode, fee mode or exit-policy mismatches do not migrate old state.

## Abrupt-exit acceptance

```bash
.venv/bin/python -m apps.strategies_nautilus.runners.portfolio_recovery_acceptance
.venv/bin/pytest -q tests/strategies_nautilus/test_portfolio_recovery.py tests/strategies_nautilus/test_portfolio_account_collector.py
.venv/bin/pytest -q -m 'not network and not postgres'
```

The CLI creates temporary files and two separate Python worker processes:

- Producer: native 0.001 BTC v16 fill and 0.000333 BTC v18 partial fill, BTC
  commissions, a quote-induced loss latch, and a whole-step v16 reduction leaving
  0.00000050 BTC. It persists a separately serialized synthetic account observation
  and exits via `os._exit(23)`, without strategy stop/end cleanup.
- Consumer: verifies different process IDs and restores v16 dust, v18's net
  0.00033250 BTC, its original 0.000667 BTC pending remainder, signal deduplication
  and the risk latch. A new crossing quote fills the original order. A duplicate
  signal creates no new order and the latch blocks a new sleeve's BUY. An owned
  v18 reduction succeeds, leaving **499.30060 USDT and 0.00000100 BTC**, four native
  orders total. A final full lineage/account check includes the new venue IDs.

The external observation here is **a synthetic serialization of the producer's
native state**, not an independently authenticated exchange. The test proves a
real process boundary, durable native reconstruction and coherent continuation;
it does not qualify a real account or establish performance evidence.

Focused verification: **61 new tests passed** (48 account/recovery, 13 collector).
The combined portfolio regression set passed **137 tests**. Tests cover response
drift, missing/duplicate history, locks, fee differences, identity/permissions,
freshness, pagination exhaustion, corrupt/mixed generations, policy/account-anchor
changes, replayed cursor, concurrent writer, delayed startup, uncertain submit and
pending-cancel refusal, and the abrupt two-process scenario.
Full offline verification: **1,990 tests passed**, with 12 Postgres integration
tests deselected because no dedicated DSN was supplied. Ruff lint, changed-file
formatting, registry validation and `git diff --check` passed.

## Explicit failure and deployment boundary

- If the last durable snapshot and fresh venue evidence disagree after a crash,
  recovery stops. It does not adopt an arbitrary newer balance or fabricate missing
  execution events. Native execution-report reconciliation and recollection are
  required to resolve such an incident.
- Prepared-but-missing, submitted-without-acknowledgement, pending-cancel and
  persistent halt states are not blindly resumed, cleared or resubmitted. No new
  cancel/replacement is sent. A lost in-flight command must be resolved from
  authoritative native/venue evidence before a later resume attempt.
- This persists client/native execution state, **not the simulated exchange's
  complete market queue or consumed-liquidity history**. Acceptance continues on
  new synthetic quotes and does not claim bit-identical replay of a pre-crash
  matching engine. A real exchange retains its own orders/queue; a real client
  bootstrap still needs native adapter reconciliation and stream continuity.
- No actual credentials or accounts were used. Signed transport, real fee/quantity
  conventions, API availability, complete archive, dynamic references, downtime
  market/risk history and stream synchronization remain unqualified. REST matching
  alone leaves `atomic_revision_verified=false` and `runtime_ready=false`.
- Full live process recovery is not claimed. Keep existing promotion gates, frozen
  SourcePolicy and the runtime 5% daily-loss ADR. The offline 50 USDT budget and
  residual re-entry policy still require reconciliation before deployment.

No upstream source, research evidence, sealed future PnL, schedules or live trading
path changed. Next entrypoint is qualifying a dedicated read-only account source
and stream/archive boundary, then exercising native execution-report recovery
through the real adapter under the existing environment gates.
