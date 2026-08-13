# 2026-08-13 Protocol v20 Safe-Asset Stress Confirmation

- **Status**: complete; candidate rejected.
- **Identity**: `rule_ofr_safe_asset_stress_relief_v1 / ofr-fsi-safe-assets-diff5-negative-lag5d-v1`
- **Confirmation window**: 2023-01-01 through 2025-12-31 by D+5 `available_at`.
- **Future blind**: sealed.
- **Trading effect**: none.

## Data

The confirmation contract and 783-decision factor qualification were on
`origin/main` at `b99962c` before signals or PnL. Duplicate Nautilus cash
replays used the already-audited v8 BTC hourly catalog. Fills match, git is
clean, and no order or fill hits a verified no-kline hour.

## Results

| Gross | Base | Stress | Positive years | Positive months | Positions | Leave-best base |
|---:|---:|---:|---:|---:|---:|---:|
| +47.630810 | +35.946934 | +33.025964 | 3/3 | 17/36 | 74 | +18.107091 |

Evidence gates pass. Performance fails solely on monthly breadth: 17 positive
months versus the frozen minimum of 18. 2023/2024/2025 base PnL is
+6.937888 / +25.850035 / +3.159011 USDT.

## Decision

Reject the identity. Do not lower the 18-month gate, retune, reverse the sign,
or ensemble it with rejected total/credit stress rules. It is not eligible for
ADR-007 or `paper_shadow`. v8/v16/v18 collectors, SourcePolicy, testnet, live
trading, and the shared future blind stay unchanged.

Machine detail is in
`docs/progress/phase-2-research-v20-confirmation-results.json`.
