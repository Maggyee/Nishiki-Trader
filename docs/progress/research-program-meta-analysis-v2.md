# Research Program Meta-Analysis v1 (ADR-014 §5)

- **Schema**: `research.meta_analysis.v2`
- **Registry**: `docs/progress/research-mechanism-family-registry.json` (as of 2026-08-27)
- **Closes**: `data/meta/btcusdt-1d-closes-2020-2025.csv` (rows=2192, sha256=ad1dd81d4f6e174c…)
- **Windows**: development 2020-01-01..2022-12-31, confirmation 2023-01-01..2025-12-31; future blind untouched.

## 1. Buy-and-hold benchmark (trade size 0.001 BTC)

| Window | B&H PnL (USDT) | Positive months | Positive years |
|---|---|---|---|
| Development 2020-2022 | +9.34 | 18/36 | 2/3 |
| Confirmation 2023-2025 | +71.03 | 23/36 | 2/3 |

The historical `>=18/36 positive months` gate should be read against the
B&H month-positive rate above: a long/flat rule can meet it while doing
nothing beyond holding beta part-time (warning W1/W4).

## 2. Survivors vs benchmark (confirmation window)

| Model | Base PnL | Capture vs B&H | Months+ | Breadth p vs B&H | Positions |
|---|---|---|---|---|---|
| `cboe-cor1m-diff5-negative-lag1d-v1` | +29.74 | 41.86% | 18/36 | 0.970 | 78 |
| `cboe-fvx-diff5-negative-lag1d-v1` | +70.71 | 99.54% | 23/36 | 0.575 | 79 |
| `cboe-gvz5obs-negative-1d-v1` | +25.18 | 35.45% | 19/36 | 0.939 | 83 |
| `cboe-vix6m-diff5-negative-lag1d-v1` | +55.51 | 78.15% | 20/36 | 0.887 | 74 |
| `cboe-vpn-diff5-positive-lag1d-v1` | +57.46 | 80.90% | 19/36 | 0.939 | 65 |
| `cboe-vxn-diff5-negative-lag1d-v1` | +60.21 | 84.76% | 20/36 | 0.887 | 72 |
| `cboe-vxn-ohlc5obs-negative-1d-v1` | +60.21 | 84.76% | 20/36 | 0.887 | 72 |
| `crypto-btc-basis-below-ma10-lag1d-v1` | +27.71 | 39.01% | 20/36 | 0.887 | 209 |
| `crypto-btc-prem-diff5-negative-lag1d-v1` | +13.68 | 19.26% | 21/36 | 0.808 | 218 |
| `treasury-nominal10-absdiff5-20-negative-lag2d-v1` | +37.67 | 53.03% | 19/36 | 0.939 | 80 |

## 3. Two-stage random-timing null

- Trials: 20000 (seed 20260827); exposure fraction U[0.2, 0.8], mean hold logU[2.0, 30.0] days;
  costs per fill (bps): {'base': 12.0, 'stress': 15.0}; historical gate set.
- P(pass development gates by luck) = **14.615%**
- P(pass confirmation | passed development) = **50.530%**
- P(pass both stages by luck) = **7.385%**

## 4. Program-level multiplicity

- Current registry PnL-opened identities: **116**
- Historical null cohort through v48: **108**; v49+ excluded.
- Observed two-stage survivors: **10**
- Expected lucky two-stage survivors: **7.98**
- P(observed ≥ 10 by luck alone): **0.2754**

> Historical v1 numbers retained, not recomputed. Current registry totals are separate; v49+ Gates-v2 models are excluded. Legacy membership was not recorded in v1, so only aggregate counts can be cross-checked. This is not a class-matched program significance test. Null assumes independent random long/flat timing per identity on BTCUSDT with survivor-like exposure and holding cadence, evaluated under the historical two-stage gate set. Family correlation between identities makes the effective trial count lower and the null conservative in that direction; selective advancement of the best development sibling makes it anti-conservative. Read as calibration, not as a verdict.

## 5. Boundaries

- No `SignalEvent` written, no `SourcePolicy` change, no live-path impact.
- The 2026-09..2027-01 future blind was not read.
- This report informs the ADR-014 §6 portfolio review; it demotes nothing by itself.
