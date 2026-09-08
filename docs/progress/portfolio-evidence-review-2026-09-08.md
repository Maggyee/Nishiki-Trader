# Retained-fill portfolio evaluation — 2026-09-08

Cohort: **partial**, 6/10 candidates verified.
2023–2025, 0.001 BTC per original sleeve, 12/15 bps per-fill base/stress costs.
Not a new backtest, actual account return, optimized portfolio or promotion decision.

| Candidate | Base PnL | Stress PnL | Holding fraction | Base exposure-matched B&H | Base excess | Daily base drawdown |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| v16 | 37.67 | 34.41 | 52.5% | 37.24 | 0.43 | 24.78 |
| v18 | 60.21 | 57.57 | 51.6% | 36.66 | 23.55 | 22.56 |
| v22 | 29.74 | 26.75 | 56.6% | 40.15 | -10.41 | 26.68 |
| v34 | 70.71 | 67.57 | 47.8% | 33.93 | 36.77 | 22.71 |
| v36 | 57.46 | 54.70 | 63.2% | 44.88 | 12.58 | 26.82 |
| v40 | 60.21 | 57.57 | 51.6% | 36.66 | 23.55 | 22.56 |

All monetary values are USDT, not percentage returns.

## Duplicate exposure

Exact execution-path groups: [['v18', 'v40']].
Weights in the JSON are diagnostic accounting weights, not authorized position sizing.

## Basket diagnostics

- raw_fixed_quantity_basket: base 315.99, stress 298.57, daily base drawdown 98.78 USDT.
- duplicate_normalized_diagnostic: base 255.78, stress 241.00, daily base drawdown 80.21 USDT.

## Dependence and marginal contribution

The JSON records full daily PnL correlation and daily holding Jaccard matrices.
The following leave-one-out figures use the raw fixed-quantity basket; removing a sleeve also removes its exposure.

| Candidate | Base PnL contribution | Base drawdown without sleeve | Drawdown increase from sleeve |
| --- | ---: | ---: | ---: |
| v16 | 37.67 | 91.73 | 7.05 |
| v18 | 60.21 | 80.21 | 18.56 |
| v22 | 29.74 | 72.09 | 26.68 |
| v34 | 70.71 | 90.94 | 7.84 |
| v36 | 57.46 | 79.78 | 19.00 |
| v40 | 60.21 | 80.21 | 18.56 |

## Excluded evidence

- v8: ValueError:committed result lacks manifest-and-fills hash references
- v42: ValueError:committed result lacks manifest-and-fills hash references
- v46: ValueError:committed result lacks manifest-and-fills hash references
- v48: ValueError:committed result lacks manifest-and-fills hash references

## Limitations

- partial cohort cannot establish ten-candidate portfolio performance
- verified account equity unavailable; leverage and percentage return are not inferred
- daily marks do not measure intraday drawdown
- exposure matching does not establish statistical significance or match volatility
- no portfolio allocation or promotion is authorized
