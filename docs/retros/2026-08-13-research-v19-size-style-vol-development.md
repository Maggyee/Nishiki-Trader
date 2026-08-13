# 2026-08-13 Protocol v19 Size/Style Volatility Development Review

- **Status**: complete; one development passer.
- **Development window**: 2020-01-01 through 2022-12-31.
- **Confirmation window**: sealed pending this committed review.
- **Future blind**: sealed.
- **Trading effect**: none.

## Data

VXFXI remains a provider rejection (533/700 reserve rows) and was not
backtested. RVX and VXD factors were exported from the qualified snapshots
captured after freeze `a2ea80a`. The four bundles below were replayed from
clean commit `4f4cbee`. Missing Binance hours use the already-frozen v7
downtime catalog; no order or fill hits a verified no-kline marker.

## Results

| Candidate | Signals | Gross | Base | Stress | Positive years | Positive months | Positions | Leave-best base | Decision |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| Russell vol relief (RVX) | 161 | -1.259300 | -7.025680 | -8.467275 | 2/3 | 19/36 | 81 | -16.254911 | reject |
| Dow vol relief (VXD) | 174 | +23.868440 | +17.483702 | +15.887517 | 2/3 | 20/36 | 87 | +7.660115 | development pass |
| China vol relief (VXFXI) | 0 | — | — | — | — | — | — | — | provider reject |

All RVX/VXD pairs reproduce with identical fills, zero shorts, zero effective
blockers, and zero verified no-kline event hits.

RVX is negative before and after costs. Removing its best position makes base
PnL more negative. The 2022 loss is -17.180565 USDT. The identity is rejected.

Dow Jones implied-vol relief clears every frozen development gate. The rule
holds BTC when the latest completed VXD close is strictly below the close five
official observations earlier. It has 87 positions, 20 positive months, and
remains positive after its best position is removed. 2022 is still negative
(-11.094103 USDT), so confirmation on 2023-2025 is required before any later
stage.

## Decision

Commit this review before opening confirmation. Only the unchanged
`rule_dow_vol_relief_v1 / cboe-vxd-ohlc5obs-negative-1d-v1` identity may open
2023-2025, and only after a separate confirmation contract is frozen. Do not
retune RVX, retry VXFXI, reverse signs, or create a PnL-selected ensemble.
v8/v16/v18 paper shadow, SourcePolicy, testnet, and live trading are unchanged.

Machine detail is in
`docs/progress/phase-2-research-v19-development-results.json`.
