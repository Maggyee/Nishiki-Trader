# 2026-07-17 Research Protocol v5 Spot lineage qualification

- **Status**: passed locally; historical Spot execution access remains closed
  until this retro is pushed.
- **Pre-access implementation commit**: `8bcdb46`.
- **Strict-JSON fix commit**: `d7a2022`.
- **Qualification date**: 2026-07-16 UTC.
- **Returns/PnL accessed**: no.
- **Trading effect**: none.

## Why this qualification was added

The locked v5 provider contract applies its immutable raw snapshot envelope to
the Spot execution archives as well as the curve and BVOL factors. The generic
catalog importer preserved a ZIP but did not preserve the official checksum,
HTTP metadata, retrieval time, content hash, or upstream-revision vintages.
This was identified before any historical Spot execution body was opened.

`spot_execution` now uses `research.raw_snapshot.v2`. It validates the official
checksum, preserves exact ZIP/checksum bytes and HTTP metadata, rejects
overwrite, creates a comparison blocker for changed content, requires exactly
1,440 ordered UTC-minute rows, and imports only an offline-verified,
conflict-free vintage into the existing v5 Nautilus catalog. The Nautilus
runtime is lazy-loaded only for this explicit kind, so the cloud curve/BVOL
collector remains lightweight and read-only.

## Dry-run and real qualification

The clean-commit dry-run planned the official BTCUSDT daily Spot URL and its
`.CHECKSUM`, reported `network_accessed=false` and `data_written=false`, and
left the Spot snapshot tree at zero files.

The first real local qualification wrote one BTCUSDT and one ETHUSDT immutable
snapshot. Both contained 1,440 minute rows with a complete grid. A first
idempotent catalog import disclosed that Nautilus prints "already exists"
messages to stdout; those messages polluted the otherwise strict JSON ledger.
No data or catalog row was invalid. Commit `d7a2022` captures that library
stdout and adds an idempotent regression test. The clean-commit rerun then
produced strict JSON, verified both snapshots offline, and skipped no required
validation.

Evidence fingerprints:

- BTCUSDT archive: `sha256:0c72247a29194970b655259ff74426939bf0d358daae07d172093daadc24d987`
- BTCUSDT snapshot: `sha256:f96ffb814292db61e4bbfd63ad887eb3ecd27d9e9e1c314489c910849f6deb89`
- BTCUSDT canonical rows: `sha256:fa792d6ebbc8240d89d22e5ed54688cb665e4f2cea58fc023762537268d71194`
- ETHUSDT archive: `sha256:529b1a89ac3abd9ab88fd9d0f981b4b67d416bec654d437f4ffd61a5ef8c9050`
- ETHUSDT snapshot: `sha256:009e2fcc1efd8da8e042ab5f58a9eae9f023a4a82a64a6d13abddc335c0022f4`
- ETHUSDT canonical rows: `sha256:490c37a8452a501c244ec1459fb2c35dfbb076b9fb79553936f2be3be3598971`

Each new envelope's archive hash exactly matches the corresponding July ZIP
used in the earlier catalog qualification. The read-only catalog audit reports
1,440 rows per asset, zero duplicates, zero missing or irregular intervals,
correct UTC bounds, and complete BTC/ETH timestamp alignment.

## Boundary audit and next action

No SignalEvent, SignalStore row, Nautilus backtest, return, PnL, credential,
SourcePolicy mutation, testnet resume, or live path was used. The future blind
and v5 daily timer remain closed. After this retro is committed and pushed,
only the five locked historical scoring folds may be downloaded through the
new immutable Spot route.
