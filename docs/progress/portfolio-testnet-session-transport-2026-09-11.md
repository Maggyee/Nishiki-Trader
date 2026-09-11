# Actual testnet account bootstrap and source-bound recovery — 2026-09-11

The selected Ed25519 key now drives a **LiveClock full-account native bootstrap**
and a **fresh-process signed reconciliation** using the new session transport.
Both retained all **502 actual assets** and reconciled exactly. Two distinct
process invocations opened separate signed subscriptions. They observed zero
business events, orders and trades. This advances the
[offline queued adapter bridge](portfolio-testnet-session-bridge-2026-09-11.md);
it does not constitute a matching-order or active-order recovery acceptance.

## Fixed ownership and distinct probe scope

`portfolio_session_transport.SessionLease` uses one private default location,
`~/.local/state/trader/spot-testnet-engineering-v1`, across checkouts/processes.
The CLI has no alternate state-root or session-ID option. A private nonblocking
file lock owns the account scope. An immutable manifest binds the ADR-017 scope,
selected initial observation hash, source UID/key fingerprint and one session ID.
A different account, key or selection cannot silently replace that manifest.

A matching session's `activated.json` marker must be exclusively written/fsynced
before creating its fixed `native.json` ledger. Repeated activation fails. An
activation marker with no native checkpoint is ambiguous and cannot be treated as
a fresh allowance. Missing manifest with known activation/native/archive files is
rejected. The current probe **does not call activate**: `activated.json` and the
matching `native.json` do not exist. Repeated read-only probe filenames do not
create or replenish a matching allowance. The 10-test-USDT trial is still unused.

Private probe checkpoints, original metadata, evidence, reports and stream archives
are separate files inside that directory. Runtime README describes their purpose
and boundaries. No private files, credentials or actual account values are committed.
The lock coordinates this project's fixed path, not arbitrary external trading
software or exchange-side activity; the operator's no-other-trading statement
remains part of the account context.

## Signed session evidence

`SessionReadHttpClient` permits only exact GET requests to the Spot testnet:
complete account, account-wide open orders, an original known client order ID,
and that order's own trades. POST, DELETE, `/sapi`, foreign selectors, symbol-filtered
open-order reads and production hosts are refused. It uses the existing native
Ed25519 signer and HTTP transport without the upstream signed-URL logging path.
A request failure has no automatic retry.

`SessionJournal` is distinct from the old observation profile. A session collection
binds the selected checkpoint hash and current source/epoch/revision, then reads:

1. Complete account and account-wide open orders.
2. Each original client order ID and its original trades, if any.
3. Account-wide open orders and complete account again.

Stable bracketing responses, bounded time and the unchanged local subscription
fence are required. Raw successful responses and unsigned selectors are persisted
before parsing; an error aborts the collection. A full 1,000-trade page is refused
because completeness would be unknown. The original bounded experiment can halt
on that condition; it never infers missing fills or performs blind pagination.

Order responses retain original bytes in the archive. The numerical reconciler
gets a fixed projection of economic/identity fields so extra endpoint-specific
fields do not manufacture drift. Foreign account-wide orders still fail. Native
recovery additionally checks full trade coverage, original intent/fees, balances,
locks and ownership. A completed *capture* seal is not by itself a successful
native reconciliation.

The collected object binds its immutable digest, original checkpoint, source,
fence and a five-second freshness limit. Those are rechecked before and after
native numerical recovery. The numerical engine retains its existing detached
`offline_testnet_session_recovery_v1` input schema and `source_authenticated=false`;
the outer transport receipt separately records `signed_source_bound=true`.
That means the actual HTTP client and current signed subscription were checked,
not independent historical identity or global stream continuity. Closing the
subscription makes its fence unusable. Saved reports cannot grant fresh admission.

## Real-clock native bootstrap and callbacks

`portfolio_session_bootstrap.py` adds an explicit
`testnet_liveclock_readonly_probe_v1` profile. It maps the full account using fresh
full exchange metadata, then parses BTCUSDT with the native Binance provider.
Native accounting precision is eight places; effective order sizing remains a
separate future execution check. The probe does not verify current fees or derive
order permission from the provider's default fee values.

The whole observed account becomes a calculated native CASH baseline, explicitly
`reported=false`, with zero session-owned inventory and no position inferred from
pre-existing faucet BTC. This is a prospective numerical anchor, not qualified
equity or a UTC day-open baseline. All amounts remain exact; unsupported metadata
or rounding prevents bootstrap.

The prior serializer read the clock several times per checkpoint, which works
with TestClock but fails state/native timestamp equality under LiveClock. It now
samples one cursor for the completed native transaction and freezes only the
serialization view. The original SessionLedger still requires TestClock. The new
read-only subclass separately requires LiveClock and forbids prepare, dispatch
and cancel. Its native execution engine forbids command execution and client
registration. No offline execution guard was removed to make an account runnable.

The source journal archives the entire WS envelope before any callback. Its
execution handler feeds the existing checked native Binance report parser and
queued native events. Account notifications are correlated against native balance
observations; they never replace the account. A changed unrelated asset halts;
unresolved BTC/USDT notifications remain pending and block successful review.
Unknown events/foreign subscriptions, persistence failure or handler rejection
invalidate the subscription. These handlers are **tested with synthetic events**;
no actual business event arrived in the two real runs below. Correlation under an
active matching lifecycle remains unqualified.

## Actual network evidence

The bootstrap invocation issued one unsigned full exchangeInfo GET and eight
signed account/open-order GETs. A second process recovered its selected output
using four new signed GETs. Total: **13 GETs**, including **12 signed GETs**;
two separate signed subscriptions; **zero matching POSTs, DELETEs or business events**.
No credential/permission change, service, schedule or production request occurred.

| Check | Bootstrap process | Fresh recovery process |
|---|---:|---:|
| Actual assets retained and reconciled | 502 | 502 |
| Account-wide open orders | 0 | 0 |
| Original orders/trades available to reconcile | 0 / 0 | 0 / 0 |
| Signed GETs | 8 | 4 |
| New signed subscription | 1 | 1 |
| Observed business events | 0 | 0 |
| Matching scope activated | false | false |
| Matching enabled / runtime ready | false / false | false / false |

`native_reports_reconciled=true` in the generic result means the native numerical
reconciliation completed; with zero known orders here, it is **not proof of real
order/trade endpoint permissions, fills or active adapter recovery**.

Immutable private artifacts under the fixed state directory:

| File | SHA256 |
|---|---|
| `probe-f1e7298c0af9-report.json` | `72afa19855d4a78a54ea6cd2774ba857ba39ed3bc5a6f51c3f2ee8c8bec003b9` |
| `probe-f1e7298c0af9-stream.jsonl` | `05473e9c4557dd1df78a4b0cb8d15c2aeef45b99b300cc951b7fd9b018bad856` |
| `probe-f1e7298c0af9-recovered.json` | `1252a9f2d16fac392268e13ddb7ccd5f8f211e799118c0ea746fcbc61839115c` |
| `probe-1f0aae63932f-report.json` | `5ced039895d66f3ca4929ef9af56979dea016feb9125106ab5af770b6b7eef3b` |
| `probe-1f0aae63932f-stream.jsonl` | `11d122072c476a384ef76196952b4cc9ee35705482d8b565a17d1867e65cfde4` |
| `probe-1f0aae63932f-recovered.json` | `2861274d5b128d40be20315904b84799db8ecb199eaca7d0cfd13ab49965b751` |

Both diagnostic reports record base commit `932331c` and `code_dirty=true`.
They are immutable account/transport diagnostic evidence, not clean-code matching
session or promotion bundles. Later reporting/cleanup/test refinements did not
rewrite those inputs or trigger another network probe.

## Verification and next operation

**34 new tests** cover signed known-order collection and native reconciliation,
receipt/source/clock changes, mid-reconciliation disconnect, incomplete fills,
foreign orders, full pages, timeout/no retry, forbidden hosts/methods/selectors,
pre-callback raw persistence, callback failure, fixed-scope locking/activation,
missing or failed activation state, LiveClock snapshots and explicit command denial.
The full offline suite and code checks are recorded in project status.

```bash
.venv/bin/python -m apps.ops.portfolio_session_transport
.venv/bin/python -m apps.ops.portfolio_session_transport --checkpoint /absolute/fixed-scope/probe-...-recovered.json
.venv/bin/pytest -q tests/strategies_nautilus/test_portfolio_session_transport.py
.venv/bin/pytest -q -m 'not network and not postgres'
.venv/bin/ruff check apps tests notebooks
.venv/bin/python -m apps.ops.research_family_registry --check
git diff --check
```

Next is the **bounded matching runtime**, using the fixed activation path and
fresh complete account/zero-fee/effective-filter evidence. It must join the verified
queued native receipt barrier to a separate exact-whitelist matching client, the
native risk/strategy path and deterministic acknowledgement/cancel timers. Cover
that LiveClock write path and account/fill correlation under timeout/disconnect,
then execute the 0.0001 BTC / 10-test-USDT trial within ADR-017. The read-only probe
must not be switched into trading by removing a guard or registering a legacy client.
No new Key or general permissions questionnaire is needed.

Changed code: session transport, read-only bootstrap, ops probe CLI and the shared
single-cursor serializer; new tests and application documentation. Upstream source,
production/live paths, SourcePolicy, ADR-015/016 full-account qualification and the
strict 0/14 continuity gate remain unchanged.
