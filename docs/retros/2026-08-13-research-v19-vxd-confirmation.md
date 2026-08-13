# 2026-08-13 Protocol v19 VXD Confirmation Review

- **Status**: confirmation failed; candidate rejected.
- **Confirmation window**: 2023-01-01 through 2025-12-31.
- **Paper-shadow eligibility**: none.
- **Future blind**: sealed.
- **Trading effect**: none.

## Evidence

The VXD-only contract was committed and pushed at `25690ca` before holdout
value export. Qualification from the existing immutable snapshot produced 752
unfilled observations, 42 warmup rows, and a maximum four-day gap. The factor
qualification was committed at `6f342e9` before signal generation or PnL.

Two clean cash-account Nautilus replays from `6f342e9` reproduce with identical
fills. Both consume 187 unchanged signals, close 94 long-only positions, and
have zero effective blockers or events in the verified exchange-unavailable
hour.

## Result

| Gross | Base | Stress | Positive years | Positive months | Positions | Leave-best base |
|---:|---:|---:|---:|---:|---:|---:|
| +71.365380 | +57.492785 | +54.024636 | 3/3 | 17/36 | 94 | +34.350455 |

All frozen performance gates pass except monthly breadth. The required minimum
is 18 positive months; VXD has 17. The classification is therefore
`reject_candidate`, despite positive cost-adjusted PnL and concentration
resilience.

## Decision

Do not reduce the breadth threshold, retune the lookback, change the sign,
combine VXD with another observed strategy, or open the future blind. The
identity does not qualify for ADR-007 or `paper_shadow`. RVX and VXFXI remain
rejected. Protocol v20 remains a separate pre-registered study whose OFR body
has not yet been opened.
