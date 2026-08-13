# 2026-08-13 Protocol v18 VXN Confirmation Review

- **Status**: passed every frozen confirmation gate.
- **Identity**: `rule_nasdaq_vol_relief_v2 /
  cboe-vxn-ohlc5obs-negative-1d-v1`.
- **Confirmation window**: 2023-01-01 through 2025-12-31.
- **Future blind**: sealed.
- **Trading effect**: none.

## Evidence

The contract was pushed at `813faee` and its committed-development evidence
lock was hardened at `d22081e` before holdout values were exported. The locked
VXN snapshot supplies 752 unfilled confirmation observations, 42 late-2022
warmup rows, a 2023-01-03 through 2025-12-31 boundary, and a maximum
four-calendar-day gap. No network request or interpolation was used.

The unchanged five-observation negative-change rule emits 144 state changes.
Two Nautilus replays from clean pushed commit `9360eb3` have identical fills
and signal-store fingerprints. Both are long/flat only. The one
exchange-unavailable BTC hour already verified by the v8 execution audit has
no order or fill event, leaving zero effective blockers.

## Results

| Metric | Result | Frozen gate |
|---|---:|---:|
| Gross PnL | +70.753350 USDT | diagnostic |
| Base PnL | +60.207790 USDT | > 0 |
| Stress PnL | +57.571400 USDT | > 0 |
| Positive years | 3/3 | >= 2/3 |
| Positive months | 20/36 | >= 18/36 |
| Closed positions | 72 | >= 30 |
| Leave-best base PnL | +35.304076 USDT | > 0 |
| Duplicate replays | identical fills | required |

Base yearly PnL is +1.020582 in 2023, +24.899783 in 2024, and +34.287425
USDT in 2025. The small 2023 gain is a caution for forward monitoring, but it
still passes the prospectively frozen annual, monthly, cost, activity, and
concentration gates without a parameter change.

## Decision

Classify the unchanged VXN identity as `paper_shadow_review_eligible`. This is
not an automatic SourcePolicy change. The next allowed action is a separate
ADR-007 review backed by a dry-run paper bundle. No collector installation,
paper-simulated order path, testnet/live action, or future-blind access is
authorized by confirmation alone.
