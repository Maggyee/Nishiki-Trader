# 2026-08-13 Protocol v18 Geographic/Style Volatility Development Review

- **Status**: complete; one development passer.
- **Development window**: 2020-01-01 through 2022-12-31.
- **Confirmation window**: sealed pending committed development review.
- **Future blind**: sealed.
- **Trading effect**: none.

## Data

The three official Cboe OHLC histories were qualified from `77afac1` with
755/755/758 unfilled 2020-2022 observations. A first backtest batch recorded
`git_dirty=true` and is not evidence. The six bundles below were replayed from
clean commit `a4ff746`. Fills match the discarded dirty batch; only provenance
changed. Missing Binance hours use the already-frozen v7 downtime catalog;
no order or fill hits a verified no-kline marker.

## Results

| Candidate | Signals | Gross | Base | Stress | Positive years | Positive months | Positions | Leave-best base | Decision |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| EM vol relief (VXEEM) | 166 | +2.164750 | -3.849353 | -5.352879 | 2/3 | 18/36 | 83 | -17.448356 | reject |
| EAFE vol relief (VXEFA) | 190 | +4.543120 | -2.377915 | -4.108174 | 1/3 | 18/36 | 95 | -10.622922 | reject |
| Nasdaq vol relief (VXN) | 162 | +20.114830 | +14.128562 | +12.631995 | 2/3 | 21/36 | 81 | +3.151905 | development pass |

All pairs reproduce with identical fills, zero shorts, zero effective blockers,
and zero verified no-kline event hits.

VXEEM is slightly positive before costs and negative after costs. Removing its
best position makes base PnL more negative. The 2022 loss is -9.908199 USDT.
The identity is rejected.

VXEFA is also cost-negative, has only one positive year, and fails leave-best
concentration. It is rejected.

Nasdaq-100 implied-vol relief clears every frozen development gate. The rule
holds BTC when the latest completed VXN close is strictly below the close five
official observations earlier. It has 81 positions, 21 positive months, and
remains positive after its best position is removed. 2022 is still negative
(-11.701216 USDT), so confirmation on 2023-2025 is required before any later
stage.

## Decision

Commit this review before opening confirmation. Only the unchanged
`rule_nasdaq_vol_relief_v2 / cboe-vxn-ohlc5obs-negative-1d-v1` identity may
open 2023-2025. Do not retune VXEEM or VXEFA, reverse signs, or create a
PnL-selected ensemble. v17 remains closed. v8/v16 paper shadow, SourcePolicy,
testnet, and live trading are unchanged.

Machine detail is in
`docs/progress/phase-2-research-v18-development-results.json`.
