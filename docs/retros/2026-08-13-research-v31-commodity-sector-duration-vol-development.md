# 2026-08-13 Protocol v31 Cboe Commodity/Sector/Duration Vol Development Review

- **Status**: development complete; zero confirmation-open eligible candidates.
- **Development window**: 2020-01-01 through 2022-12-31.
- **Confirmation**: sealed.
- **Trading effect**: none.

Two clean Nautilus cash replays of the provider-qualified VXTLT identity were
produced from commit `d5eeb39`. The pair has identical fills, zero shorts, no
effective blockers, and no event in the 30 verified no-kline hours.

| Candidate | Gross | Base | Stress | Positive years | Positive months | Positions | Leave-best base | Decision |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| Long-Treasury ETF vol relief | -1.485800 | -7.758932 | -9.327215 | 1/3 | 20/36 | 89 | -15.814085 | reject |

Unchanged VXTLT five-observation relief is rejected on cost sign, year
breadth, and leave-best. VXSLV and VXXLE remain provider-rejected. None may
be retuned, sign-flipped, ensembled, or confirmed.

Confirmation values and PnL stay sealed. Existing paper-shadow policies,
SourcePolicy, testnet, live trading, and the future blind are unchanged.
