# Historical fixed-session archive replay — 2026-09-13

The retained ADR-017 session response archive now reproduces its original sealed
recovery evidence and reconciles the historical native account in a standalone
process, including after the collector's 24-hour window expires. It does not query
the exchange, revive a stream fence or authorize an order/cancel/restart.

## Implementation

`apps/strategies_nautilus/portfolio_session_archive.py` accepts explicit archive
and original checkpoint SHA256 references plus one collection ID. The checkpoint
pins the testnet source and contract. The parser checks the entire newline-terminated
hash chain, sequence, source, monotonic receipt times and unique subscription epochs,
including the tail after the selected seal. The selected collection must bind the
original checkpoint, start after it and within the original 24-hour history window,
and finish within 60 seconds without a business event, restart, disconnect, abort
or competing collection. Transport heartbeat records may occur without changing
the selected epoch. Missing raw bodies or completion seals fail closed.

It checks the exact original account/openOrders/order/myTrades sequence, unsigned
selectors, original IDs, each raw-body hash, the less-than-1000 trade-page bound,
stable full-account brackets and account-wide active-order coverage. Reconstructed
canonical evidence must match the original `session_collection_completed` seal.
The detached result contains evidence bytes and provenance metadata, with no live
journal, client, lease, fence or `assert_current` capability.

`apps.ops.portfolio_session_archive` reads bounded private files with explicit
selection arguments. Run it as a separate Python process because native currency
registration is process global. `recover_session` reconstructs at the **original
receipt time**, while the report separately records review time and historical
age. This does not change source timestamps or the live collector's freshness and
history gates. The original intents, cancellation preparation, dispatches, session
identity, deadline and existing halts must survive native reconciliation. Newly
observed fee halts remain latched.

Only a new exclusive mode-0600 diagnostic report is published; no restorable
checkpoint, session activation or fixed-state replacement is written. Existing
outputs are never overwritten. CLI stdout contains sanitized status/counts/hashes,
not private raw responses or account-wide balances. Exit 0 means historical review
completed. It always reports `current_venue_state_verified=false`,
`source_authenticated=false`, `new_orders_authorized=false`,
`cancel_retry_allowed=false` and `runtime_ready=false`.

Hash references select retained bytes; they do not authenticate the venue or repair
lost history. Hashing damaged files now cannot establish their former completeness.
An original input checkpoint is required: the later recovered output cannot be
substituted merely because its balances match. This profile remains separate from
strict portfolio account archives and observation-only testnet archives.

## Actual retained evidence

The September 11 references in
[the cancellation recovery report](portfolio-testnet-cancel-recovery-2026-09-11.md)
selected the following existing files under the fixed private session directory:

| Input | SHA256 |
| --- | --- |
| `native.json` | `08995a8289a99b88e02f87c9c07387302c8f74ed006e5a2a33ddf1932d0b1a5f` |
| `cancel-recovery-9c1359b2b5f4-stream.jsonl` | `63eab354a2b2130eba3af4743cda2b62eaf47a5a4f2ec7ad255a279b372e9ca2` |
| Original sealed evidence | `5ca0213543cb9110eb353bf3f02c048649be97e205b246ab665fb1299e842b65` |
| Original recovered checkpoint used for comparison | `d097a49e24edb32729846241c89f491e20c4e0fce99c21cd05b71d56da362b07` |

Selected collection: `85d5fab6-126a-4851-b62b-54b071f97b07`.
The standalone September 13 review reproduced the **identical evidence hash** and
historical native view. All **502 assets** reconcile, the one BUY is **CANCELED**,
there are **zero fills, zero open orders, zero session-owned BTC** and **two original
dispatch records**. Each pinned original file remained byte-identical.
The private `archive-review-20260913.json` has SHA256
`5c84a43d0d48e1acc5cad24233f8ded70c2e22b0b8ce39c9c84965b9b1f2736d`.
This review used the working implementation before its documentation/commit; it was
an offline diagnostic, with zero venue requests and no execution deployment.

The history window is expired. This is a reproduction of September 11 evidence,
not a September 13 exchange observation. The consumed BUY/cancel scope remains
closed. It provides no actual fill, fee, cleanup SELL or active recovery evidence.

## Verification and next step

**56 new tests pass**: archive truncation, full-tail corruption, duplicate keys,
rehashed structural/source/epoch/time changes, missing seals, selector violations,
pagination, unstable brackets, foreign orders and native economic mismatches.
Two fresh CLI processes reproduce the same BUY historical native view, preserve
inputs, and reject output overwrite. A guarded process forbids credential reads,
network connection/DNS, subprocesses and live client/journal/lease construction.
Missing/wrong/public/symlink checkpoint inputs fail with sanitized output.

Synthetic SELL tests cover missed fills, exact residual ownership and base locks,
late fills, terminal cancellation and USDT fee halts. Historical reconstruction
retains consumed BUY/SELL/cancel attempts and unrelated balances. The report exposes
no checkpoint for execution. These fixtures remain synthetic acceptance only.

Full offline regression: **2,677 passed, 12 deselected** in 199.46 seconds.
The 12 Postgres integration tests require an unavailable dedicated DSN. Ruff,
research registry and whitespace checks pass; current status is recorded in
`docs/project-status.md`.
No upstream source, existing execution/collector admission, SourcePolicy, dependency,
service, schedule, credential permission or production path changed.

Next progress should address ADR-016 full-account valuation, qualified UTC day-open
and cash-flow evidence through an offline acceptance/gap review. Do not repeat the
completed trial to obtain fills, widen the historical window, reset activation or
change original IDs. Actual fills/fees/cleanup and strict 0/14 continuity remain
unqualified and need their own prospectively approved evidence scope.
