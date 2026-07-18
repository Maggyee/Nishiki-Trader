# 2026-07-18 Research Protocol v5 first scheduled collection

- **Result**: 08:15 UTC retry complete; four new immutable vintages accepted.
- **Data date**: 2026-07-17.
- **Deployment commit**: `d37d227874d49e88e8e8857f1bf45ea426ee7a3d`.
- **Signals/PnL**: none.
- **Trading effect**: none.

## Scheduled attempts

The first timer attempt started at 04:15:00 UTC and finished at 04:15:03 UTC.
All four archive requests returned HTTP 404, so the batch remained incomplete,
each stream retained `desired_state=flat`, and the service returned the locked
nonzero incomplete-batch status. It wrote no partial snapshot, generated no
signal, computed no PnL, and created no conflict marker.

The scheduled retry started at 08:15:08 UTC and finished at 08:15:16 UTC. It
completed all four registered streams:

| Stream | Asset | Vintage suffix | Result |
|---|---|---:|---|
| delivery curve | BTCUSDT | `3066bfbfe0a0` | valid |
| delivery curve | ETHUSDT | `29460c62d226` | valid |
| BVOL | BTCUSDT | `daaff1ad10af` | valid |
| BVOL | ETHUSDT | `ff604553027a` | valid |

The batch report recorded `valid_snapshot_count=4`,
`failed_snapshot_count=0`, `complete=true`,
`vintage_conflict_count=0`, `signals_generated=false`, and
`pnl_computed=false`. The service result is `success` with exit status 0. The
timer remains active/enabled and next schedules 2026-07-19 04:15 UTC.

This one observation establishes only that the 2026-07-17 archives were absent
at 04:15 UTC and present by 08:15 UTC. It does not justify changing the timer.
Future first-attempt failures remain expected flat operational evidence; any
schedule adjustment requires several days of actual publication observations.

## Offline verification

All checks ran in the locked collector image with `--network none`, a read-only
bind mount, a read-only container filesystem, and all Linux capabilities
dropped.

- `research_v5_snapshot --verify` recomputed every official checksum, raw-file
  hash, content hash, snapshot hash, request identity, audit value, availability
  timestamp, and normalized value for each of the four new snapshots. All four
  returned `valid=true`.
- Each new Parquet contains exactly one row and its columns and values exactly
  match the snapshot's embedded normalized envelope.
- The data root now contains 8 snapshots and 8 normalized Parquets: four July
  qualification vintages plus the four new 2026-07-17 vintages.
- The data root contains 0 `comparison-blocked-*.json` conflict artifacts and
  0 `RESULT_COMPARISON_BLOCKED` markers.
- The deployed checkout is clean. Its HEAD, the image OCI revision, and the
  expected collector commit all remain `d37d227...`; image ID remains
  `sha256:7ad7f96146922078a141cc6e6c9fe92d1182e3f23767295570d40a375c6cdd8f`.

## Research boundary

This successful collection does not reopen Protocol v5. Curve carry and BVOL
relief remain `reject_v5_candidate`; the 2026-08..12 blind remains sealed.
The collector may preserve future raw evidence only. It cannot generate
signals or PnL, fill or interpolate data, retune either rule, combine sleeves
to hide an asset loss, change `SourcePolicy`, resume testnet, start Nautilus,
or touch live orders.
