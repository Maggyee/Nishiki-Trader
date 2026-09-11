# Bounded LiveClock matching runtime — 2026-09-11

The ADR-017 fixture now has a separate wall-clock execution profile and one-shot
CLI: `apps.ops.portfolio_session_run --execute`. This joins the fixed account lease,
complete native CASH baseline, signed stream archive, native Strategy/RiskEngine/
queued execution adapter and durable one-attempt HTTP boundary. It is exclusively
Binance Spot testnet. The existing offline bridge and GET-only probe keep their
original guards. Production, SourcePolicy and portfolio qualification are unchanged.

## Admission and execution

The CLI requires clean committed code equal to the current branch's upstream.
There is no alternate state-root, session-ID, symbol, quantity or price override.
It uses the existing selected account artifact and Ed25519 configuration. Fresh
complete account observations, zero commissions and effective filters precede
activation. Full native-vs-signed reconciliation precedes each new order. All rule
inputs must still be within five seconds at the actual submit boundary.

`MatchingRuntimeLedger` explicitly requires LiveClock and permits at most one second
between native order initialization and validation. The original TestClock ledger
still requires exact time equality. The matching profile cannot convert a probe
checkpoint. Activation is exclusive and precedes the fixed `native.json`; errors
never delete it, replace session IDs or replenish allowances.

The deterministic engineering SignalEvent v1 feeds the existing native strategy.
The first BUY remains exactly 0.0001 BTC, at the newly observed best bid minus one
price tick, with at most 10 existing free test USDT allocated. Native RiskEngine
also enforces a 10-USDT per-order cap. No fill is guaranteed or forced.

Native Submitted or PendingCancel and the single dispatch receipt must be fsynced
before the exact matching request is signed and sent. The HTTP client allows only
POST/DELETE `/api/v3/order` with the original native terms/IDs. It pins the testnet
host, verifies the selected key, refuses direct transport calls, and never calls
the upstream signed-query logging path. Unsigned attempt selectors and raw HTTP
responses are retained privately. Any unknown response remains uncertain; no
synthetic rejection, resubmission, amendment or replacement is generated.

The lifecycle requests cancellation once, two seconds after native acknowledgement,
if the order remains active. A 20-second acknowledgement/terminal wait bounds the
controller; native HTTP has a 10-second timeout. A disconnected stream or uncertain
native history halts admission and requires original-ID reconciliation. It does not
blindly cancel through an unqualified replacement connection. This first runner
has no executable recovery/reconnect or automatic reduction after such a halt.

After a confirmed terminal BUY, complete signed orders/trades/balances must agree
with the native view before cleanup. Only whole effective steps of owned net BTC
can be offered in one SELL, at the newly observed best bid. Below-minimum residuals
are retained. All new orders retain the original 180-second deadline. SELL proceeds
cannot finance a second BUY; pre-existing BTC and every unrelated asset are retained.

Account notifications are correlated against native balance observations and never
assigned to the account. Pending notifications block new admission and successful
review. Complete signed final reconciliation is still mandatory; callback correlation
and stable REST bracketing do not prove global gap-free stream delivery.

## Recovery and operational limits

`apps.ops.portfolio_session_run --recover` opens a new signed subscription and reads
only the fixed matching checkpoint's original order IDs, their trades and complete
account-wide balances/orders. The native numerical reconciler writes a separate
immutable recovered checkpoint/report. It neither replaces the fixed matching
checkpoint nor sends an order/cancel, clears a halt, renews budget or claims readiness.
Missing original orders or ambiguous evidence remain blocked. It can be used after
an interrupted run; active-order reduction after recovery remains a later explicit
implementation, within the same fixed scope and original consumed allowances.

No services, schedules, dependencies, credential/permission changes, old execution
runners or production endpoints are added. Strict continuity remains 0/14; ADR-013
and ADR-015/016 full-account baseline/equity gates stay unqualified. This engineering
fixture is not a research promotion, portfolio allocation or real-money trial.

## Verification

The new tests exercise the actual LiveClock native queues and Ed25519 signer with a
stubbed network boundary: pre-send checkpoint receipts, exact parameters/signature,
RiskEngine denial, full owned cleanup, late fills during timed cancellation,
account callbacks before native settlement, disk/archive failures, transport timeout,
source/lease loss, stale evidence, forbidden routes, unknown reports and fixed-scope
reuse denial. Whole CLI tests run both an unfilled BUY/cancel and a filled BUY/SELL,
then open a separate GET-only recovery invocation and prove no further writes.
Existing offline partial-fill and abrupt-exit recovery tests remain applicable.

**31 new tests** and the full offline suite pass: **2,542 passed, 12 deselected**
(114.73 seconds; no dedicated Postgres integration DSN). Ruff, registry and whitespace
checks pass. The independent Ed25519 signature check uses existing OpenSSL; no
dependency was added. Actual testnet results will
be appended here after running the committed implementation; this implementation
section alone is not evidence that a matching order or cancellation was accepted.

## Actual testnet result — 2026-09-11 12:33 UTC

The committed, clean, pushed implementation **6d7c43b821750e5ee638b2d101b1596e302f1371**
executed the fixed scope successfully. Fresh capabilities again showed every
commission component zero. The BUY LIMIT was **0.0001 BTC at 76,908.15 USDT**,
notional **7.690815 test USDT**. Exactly one matching POST returned HTTP 200.
The signed stream delivered native NEW/Accepted and its account reservation event.

The native PendingCancel occurred **2,036.370024 milliseconds after Accepted**.
Exactly one original-ID DELETE returned HTTP 200; the stream delivered CANCELED
and the corresponding account release. The native lineage is Initialized →
Submitted → Accepted → PendingCancel → Canceled, with both dispatch receipts retained.
There was **no fill** and therefore no cleanup SELL. The four actual business events
were two execution reports and two account updates; both account updates correlated
without replacing any native balances. No halt was recorded.

| Final check | Matching process | Independent recovery process |
|---|---:|---:|
| Complete assets reconciled | 502 | 502 |
| Original orders queried | 1 | 1 |
| Exact trades returned | 0 | 0 |
| Account-wide open orders | 0 | 0 |
| Native session-owned BTC | 0 | 0 |
| BUY spent / reserved test USDT | 0 / 0 | 0 / 0 |
| Matching POST / DELETE sent | 1 / 1 | 0 / 0 |
| Original order status | CANCELED | CANCELED |

A second CLI process ran **`--recover`**, established a new signed subscription,
queried the same original order and complete account, and reproduced the identical
native view. It did not submit or cancel. The fixed matching checkpoint was not
replaced. Recovery's `matching_dispatches_recorded=2` counts the original retained
receipts; its own `matching_requests_made=0` correctly describes numerical recovery.

The matching invocation made 31 GETs (20 signed session reads, six signed capability
reads, four public capability reads and full public metadata), plus the POST and
DELETE. Fresh-process recovery made six signed GETs. No `/sapi`, production, retry,
replacement, external funding, unrelated-asset sale or additional BUY occurred.

Immutable private artifacts under
`~/.local/state/trader/spot-testnet-engineering-v1`:

| File | SHA256 |
|---|---|
| `native.json` | `08995a8289a99b88e02f87c9c07387302c8f74ed006e5a2a33ddf1932d0b1a5f` |
| `matching-178974c00a92-buy-capabilities.json` | `e0a14d39db8f602fc390c6314c4f571244bb97a754f519226dfc3b60e2b96e60` |
| `matching-178974c00a92-report.json` | `18f6e1a886adb7a7628e42cf86df8f4eda61b6aace88711db027a03151abcad3` |
| `matching-178974c00a92-stream.jsonl` | `2fd42b5420f8554eb46e1519edf8f1fa39c0a063f380ee8c94a81c79d1d52006` |
| `matching-178974c00a92-evidence.json` | `621460112ba6c71c472c9a7935eac1c4d73a0871840ed3e2dcd27625f9c39e52` |
| `matching-178974c00a92-recovered.json` | `99d360e68c1a90cee51abb93d8f59ef7ab2ef6b14dfe8a63f3ab915a9936d75a` |
| `recovery-2469aceead1b-report.json` | `eb6b8c52f042359bff563b4a9ed099649d9cbd8f8c1cb66975e1aaad979c6d71` |
| `recovery-2469aceead1b-stream.jsonl` | `7a41db12dbd89d4835978abc37c690b722a81b1831e3bc1dbc648d46c3ae4e6f` |
| `recovery-2469aceead1b-evidence.json` | `aff876bc270559aea8f8a60a6b159dc8295513bbf2a7b6f572b2a392b9a9a1a3` |
| `recovery-2469aceead1b-recovered.json` | `f294054526936a5b7c09fc91b6c8e7f64f171172901f11165ca1a6d201c82cce` |

The fixed activation and BUY allowance are now **consumed**, even though the order
was unfilled. Do not repeat `--execute`, reset/delete files, or create another scope
to force a fill. Terminal cancellation, actual reservation/release callbacks and
fresh-process terminal reconciliation are now verified. Actual fills, partial/late
fills, fee settlement, cleanup SELL and interrupted-active-order executable recovery
remain synthetic-only or unimplemented. A future increment should develop qualified
recovery/reduction without restoring BUY permission; no production or continuity
gate is advanced by this one canceled order.
