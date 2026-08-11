# 2026-08-11 Protocol v9 Option-Risk Development Review

- **Status**: complete; both candidates rejected.
- **Development window**: 2020-01-01 through 2022-12-31.
- **Confirmation window**: sealed and not opened.
- **Future blind**: sealed and not opened.
- **Trading effect**: none.

## What was tested

The batch was frozen and pushed before either new Cboe CSV body was read. It
tested two BTCUSDT Spot long/flat mechanisms:

1. hold BTC when VIX9D is strictly below same-session VIX;
2. hold BTC when VVIX is below its value five official observations earlier.

VIX9D and VVIX each provide 756 official observations in the development
window. Every observation becomes available at the next UTC midnight, no
calendar or value is forward-filled, and every signal carries snapshot/vintage
lineage.

## Corrected execution boundary

The first four backtest bundles are invalid attempts. Passing
`--catalog-end 2022-12-31` ended the runner at 00:00 and omitted the final 23
hours. The manifests exposed `blind_window_not_fully_covered` and an early
system-exit lineage blocker. The exact frozen interval was then rerun with
`2022-12-31T23:59:59Z`; no strategy parameter, signal body, cost, gate, or
catalog changed. Only the four corrected bundles are evidence.

## Results

| Candidate | Signals | Base PnL | Stress PnL | Positive years | Positive months | Positions | Leave-best base | Decision |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| VIX9D below VIX | 85 | +15.269651 | +14.537709 | 2/3 | 12/36 | 43 | -1.628722 | reject |
| VVIX 5-observation relief | 165 | +2.540920 | +0.991650 | 2/3 | 21/36 | 83 | -7.023792 | reject |

Both duplicate pairs match exactly, remain Spot long/flat, and have no order or
fill in any of the 30 official REST-empty Binance hours. The generic catalog
row blocker is fully explained by the already-frozen session audit; no
synthetic bar is used.

## Interpretation

The curve rule is profitable after modeled costs but too narrow: only one third
of calendar months are positive and removing its best position makes the
result negative. It is concentrated in 2021 and loses materially in 2022.

VVIX relief has better monthly breadth and enough activity, but its small total
edge is dominated by its best trade. It also loses 21.323390 USDT in 2022.
Removing the best position changes base PnL from +2.540920 to -7.023792.

These are useful negative results: the data and execution evidence pass, while
the economic robustness gates fail. The right decision is rejection, not a
threshold adjustment or a combination selected after seeing PnL.

## Decision

Protocol v9 stops with zero development passers. Do not open 2023-2025
strategy-specific confirmation PnL, alter either model version, create a
PnL-selected ensemble, or feed either source into paper/testnet. The confirmed
GVZ paper-shadow process continues unchanged.

Machine detail is in
`docs/progress/phase-2-research-v9-development-results.json`.
