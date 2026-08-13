# 2026-08-13 Protocol v30 Google/Alphabet Vol Confirmation Review

- **Status**: confirmation failed; protocol closed.
- **Identity**: `rule_cboe_google_vol_relief_v1 / cboe-vxgog-diff5-negative-lag1d-v1`.
- **Confirmation window**: 2023-01-01 through 2025-12-31.
- **Future blind**: sealed.
- **Trading effect**: none.

## Evidence

The confirmation contract was on `origin/main` before holdout-value export.
The factor was taken from the already-captured VXGOG snapshot with no new GET,
no fill, no interpolation, and no historical-vintage claim. Coverage is 752
unfilled confirmation observations, 42 warmup rows, and a four-day maximum
gap.

Two clean cash-account Nautilus replays from `69fa1a9` consume the same 184
signals and close 92 long-only positions. Fills match. There are zero
effective blockers, shorts, or events in the verified exchange-unavailable
hours.

## Result

| Gross | Base | Stress | Positive years | Positive months | Positions | Leave-best base |
|---:|---:|---:|---:|---:|---:|---:|
| +18.235660 | +5.161518 | +1.892982 | 2/3 | 21/36 | 92 | -10.350719 |

Annual base PnL is +4.1002 / +16.8547 / -15.7933 USDT for 2023/2024/2025.
Leave-best base PnL is negative, so the identity is rejected. It may not be
retuned, sign-flipped, ensembled, or promoted.

Apple and Amazon remain development-rejected. Existing paper-shadow policies,
SourcePolicy, testnet, live trading, and the future blind are unchanged.
