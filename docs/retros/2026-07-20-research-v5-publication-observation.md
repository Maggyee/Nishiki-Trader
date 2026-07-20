# Protocol v5 Publication Observation: Durable Review Trigger

- **Date**: 2026-07-20
- **Scope**: passive observation of the scheduled 08:15 UTC retry for data date
  2026-07-19
- **Result**: incomplete; durable provider/timing review trigger reached
- **Collector identity**: `d37d227874d49e88e8e8857f1bf45ea426ee7a3d`

## Observation

The collector ran from 08:15:16 through 08:15:23 UTC. ETH delivery curve and
BTC BVOL succeeded. BTC delivery curve remained unpublished with HTTP 404 and
wrote no snapshot. ETH BVOL failed validation with `must contain one
observation in every UTC second` and wrote no snapshot. The batch therefore
recorded 2 valid and 2 failed streams for data date 2026-07-19.

This is the first of the three planned 08:20 batch observations and is
incomplete. More importantly, the ETH BVOL failure is the same every-second
validation failure recorded in the 2026-07-18 baseline. Under the approved
observation protocol, recurrence on a later data date is a durable
provider/timing review trigger; later oracle observations are skipped.

Storage now contains 11 snapshots and 11 Parquets, with zero vintage conflicts
and zero comparison markers. Checkout and image revision both match the clean
collector commit. The image ID remains
`sha256:7ad7f96146922078a141cc6e6c9fe92d1182e3f23767295570d40a375c6cdd8f`.
The timer remains active and enabled, with its next scheduled trigger at
2026-07-21 04:15 UTC.

The status artifact is read-only. Credential loading, SignalEvent writes, PnL,
SourcePolicy mutation, Nautilus startup, testnet resume, and live-path access
all remained false. Strict JSON parsing and status/dashboard consistency
assertions passed.

## Decision

Do not retry or backfill, change the collector or timer, open blind data,
generate signals or PnL, or loosen the every-second validation rule. A separate
provider/timer review is next. It must evaluate publication behavior and timing
without weakening validation or changing the frozen Protocol v5 identities.
