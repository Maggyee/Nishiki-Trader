# Phase 2 Research Protocol v9

- **Frozen**: 2026-08-11, before reading the VIX9D or VVIX CSV body.
- **Machine contract**: `docs/progress/phase-2-research-protocol-v9.json`
- **Status**: pre-registered; provider qualification pending.
- **Trading effect**: none.

## Why this batch is allowed

The original 16-family stop rule remains binding. Protocol v8 supplied new
independent evidence that the official Cboe history chain can support a
point-in-time cross-asset strategy. v9 does not retune any rejected OHLCV,
funding, flow, rotation, or Protocol v7 identity. It tests two higher-order
option-risk mechanisms: the equity-volatility curve and volatility of
volatility.

SKEW is deliberately excluded. Cboe announced that its methodology should be
modified, so a long historical test could cross a definition change that is
not yet stable enough for this protocol.

## Locked candidates

1. **Equity volatility curve** — hold BTC only when the completed VIX9D close
   is strictly below the same-session VIX close. An inverted short end is flat.
2. **Volatility-of-volatility relief** — hold BTC only when VVIX is strictly
   lower than five official observations earlier. Zero or an increase is flat.

Both candidates are BTCUSDT Spot long/flat, emit only on state changes, use a
one-day TTL and confidence 0.75, and start each scored period flat. No sign
flip, threshold search, parameter grid, or PnL-selected combination is allowed.

## Sequential evidence rule

The 2020-01-01 through 2022-12-31 development reserve may be opened once after
provider qualification. A candidate must pass every frozen cost, breadth,
activity, concentration, lineage, continuity, and duplicate-replay gate before
its 2023-01-01 through 2025-12-31 confirmation result may be opened. A failed
candidate stops; it cannot be reparameterized under v9.

The existing 2026-09 through 2027-01 future blind remains sealed. v9 cannot
open it or modify the GVZ paper-shadow policy.

## Provider qualification

The VIX9D and VVIX links come from Cboe's official VIX historical-data page.
The pre-access collector may fetch each body exactly once and record only raw
bytes/hash, schema, dates, row count, and development coverage. It may not
calculate a signal or PnL. The already-frozen v7 VIX snapshot is reused without
refreshing it.

## Boundaries

No credentials, SourcePolicy change, testnet restart, future-blind access, or
live path is authorized. The pre-access contract and collector must be clean,
committed, and pushed before either new CSV body is downloaded.
