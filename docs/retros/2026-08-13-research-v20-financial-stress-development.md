# 2026-08-13 Protocol v20 Financial-Stress Development Review

- **Status**: complete; one development passer.
- **Development window**: 2020-01-01 through 2022-12-31.
- **Confirmation window**: sealed pending this committed review.
- **Future blind**: sealed.
- **Trading effect**: none.

## Data and evidence

The single OFR snapshot qualified from pushed freeze `5d3a899`. Its three
required series share 762 unfilled development timestamps under a conservative
D+5 current-history reconstruction. The six bundles below were replayed from
clean commit `b875e6c` against the already-audited BTC hourly catalog.

All three duplicate pairs have identical fills, zero shorts, zero effective
blockers, and zero order/fill hits in verified no-kline hours.

## Results

| Candidate | Signals | Gross | Base | Stress | Positive years | Positive months | Positions | Leave-best base | Decision |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| Total financial-stress relief | 134 | -6.091350 | -10.913104 | -12.118542 | 2/3 | 17/36 | 67 | -21.915807 | reject |
| Credit-stress relief | 119 | -28.862230 | -33.280100 | -34.384568 | 1/3 | 13/36 | 60 | -39.968626 | reject |
| Safe-asset-stress relief | 152 | +17.108510 | +11.916318 | +10.618271 | 2/3 | 20/36 | 76 | +0.482873 | development pass |

Total and credit stress relief are negative after costs and fail concentration
or breadth gates. Both identities are rejected.

Safe-asset-stress relief holds BTC when the OFR `Flight_to_Safety` component
is below its value five common observations earlier. It clears every frozen
development gate, but leave-best margin is only +0.482873 USDT and 2022 loses
-20.924094 USDT. This is deliberately treated as fragile pending independent
2023-2025 confirmation.

## Decision

Commit this review before opening confirmation. Only the unchanged
`rule_ofr_safe_asset_stress_relief_v1 /
ofr-fsi-safe-assets-diff5-negative-lag5d-v1` identity may enter a separately
frozen confirmation. Do not retune the other two candidates, reverse signs,
construct an ensemble, claim historical publication vintages, mutate a policy,
or open the future blind.
