# Trend-Regime 2025 Blind Review

- **Date**: 2026-07-10
- **Source/model**: `rule_trend_regime_v1 / ema24-96-1h-mom24-atr14x0.5-v1`
- **Pre-registration commit**: `b8c7ee2a07e8023788fe7a48c66dc4f25393fb7d`
- **Locked blind window**: 2025-08-01 through 2025-12-31 UTC
- **Recommendation**: `stop_before_testnet_resume`
- **Policy effect**: None

## Decision

Reject this fingerprint as an alpha candidate. It met the mechanical evidence
requirements but failed profitability in all three scenarios and produced only
one base-positive month. It must not enter `paper_shadow`, must not be tuned
against this opened window under the same `model_version`, and does not justify
resuming testnet continuity.

No `promotion_review.py` command was run and SourcePolicy was not changed.

## Pre-registration and development screen

The economic hypothesis, complete fingerprint, and untouched 2025-08..12 blind
window were committed and pushed before any 2025 market data was downloaded or
read. The prior 2024-08..12 development screen then produced:

| gross | base (10 + 2 bps) | stress (10 + 5 bps) | base-positive months | closed positions | result |
|---:|---:|---:|---:|---:|---|
| +16.191970 | +10.844598 | +9.507755 | 3/5 | 29 | passed the pre-registered continuation screen |

The development gate deliberately required only positive aggregate
gross/base/stress, Spot long/flat behavior, clean evidence, and exact replay.
It did not qualify the source for paper. Bundles
`20260710-053017Z-8c63508d` and `20260710-053023Z-60211b0d` reproduced with
fills sha256
`3df3bf6a4a833f8af0953c191a24fb96c50c85f2341cd5da449ac87421f5967d`.

## Data audit

Only after the development screen passed was Binance public BTCUSDT 1m data
through 2025-12-31 imported. The importer detects the archive's timestamp unit;
this is required because Binance Spot archive timestamps switch to microseconds
from 2025-01-01.

| scope | rows | expected | duplicate timestamps | minute gaps | range |
|---|---:|---:|---:|---:|---|
| 2025 | 525600 | 525600 | 0 | 0 | 2025-01-01 00:00 .. 2025-12-31 23:59 UTC |
| 2024 + 2025 | 1052640 | 1052640 | 0 | 0 | 2024-01-01 00:00 .. 2025-12-31 23:59 UTC |

## Locked blind result

Both CASH/NETTING NautilusTrader runs used 100000 USDT starting balance,
0.001 BTC trade size, the same risk settings, and the locked signal filter.

| metric | result | gate |
|---|---:|---|
| gross net PnL | -13.634510 USDT | reference only; negative |
| base net PnL | -21.238820 USDT | fail: must be > 0 |
| stress net PnL | -23.139897 USDT | fail: must be > 0 |
| base-positive months | 1/5 | fail: must be at least 4/5 |
| closed positions | 31 | pass: at least 30 |
| short positions | 0 | pass |
| invalid lineage / blockers | 0 / 0 | pass |
| reproducible | yes | pass |

Monthly scenario net PnL:

| month | gross | base | stress |
|---|---:|---:|---:|
| 2025-08 | -1.187310 | -2.285496 | -2.560043 |
| 2025-09 | -3.383999 | -5.410791 | -5.917489 |
| 2025-10 | +4.015289 | +2.781317 | +2.472824 |
| 2025-11 | -1.492000 | -2.375509 | -2.596386 |
| 2025-12 | -11.586490 | -13.948341 | -14.538803 |

The same-size buy-and-hold reference also lost money in this market window:
gross `-28.080780`, base `-28.324833`, stress `-28.385846` USDT. That context
does not relax the candidate gates.

## Evidence identity and reproducibility

| run | manifest sha256 | fills sha256 |
|---|---|---|
| `20260710-053944Z-1a2d2376` | `c32e8f89d75edea25977e56eb4f7dd5267f7932ef4b3196934623a75abaeb27e` | `05d46c7a36d66c78cbe03356caf99e8b5e9772ae0d09c0a68e20e569783f13ef` |
| `20260710-054013Z-b92c0aa3` | `2aaf9bf2ffef5c673c19cf250805126865021e706cf6a70fb862ea153705f569` | `05d46c7a36d66c78cbe03356caf99e8b5e9772ae0d09c0a68e20e569783f13ef` |

Both manifests record `git_dirty=false` and the pre-registration commit.
`compare_backtests` returned `MATCH` for `fills.parquet`, `orders.parquet`,
`positions.parquet`, and `signal_lineage.parquet`. The passive
`alpha.review.v1` output reports clean evidence, reproducibility, long/flat
behavior, and `stop_before_testnet_resume`.

## Next research boundary

Do not optimize EMA lengths, momentum horizon, ATR multiplier, or exit rules
against the opened 2025 blind months under this fingerprint. Any continuation
must start from a materially new economic hypothesis, use a new source/model
version, and lock a genuinely future blind window before inspecting it. Until
then, alpha research is stopped before testnet resume.
