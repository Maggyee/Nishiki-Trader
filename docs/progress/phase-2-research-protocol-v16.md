# Phase 2 Research Protocol v16

- **Frozen**: 2026-08-12 before opening any Treasury CSV body.
- **Status**: development complete; one candidate is confirmation-open eligible.
- **Trading effect**: none.

V16 preserves v15's three economic rules but moves them to direct official
U.S. Treasury annual CSVs and assigns new provider/model fingerprints. The
nominal route supplies 2-year and 10-year yields; the real-yield route supplies
the 10-year real yield. All eight 2019-2022 nominal/real annual URLs returned
HTTP 200 to body-free HEAD qualification.

Rows are normalized by field name and date, sorted, deduplicated, restricted
to the registered window, and inner-joined only where all required values are
numeric. No value is filled. Observations become usable after two calendar
days, which is conservative relative to the Treasury's same-day published
closing curve. Current files are official reconstruction evidence, not a claim
that their HTTP bodies existed unchanged at each historical decision.

The 2020-2022 development reserve and existing performance/evidence gates are
unchanged. The 2023-2025 confirmation may open only after a full development
pass is committed. V15 is not retried; v12-v14, GVZ paper shadow, SourcePolicy,
testnet, live trading, and the shared future blind remain unchanged.

## Development outcome

All eight annual bodies passed audit. The numeric nominal/real inner join has
791 observations from 2019-11-01 through 2022-12-30, a maximum four-calendar-
day gap, and no filled value. Snapshot SHA-256 is
`5b281c2cd540c1226325969fedb3ecca17d5f936d9992922f226934e202549ac`.

| Candidate | Signals | Base / stress PnL | Positive years / months | Positions | Leave-best base | Decision |
|---|---:|---:|---:|---:|---:|---|
| Real-yield relief | 50 | +23.053854 / +22.608183 | 3/3 / 14/36 | 25 | +3.223758 | insufficient evidence |
| Yield-curve steepening | 47 | +45.902945 / +45.538659 | 2/3 / 7/36 | 24 | +5.029640 | insufficient evidence |
| Treasury-yield volatility relief | 151 | +55.211116 / +53.821362 | 2/3 / 20/36 | 76 | +35.236938 | development pass |

All duplicate pairs reproduce exactly, remain Spot long/flat, have no
effective blockers, and place no event in a verified Binance no-kline hour.
Only Treasury-yield volatility relief passes every development gate. Its
result must be committed before any 2023-2025 confirmation body is opened.

## Confirmation outcome

The development review was committed at `2e4edbf`, then the single-candidate
confirmation contract was pushed at `37187ca` before 2023-2025 bodies opened.
The three nominal Treasury files contain 749 numeric observations, no fill,
and no gap above four calendar days.

The unchanged Treasury-yield volatility rule emits 159 confirmation signals
and closes 80 positions. Gross/base/stress PnL is
`+50.699030/+37.668725/+34.411149` USDT; all three years and 19/36 months are
positive, and leave-best base PnL remains `+19.510103`. Duplicate fills match,
with zero shorts, effective blockers, or verified no-kline event hits.

The identity is `paper_shadow_review_eligible`. This is permission to perform
the separate ADR-007 paper-shadow policy review, not an automatic SourcePolicy
mutation or trading start. The 2026-09..2027-01 future blind remains sealed.
