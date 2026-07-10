# Pullback-Regime Opened-Data Development Rejection

- **Date**: 2026-07-10
- **Source/model**: `rule_pullback_regime_v1 / daily50-200-1h24-pullback-giveback1.25-v1`
- **Pre-registration commit**: `864bf44`
- **Decision**: Close fingerprint before unseen validation
- **Recommendation**: `stop_before_testnet_resume`
- **Policy effect**: None

## Decision

Reject the candidate on opened development data and preserve every unseen 2026
bar. Both pre-registered five-month folds failed the cost and monthly gates;
the 2024 fold was negative before costs, while the small positive 2025 gross
result was overwhelmed by realistic costs.

Do not adjust the daily regime, pullback, ATR, giveback, or timeout parameters
under this model version. Do not import the locked 2026-01..05 validation or
consume the 2026-08..12 future blind window for this fingerprint.

## Scientific sequence

The complete rule, source/model identity, two opened-data folds, unseen
validation, future blind window, and concentration gate were committed and
pushed before the full catalog signal stream was generated. Only synthetic
data was used before commit `864bf44`; no 2026 market data was imported or
read.

After the commit, the fixed generator produced 518 signals from the already
opened 2024-2025 catalog. No parameter search or rerun with altered rules was
performed.

## Gate results

| fold | signals | positions | gross | base | stress | base-positive months | base without best | result |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| 2024-08..12 | 146 | 73 | -4.254450 | -18.521015 | -22.087657 | 0/5 | -23.465132 | fail |
| 2025-08..12 | 128 | 64 | +2.517530 | -15.022640 | -19.407682 | 1/5 | -19.843135 | fail |

Both folds passed only the mechanical gates: at least 30 positions, zero
shorts, clean evidence, and exact reproducibility. Both failed base, stress,
positive-month, and leave-best-position-out gates. The 2024 fold also failed
gross profitability.

Monthly net PnL:

| month | gross | base | stress |
|---|---:|---:|---:|
| 2024-08 | -1.940800 | -2.692447 | -2.880358 |
| 2024-09 | +0.363820 | -0.409926 | -0.603362 |
| 2024-10 | -2.369970 | -5.357228 | -6.104042 |
| 2024-11 | +1.354491 | -3.358010 | -4.536136 |
| 2024-12 | -1.661991 | -6.703405 | -7.963758 |
| 2025-08 | -2.038190 | -8.343477 | -9.919799 |
| 2025-09 | +0.060285 | -6.035006 | -7.558828 |
| 2025-10 | +5.279005 | +0.403770 | -0.815038 |
| 2025-11 | -0.783570 | -1.047927 | -1.114017 |
| 2025-12 | 0.000000 | 0.000000 | 0.000000 |

## Behavioral reading

The higher-timeframe permission avoided all December 2025 trading, but the
hourly pullback/recovery rule still turned over too quickly:

| fold | entries | structural exits | bounded-giveback exits | daily-risk-off exits | timeout exits |
|---|---:|---:|---:|---:|---:|
| 2024-08..12 | 73 | 37 | 35 | 1 | 0 |
| 2025-08..12 | 64 | 33 | 30 | 1 | 0 |

The 72h timeout never became the active exit. Almost every position closed by
structural failure or giveback before then. The candidate therefore solved the
previous slow-exit problem by creating much higher turnover, but it did not
create sufficient per-trade gross edge to pay a 24 bps modeled round trip.
This reproduces the broader research boundary: reducing giveback alone cannot
rescue an entry process whose continuation edge is too small.

## Evidence identity

| fold/run | manifest sha256 | fills sha256 |
|---|---|---|
| 2024 `20260710-111509Z-84c9d086` | `60d90815d7e787b30f1b3e23209eb34653398f86ccb4c486b6c60523e5b5ffae` | `2fb8fda7d4d5f1c099b9710cba5ab0a331b53b67c888868d3f220c8dbf149602` |
| 2024 `20260710-111509Z-9ecd816f` | `bcd0a2c4ca1050746aa775eeb3e436d30236d966fd1c08d5fd65b4cde2eff39c` | `2fb8fda7d4d5f1c099b9710cba5ab0a331b53b67c888868d3f220c8dbf149602` |
| 2025 `20260710-111547Z-812ba3eb` | `f2316b5345b04676eab39a085cef1007d94b58d94795f9f5e25e50aba91ad8e7` | `dfcd02292f578d0bfe6fad77328a3df6fb14138a26e9db6f7d8e1c660e2a78eb` |
| 2025 `20260710-111547Z-f3b8a1a6` | `d53963eb7feaaec113a3bd51d26ab5724ec8aecbe8a723573c62780fe74c7528` | `dfcd02292f578d0bfe6fad77328a3df6fb14138a26e9db6f7d8e1c660e2a78eb` |

`compare_backtests` returned `MATCH` for fills, orders, positions, and signal
lineage in both fold pairs. Both `alpha.review.v1` artifacts report clean,
reproducible, Spot-only evidence and `stop_before_testnet_resume`.

## Next boundary

Three nearby single-asset technical structures have now failed for distinct
but related reasons: high-turnover breakout lacked gross edge, slow trend
following was regime-dependent, and pullback continuation traded more often
without enough per-trade edge. Do not immediately create another threshold
variant from the same BTC-only indicator family.

The next decision should be a research-scope review: either broaden the
economic premise and data universe, or pause alpha implementation while the
locked future data accumulates. Testnet continuity and live work remain
stopped.
