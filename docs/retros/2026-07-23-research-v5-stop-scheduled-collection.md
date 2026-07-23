# Research Protocol v5 scheduled collection closeout

- **Date**: 2026-07-23
- **Status**: Decision recorded; controlled Oracle shutdown pending
- **Decision**: `stop_scheduled_collection`
- **Reason**: `rejected_candidates_and_persistent_provider_instability`
- **Machine record**:
  `docs/progress/phase-2-research-v5-provider-timer-review.json`

## Decision

End Protocol v5 scheduled collection and archive the existing evidence. Also
disable the completed Protocol v2 timer. This is a lifecycle closeout, not a
research retry: no missing archive is backfilled, no validation rule changes,
no signal or PnL is generated, the 2026-08..12 blind stays sealed, and neither
testnet nor live trading is resumed.

The v5 identity is permanently closed. Any future study of similar data must
register a new protocol/provider identity before access; it must not restore
this timer and alter the rejected strategy after seeing these results.

## Evidence reviewed

The scheduled journal contains ten attempts for data dates 2026-07-17 through
2026-07-21. The 2026-07-17 08:15 retry is the last complete four-stream batch.
After it:

- the 04:15 first attempt returned HTTP 404 for every stream on every day;
- BTC delivery curve never recovered on retry;
- ETH delivery curve was intermittent and last succeeded on 2026-07-19;
- BTC BVOL remained available through 2026-07-21;
- ETH BVOL repeatedly failed the unchanged one-observation-per-UTC-second
  validation on every retry.

The last data date with any valid stream is 2026-07-21. The retained v5 tree
has 13 immutable snapshots and 13 normalized Parquets: BTC curve 2, ETH curve
3, BTC BVOL 6, and ETH BVOL 2. Vintage conflicts and comparison markers are
both zero. All journal reports kept `signals_generated=false` and
`pnl_computed=false`.

Protocol v2 remains complete: `COMPLETE` is present, its qualification ledger
has 14 rows, and checksums for `COMPLETE`, the ledger, and latest review are
recorded in the machine review. The v5 checkout is clean and its Git commit,
container image revision, and internal deployment identity all match
`d37d227874d49e88e8e8857f1bf45ea426ee7a3d`.

## Implementation and acceptance

`research.v5.collector_status.v2` adds the explicit `active|archived`
lifecycle. An archived artifact is accepted only when the timer is inactive
and disabled, the service is inactive, deployment identity is clean and
matching, and storage has no conflicts. The last incomplete batch remains
visible historical evidence but is not an active blocker. The terminal action
is `retain_archived_evidence` and there is no next trigger.

The dashboard continues to accept v1 and also accepts v2. It renders a valid
archive as archived, exposes the closeout reason/time and retained counts, does
not display a retry, and does not count the terminal state as an operational
fault. Invalid archive claims fail closed.

The controlled Oracle execution and post-trigger-window verification will be
added here after the first code/review commit is pushed. Until then the two
timers are intentionally unchanged.

Pre-shutdown verification passed: 99 collector/dashboard tests, the full suite
at 969 passed / 12 Postgres-dependent skips, repository-wide Ruff, strict JSON
and diff checks, Dashboard active-v2 snapshot smoke, frontend typecheck and
production build. `npm audit` initially found newly published Next.js/sharp
advisories; the minimal Next.js 15.5.21 patch plus a sharp 0.35.3 override
reduced the audit result to zero vulnerabilities.

## Boundaries

- No upstream `freqtrade/` or `nautilus_trader/` source is changed.
- No cloud checkout, image, data directory, or retained evidence is modified.
- No `SignalEvent`, `SourcePolicy`, credential, Nautilus runtime, testnet, or
  live-order path is opened.
