# 2026-08-12 Protocol v16 Treasury-Rates Development Review

- **Status**: complete; one development passer.
- **Development window**: 2020-01-01 through 2022-12-31.
- **Confirmation window**: sealed pending committed development review.
- **Future blind**: sealed.
- **Trading effect**: none.

## Data

Eight official U.S. Treasury annual nominal/real CSVs produced 791 numeric
joint observations with no fill and no gap above four calendar days. The
immutable snapshot is `sha256:5b281c2c…49ac`; observations are delayed D+2.

## Results

| Candidate | Signals | Gross | Base | Stress | Positive years | Positive months | Positions | Leave-best base | Decision |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| Real-yield relief | 50 | +24.836540 | +23.053854 | +22.608183 | 3/3 | 14/36 | 25 | +3.223758 | insufficient evidence |
| Yield-curve steepening | 47 | +47.360090 | +45.902945 | +45.538659 | 2/3 | 7/36 | 24 | +5.029640 | insufficient evidence |
| Treasury-yield volatility relief | 151 | +60.770130 | +55.211116 | +53.821362 | 2/3 | 20/36 | 76 | +35.236938 | development pass |

All pairs reproduce with identical fills, zero shorts, zero effective blockers,
and zero verified no-kline event hits.

Real-yield relief is positive in every year and robust to removing its best
position, but 25 positions and 14 positive months do not establish sufficient
breadth. Curve steepening is highly profitable but concentrated in 2021, with
only 24 positions and seven positive months. Both remain insufficient evidence.

Treasury-yield volatility relief clears every frozen development gate. The
rule holds BTC when the five-observation mean absolute daily change in the
10-year nominal Treasury yield is below its twenty-observation mean. It has 76
positions, 20 positive months, positive base/stress PnL, and remains strongly
positive after its best position is removed.

## Decision

Commit this review before opening confirmation. Only the unchanged
`rule_us_treasury_volatility_relief_v2 / treasury-nominal10-absdiff5-20-negative-lag2d-v1`
identity may open 2023-2025. No parameter, sign, ensemble, SourcePolicy, or
trading-path change is authorized by development alone.
