# Read-only source, user stream and native adapter qualification — 2026-09-10

Status: **offline native signing, stream journal and adapter reconciliation
acceptance implemented**. No private account HTTP or actual WebSocket connection
was made. This advances the September 9 process-recovery work; it does not qualify
a real account or enable runtime recovery/admission.

## Source binding and signed collection

`portfolio_stream.bind_source` binds the explicit official REST endpoint, expected
account UID and SHA256 of the supplied API key. The collector checks this binding
against the stream before collection and rechecks the client after collection.
The signed `/account` response must still match the expected UID. Key rotation,
account mismatch, stream changes and reconnects invalidate collection.

Tests instantiate the installed Nautilus `BinanceHttpClient`, run its unchanged
`sign_request`, and replace only network `send_request`. An independent HMAC
calculation checks the signature, key header and GET method. Inputs and credentials
are synthetic. This verifies the signing path, not the origin of a real response.
No key, secret or signed URL is written to the journal; its key fingerprint and
raw account events are still private account metadata and must stay under ignored
local data. Permission observations remain explicit: GET-only behavior does not
prove that the API key itself lacks trading permissions.

The existing collector requires `/sapi/v1/account/apiRestrictions`; allowing a
testnet host does not prove that this endpoint or its permission evidence exists
there. Unavailable permission/account endpoints fail closed, without production
fallback or a fabricated read-only permission. Real endpoint qualification remains
necessary before selecting a test environment.

## Observed stream boundary

`UserStreamJournal` records a single-writer JSONL SHA256 chain, checks complete
records/source/hash linkage on reopening, and fsyncs each accepted event. A process
restart always starts disconnected. Transport integration must supply a confirmed
subscription ID and the same source binding, report health/disconnections, and
serialize callbacks and collector completion on one owning event-loop thread.
**No transport is wired by this change**; a manually supplied acknowledgement is
not authenticated exchange evidence.

Each subscription has a fresh local epoch, even if Binance reuses its subscription
ID. Every accepted account event, including identical execution-report replay,
changes the local revision. Collection captures a fence before REST and records
response hashes only if the same fence is still valid afterward. Consumers must
call `assert_fence` again at use; the fence is an in-memory observation token, not
a transferable approval artifact. `atomic_revision_verified` stays **false**.

Execution reports are indexed by symbol/order/execution ID. Identical duplicates
are archived; conflicting duplicates invalidate the session. Execution IDs need
not be consecutive or globally ordered. Partial `outboundAccountPosition` rows
are validated and archived, never treated as a complete account snapshot.
Disconnect, transport expiry, wrong subscription, stale/future or malformed
messages, transfers, external locks, termination and unknown event types require
requalification. Failed persistence permanently blocks the current journal object.
The replay index is bounded; reaching its limit stops the session for rotation.

This proves only locally observed receipts and changes. A hash chain is not an
exchange signature and cannot independently detect removal of an entire valid
archive suffix. REST agreement, pongs, subscription IDs and local receipt numbers
cannot prove global gap-free delivery or cover downtime. The current Binance
Spot documentation does not supply such a global consecutive sequence here.

## Actual native adapter code, synthetic account bodies

`portfolio_adapter_recovery` validates complete original order/trade history
before using Nautilus 1.226.0's actual Binance schema converters and
`LiveExecutionEngine` mass-status reconciliation. Its isolated engine requires
`TestClock`, refuses execution-client registration and trading commands, and
rejects inferred fills. No position reports are injected to synthesize lifecycle
adjustments. All new fills and positions are applied by Nautilus.

The preparation gate requires known order coverage, account/instrument/position
lineage, unchanged LIMIT/GTC intent, unique venue/trade IDs, exact fill history and
notional, valid times and side, and supported actual fees. BTC BUY commissions
and USDT commissions are supported within the existing per-fill 15 bps ceiling;
BNB, off-step quantities, off-tick prices, sub-quantum commissions, missing fills,
historical fee conflicts and terminal-state regressions are refused.
After native reconciliation, order status, filled quantity and every trade's
quantity/price/commission are checked exactly; native success alone is insufficient.
Failures require discarding the isolated cache: native reconciliation is not a
transaction with rollback. Independent account/locks, sleeve and risk-history
qualification remain the responsibility of the existing account/recovery gates.

Acceptance includes an uncertain submitted BUY resolved from original fills:
0.001 BTC gross becomes **0.00099850 BTC / 400 USDT** after actual base commission.
Replay does not charge the fee again. A pending cancel with a second late 0.000333
BTC fill becomes canceled at **0.00066500 BTC / 433.4 USDT**, retaining its original
position ID. Unfilled NEW/CANCELED/EXPIRED states create no inventory. Actual USDT
commission produces **0.001 BTC / 399.85 USDT** in the separate fee case.

These tests exercise the real native converter/reconciliation implementation in
one isolated process. The September 9 abrupt-exit/fresh-process tests also remain
green, but their synthetic venue IDs and recovery gate are unchanged. The new
adapter fixture is not connected to that recovery bootstrap or to any live runner.
Uncertain commands remain blocked there; nothing resubmits or cancels at a venue.

## Verification and next entrypoint

```bash
.venv/bin/pytest -q tests/strategies_nautilus/test_portfolio_stream.py tests/strategies_nautilus/test_portfolio_adapter_recovery.py tests/strategies_nautilus/test_portfolio_account_collector.py tests/strategies_nautilus/test_portfolio_recovery.py
.venv/bin/pytest -q -m 'not network and not postgres'
.venv/bin/ruff check apps tests notebooks
.venv/bin/python -m apps.ops.research_family_registry --check
git diff --check
```

54 new tests: 32 stream/source/native-signing cases and 22 adapter-recovery cases.
Full offline verification: **2,044 passed**, 12 Postgres tests deselected without
an integration DSN. Ruff, registry and whitespace checks pass.

The next external acceptance needs an explicit environment, existing credential
variable names/config path and expected account UID; never paste secret values.
Then qualify endpoint/permissions and signed account evidence, integrate the
native WebSocket subscription with durable observation and reconciliation, and
test disconnect/restart recovery against independently retained history. Complete
downtime risk coverage and reconcile planning loss limits with runtime ADRs before
any admission integration. No schedules, SourcePolicy, promotion, SignalEvent v1,
5% runtime loss rule, existing runners or upstream source changed.

Public references inspected September 10 (public documents only):

- [Binance Spot user data stream](https://github.com/binance/binance-spot-api-docs/blob/master/user-data-stream.md)
- [WebSocket API: signed user-data subscription](https://github.com/binance/binance-spot-api-docs/blob/master/web-socket-api.md)
- [Spot REST API](https://github.com/binance/binance-spot-api-docs/blob/master/rest-api.md)
