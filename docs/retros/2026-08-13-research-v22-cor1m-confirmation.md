# 2026-08-13 Protocol v22 COR1M Confirmation Review

- **Status**: confirmation passed; separate ADR-007 `paper_shadow` review eligible.
- **Identity**: `rule_cboe_implied_correlation_relief_v1 / cboe-cor1m-diff5-negative-lag1d-v1`.
- **Confirmation window**: 2023-01-01 through 2025-12-31.
- **Future blind**: sealed.
- **Trading effect**: none.

## Evidence

The confirmation contract was on `origin/main` at `d303fb5` before holdout
value extraction. The qualified 752-observation factor hash was then committed
at `0dac1cc` before signals or PnL. No network request, fill, interpolation, or
historical-vintage claim was used for confirmation data.

Two clean cash-account Nautilus replays from `0dac1cc` consume the same 155
signals and close 78 long-only positions. Both fills files have SHA-256
`b9bc07d4…27462e2`. There are zero effective blockers, shorts, or events in the
verified exchange-unavailable hour.

## Result

| Gross | Base | Stress | Positive years | Positive months | Positions | Leave-best base |
|---:|---:|---:|---:|---:|---:|---:|
| +41.704460 | +29.737095 | +26.745253 | 2/3 | 18/36 | 78 | +14.242905 |

Annual base PnL is +1.166107 / +29.387830 / -0.816843 USDT for
2023/2024/2025. Monthly breadth passes exactly at the frozen 18-month minimum;
all other performance and execution-evidence gates pass with wider margins.

## Decision

The unchanged identity is `paper_shadow_review_eligible`. This is not an
automatic policy change or trading authorization. A separate identity-specific
ADR-007 review must decide whether to hold it at dry-run `paper_shadow`, with a
signed SourcePolicy and entry evidence. Do not retune the rule, count this
historical confirmation as forward evidence, resume testnet, touch live
trading, or open the future blind.
