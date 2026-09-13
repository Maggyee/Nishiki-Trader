# Full-account / UTC / cash-flow evidence gap review — 2026-09-13

The selected September 11 account reference and completed ADR-017 session now
pass one combined offline review. All **502 assets** are retained; the endpoints
have **zero unexplained net balance differences** after accounting for native
session fills/fees. This does **not** qualify the full-account risk baseline:
there are still two unpriced assets, no independent UTC midnight/peak baseline,
and no complete external-flow/reset history. ADR-015 risk inputs remain null.

## What the new review establishes

`apps.ops.portfolio_testnet_baseline_review` reuses the original admission reviewer
and historical session archive reviewer. It revalidates all five pinned original
inputs: initial account selection, account archive, bound market capture, session
archive and original native checkpoint. It does not trust a later report's flags
instead of replaying the original evidence. Native mapping uses its existing
isolated subprocess; run this CLI in a fresh process for native session recovery.

The reference must precede the session start, and its selected UID/key/endpoint
binding must match the session. Source changes and overlapping/backward intervals
fail; a later checkpoint or another collection cannot silently replace an input.

For each asset in the union of all three snapshots, the report compares:

```text
known session delta = reconciled historical end total - session baseline total
observed endpoint delta = reconciled historical end total - earlier reference total
unexplained net delta = observed endpoint delta - known session delta
```

Totals include free plus locked balances; native reconciliation already accounts
for actual fills and commission currency. A change in reference-to-session locks
is reported separately from a change in total funds. Missing assets, including
zero rows, remain explicit coverage gaps with null deltas. Nonzero unexplained
deltas are not automatically labeled deposits, withdrawals or trading PnL.

Even zero unexplained net delta cannot exclude offsetting external transfers,
intervening trading, reset/replenishment or unsampled events. `cash_flow_history_complete`
and `reset_history_verified` always remain false; external net cash flow in USDT
remains null. Historical balance equality does not establish absence of flows.

The original market valuation applies only to its original account capture. The
review never carries those prices forward to the later session or today's review.
It retains original unpriced/depth limitations, reports actual UTC timestamps and
offsets, and keeps qualified current/day-open/peak equity, daily/peak loss and the
effective daily limit null—even if all marks are available, endpoints agree, or
an observation timestamp happens to fall exactly at midnight.

The policy parameters are imported from ADR-015's shared module: daily cap 25 USDT,
fraction 0.05, fixed peak-loss ceiling 250 USDT. They are policy constants, not
measured loss headroom. No provisional 500 USDT or priced subtotal becomes equity.

The CLI reads bounded private files and writes one new exclusive mode-0600 report.
It loads no credentials, contacts no venue and writes no fixed session state or
execution checkpoint. Exit 0 means the historical gap review completed with the
baseline still blocked; invalid inputs/output publication return 1 with sanitized
errors. Detailed balances stay private; stdout contains counts, status and report hash.

## Actual selected evidence

Original references come from
[September 11 admission](portfolio-testnet-admission-2026-09-11.md) and
[September 11 cancellation recovery](portfolio-testnet-cancel-recovery-2026-09-11.md).
No new exchange observation was collected.

| Original input | SHA256 |
| --- | --- |
| Initial account selection | `205cf2a16badecf973889f5de92ceede53d902d294d92eec565ff060f6c422cc` |
| `spot-testnet-baseline-20260911T054139Z.jsonl` | `0b4638db102fa21f7d574d0184c6ba27ebdde9d653b6fca33dc8f6f276bd78c3` |
| `spot-testnet-baseline-20260911T054139Z-market.json` | `0b8606a2165c84b7cefb05bd7e460ab510765a3d9ef7c4a37a5b030413a4380d` |
| `cancel-recovery-9c1359b2b5f4-stream.jsonl` | `63eab354a2b2130eba3af4743cda2b62eaf47a5a4f2ec7ad255a279b372e9ca2` |
| Original `native.json` | `08995a8289a99b88e02f87c9c07387302c8f74ed006e5a2a33ddf1932d0b1a5f` |

Account collection: `acd69464-4f34-4741-bbfd-46fe585b2e11`.
Session collection: `85d5fab6-126a-4851-b62b-54b071f97b07`.
All five pinned originals were verified unchanged after the final review.
The selected private output `data/spot-testnet-baseline-gap-review-20260913-v2.json`
has SHA256 `254fac56d653ff797d9e3669e3039d62a76735f98ceffc8f135ebc7019fc0255`.
The earlier private diagnostic remains immutable and is not the selected final output.

| Check | Historical result |
| --- | --- |
| Reference completion | 2026-09-11 05:42:03.400925 UTC (not midnight) |
| Session start | 2026-09-11 12:33:48.103307 UTC |
| Selected session observation | 2026-09-11 12:55:07.451625 UTC |
| Assets compared / missing / unexplained net deltas | 502 / 0 / 0 |
| Reference-to-session locked balance changes | 0 |
| Reference indicative marks / unpriced assets | 500 / 2 |
| Per-asset top-book capacity exceedances | 65 |
| Historical session fills / open orders / owned BTC | 0 / 0 / 0 |
| Original dispatches | 2 (consumed BUY and cancellation) |
| Qualified current/day-open/peak equity and loss inputs | null |
| Current venue confirmation / baseline qualification / runtime readiness | false |

## Concrete remaining evidence and order of work

| Gap | Needed evidence or decision | What existing evidence cannot substitute |
| --- | --- | --- |
| Two unpriced nonzero test assets | Supported testnet price paths for the complete account, or a separately reviewed prospective account/scope decision | Zero prices, deleting assets, assumed stablecoin pegs, production or old last prices |
| Quote freshness and account/market synchronization | Prospectively retained native account and quote events, event timestamps and explicit synchronization/gap acceptance | Nearby REST receipt times; historical bookTicker without qualified event age |
| UTC day-open and peak history | Independently qualified full-account baseline and complete applicable UTC/peak history under ADR-015 | First later snapshot, midnight label alone, 500 USDT planning capital |
| External flows and resets | Complete independently supported funding/reset history for the qualified interval; explain every balance delta | Equal endpoint balances, no-other-trading statement, owned-session fills alone |
| Identity and key restrictions | Qualified source/permission evidence supported by the selected environment | A second copy of the existing Key, canTrade, signed GET success, unsupported `/sapi` calls |

Next prepare a concrete **prospective account/quote evidence contract and provider
coverage review** against these gaps. That review must identify what the selected
Spot testnet APIs can actually prove before proposing collection or deployment.
It must not claim that a new scheduler or a few midnight samples alone solve the
independent-baseline or reset-history requirements. No service/schedule is started
by this task. Old absent history remains absent; any scope or qualification-policy
change requires its own explicit decision, not a reinterpretation of this report.

The completed ADR-017 scope stays consumed. Actual fills/fees/owned cleanup and
active recovery remain unverified on the exchange; synthetic acceptance and this
net-balance comparison do not substitute for them. Strict continuity stays 0/14,
SourcePolicy and production execution remain unchanged.

## Verification

20 new tests cover native-filled session integration, exact asset-unit deltas,
positive/negative unexplained changes, locked funds, missing zero assets, all-priced
but unqualified baselines, source/order/hash refusal, UTC rollover, exact-midnight
nonqualification and missing quotes. The standalone CLI test blocks credential
reads and network connections, permits only the existing isolated mapping child,
checks private output, preserves all inputs and rejects output overwrite.

Full offline regression: **2,697 passed, 12 deselected** in 211.00 seconds.
The 12 Postgres integration tests lack a dedicated integration DSN. Ruff, registry
and whitespace checks pass. Current progress is updated in `docs/project-status.md`.
No upstream source, live order path, risk-policy value, dependency, credential,
service, schedule or fixed session file was modified.
