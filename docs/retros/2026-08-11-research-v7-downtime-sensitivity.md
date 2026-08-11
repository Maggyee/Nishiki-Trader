# 2026-08-11 Research v7 Downtime Sensitivity

- **Status**: complete; post-hoc diagnostic only.
- **Formal Protocol v7 decision**: unchanged; zero candidates selected.
- **Future blind**: sealed and unopened.
- **Trading effect**: none.

## Why the hourly bars are absent

The gaps are present in the official Binance source, not introduced by the
local downloader or Parquet conversion. All 36 monthly ZIP files match their
current official SHA-256 checksums. The 14 exact missing windows also return
zero klines from the official Spot REST endpoint. An independent official
daily ZIP check for 2020-02-19 contains only 19 rows and matches its checksum;
its five missing hours are identical to the monthly archive and REST response.

The multi-hour dates align with archived Binance Spot maintenance notices,
including 2020-02-19, 2020-06-28, 2021-04-25, and 2021-08-13. The defensible
data conclusion for all 14 windows is narrower: Binance generated no official
Spot kline during those windows. They are exchange-side non-trading/no-kline
periods, not recoverable missing trades.

## Sensitivity construction

The original `data/research-v7/` evidence was not modified. A separate ignored
catalog under `data/research-v7-downtime-sensitivity/` retains all 26,274
official bars and adds 30 explicit downtime markers so the hourly clock has
26,304 rows. Each marker uses the previous real close for OHLC, zero volume,
and metadata declaring that trading was unavailable and the price is not
executable evidence. The completed catalog audit reports zero duplicates,
gaps, or irregular steps.

This is not conventional price interpolation: no high, low, close movement or
volume is invented inside a closed matching-engine window. It is still
post-hoc because the marker treatment was chosen after seeing Protocol v7 PnL.

## Re-test

Six clean-commit Nautilus backtests ran on commit
`1b431d6e6b368b914831965c9c135ae56cea8361`. Each candidate ran twice and all
three normalized comparisons returned `MATCH`. No order or fill timestamp
coincides with a synthetic marker.

| Candidate | Base | Stress | Positive months | Leave-best base | Sensitivity result |
|---|---:|---:|---:|---:|---|
| VIX relief | +9.538828 | +8.041265 | 21/36 | -1.373440 | reject |
| OVX relief | -2.443604 | -3.986020 | 15/36 | -13.355872 | reject |
| GVZ relief | +18.871408 | +17.434647 | 24/36 | +6.266502 | numeric pass only |

The results are unchanged to their reported precision. Therefore the missing
hours did not create, erase, or move any trade in this batch, and they do not
explain GVZ's positive result.

## Decision

The sensitivity evidence increases confidence that GVZ's historical result is
not an artifact of these exchange downtime windows. It does not retroactively
make the original incomplete-catalog gate pass. Protocol v7 remains formally
closed with zero selected candidates and the future blind sealed.

Any promotable follow-up must be a new protocol whose continuity rules are
frozen before PnL access. Such a protocol may explicitly distinguish verified
exchange downtime from unexplained data loss, but it may not present these
synthetic markers as tradable prices or reuse the sealed v7 future blind.

Machine detail is in
`docs/progress/phase-2-research-v7-downtime-sensitivity-results.json`.
