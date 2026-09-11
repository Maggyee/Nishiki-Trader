# ADR-017 queued native adapter bridge — 2026-09-11

The engineering fixture now passes through a dedicated **Nautilus Strategy,
RiskEngine, queued LiveExecutionEngine and Binance Spot adapter**, with durable
native receipts before each adapter attempt. This completes the offline bridge
increment after [session ledger/recovery acceptance](portfolio-testnet-session-recovery-2026-09-11.md).
It uses TestClock, synthetic accounts and an in-memory HTTP sink. **No credentials,
network requests, matching orders or exchange cancellations were used.**

## Native execution and persistence

`portfolio_session_bridge.py` adds an isolated fixture strategy using the existing
SignalEvent v1 identity and ADR-017 ledger. Native RiskEngine checks remain enabled;
a separate 10-USDT per-order cap is installed by the harness. The ledger enforces
the smaller whole-session scope: one fixed 0.0001 BTC BUY, one owned cleanup SELL,
zero expected fees, the 180-second bound and no allowance recycling. Native minimum
notional in the shared synthetic instrument now agrees with its existing 5-USDT
effective fixture rules; previously the test-kit instrument retained 10 USDT and
would deny the fixture's 7-USDT order when actually passed through RiskEngine.
No observed exchange filter or existing execution runner was changed.

The native Binance adapter's `generate_order_submitted` enqueues an event; its
return alone does not mean the order is updated or durable. The bridge registers
a receipt future before that call and waits, at most two seconds, for the queued
native event transaction and checkpoint fsync to finish. Only then may the native
LIMIT serializer enter the fixture HTTP sink. Native callbacks finish account,
order and position processing before the checkpoint is captured. Reentrant strategy
admission while that transaction is in progress is rejected.

Nautilus Strategy applies/publishes PendingCancel directly, outside the execution
engine event queue. A dedicated callback persists it after the existing ledger
has durably recorded cancellation intent. Both paths require the exact native
event in the previously acknowledged checkpoint before consuming a dispatch.

`SessionLedger.record_dispatch` records one `submit:<original-id>` or
`cancel:<original-id>` attempt and the original native event ID. Its checkpoint
must finish before the sink records a request. An attempt is consumed even if a
process subsequently dies before an outbound request could occur. This is an
attempt receipt, not proof of exchange acceptance. A delayed submit also fails
once its original preparation is older than five seconds, or the session expires.
The optional new `dispatches` state survives existing native recovery without
changing old checkpoint versions or granting old checkpoints send permission.

The adapter uses the upstream LIMIT/cancel parameter serializers, but excludes
the common retry and exception-to-Rejected path. Timeout, task cancellation or
other attempt failure keeps Submitted/PendingCancel uncertain and persists a halt
when storage is healthy. It never fabricates Rejected/CancelRejected to imply
absence at the venue. Disk failures poison the writer; no subsequent send or
attempt to restore the prior free budget is allowed. If native settlement succeeds
but disk persistence fails, the old complete checkpoint remains the recovery anchor;
its now-stale contents are not represented as the current account.

## Callback scope and transport boundary

Known synthetic `executionReport` bytes are decoded and handled by the native
Binance Spot schema. The wrapper checks original order identity, venue ID, LIMIT
terms, timestamps, fill precision, actual fee fields, cumulative quantity/notional
and terminal status. Missing fills and altered duplicate trades halt before native
processing; exact duplicate fills still reach native deduplication. Back-to-back
callbacks account for events which have been queued but not yet applied.

Late valid fills continue to settle after a transport halt. Supported unexpected
fees are accounted exactly and retain the ledger's persistent fee halt. Unknown
orders, changed terms, missing commission evidence and unsupported messages fail
closed. The current fixture does **not** apply outboundAccountPosition to overwrite
calculated balances: an account message halts this unqualified callback surface.
Source-bound account-stream correlation and signed full-account reconciliation
remain the next integration work.

The HTTP sink constructs no signed request and never calls the network transport.
It accepts only the native fixture's exact POST/DELETE `/api/v3/order` selectors
and values at the fixed testnet base URL. Real `send_request`, connections,
amendments, batches and automatic queries/reconciliation are denied. The engine
accepts only its own fixture adapter; both bridge and engine require TestClock.
This intentionally has no LiveClock configuration, real key loader, reconnect
bootstrap, automatically timed matching lifecycle or production runner.

The fixture uses one selected checkpoint and rejects replacement with a new
session ID at that path. This is still **not a global account/session lease**.
A future real runner must bind one fixed account/scope path across invocations,
preserve the original session ID and never create a new authorized experiment
merely by selecting a different filename.

## Acceptance

The queued 502-asset fixture submits a 7-USDT BUY through native risk and execution,
receives a 0.00004 BTC partial fill, requests cancellation after the two-second
acknowledgement delay, receives another 0.00004 BTC while cancellation is pending,
receives a duplicate, then receives CANCELED. Final session ownership is
**0.00008 BTC**, debit **5.6 USDT**, two unique native fills and no remaining lock.
All 502 synthetic assets remain represented, including the pre-existing 2 BTC.
The two fixture HTTP attempts are not external requests or matching evidence.

Additional tests cover full BUY plus exact owned cleanup, the native risk denial
path, five persistence-failure boundaries, callback persistence failure, missing
Submitted receipt timeout, cancellation of an awaiting HTTP task, delayed
preparation, unexpected fees, malformed/conflicting/missing stream evidence,
forbidden routes and absence of live-clock/network capability.

Two scenarios each span three separate process invocations:

| Abrupt-exit boundary | Recovery from independent fixture reports | Dispatch receipts preserved |
|---|---|---:|
| Native Submitted + submit dispatch durable, before fixture response | Original BUY becomes FILLED, 0.0001 BTC owned | 1 |
| Native partial fill + PendingCancel + cancel dispatch durable, before fixture response | Additional late fill, CANCELED, 0.00008 BTC owned | 2 |

The producers call `os._exit(23)` without strategy stop or cleanup. Separate
consumer/replay processes use the existing native report reconciler, preserve all
502 assets and consumed allowances, and produce stable economic views. These
are synthetic recovery reports, not authenticated source or global stream evidence.

**44 new bridge tests; 91 combined bridge/ledger tests.** Full offline regression:
**2,477 passed**, 12 PostgreSQL integration tests deselected because no dedicated
integration DSN was supplied. Full application/test/notebook Ruff, the research
family registry and whitespace checks passed.

```bash
.venv/bin/python -m apps.strategies_nautilus.runners.portfolio_session_bridge_acceptance
.venv/bin/pytest -q tests/strategies_nautilus/test_portfolio_session_bridge.py tests/strategies_nautilus/test_portfolio_session_ledger.py
.venv/bin/pytest -q -m 'not network and not postgres'
.venv/bin/ruff check apps tests notebooks
.venv/bin/python -m apps.ops.research_family_registry --check
git diff --check
```

## Next operation

Build the explicit real-testnet runtime profile around this verified receipt
barrier: fixed account/session ownership, selected Ed25519 source, fresh zero-fee
and effective-filter checks, native account/instrument bootstrap, signed original
order/trade collection and source-bound stream callbacks. Correlate account
notifications with complete native fills before comparing all balances; never
repair native state by assigning remote totals. Exercise disconnect/unknown-response
recovery through that actual transport before starting the bounded matching trial.
Do not substitute the legacy runners or remove the offline guard to imply readiness.
The existing key and earlier TRADE validation remain recorded; no additional key
submission or general permissions questionnaire is needed.

Full-account ADR-015/016 equity/day-open qualification stays separate and blocked.
This increment does not start the strict 14-day clock, change SourcePolicy, add a
service/schedule/dependency, accept ADR-013 or authorize real-money trading.
Upstream checkouts and installed upstream code were read only. The live path is
unchanged; only project-owned fixture/ledger code, tests and documentation changed.
