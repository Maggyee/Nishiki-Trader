# 2026-08-13 Protocol v32 Cboe FX Vol Development Review

- **Status**: development complete; zero confirmation-open eligible candidates.
- **Development window**: 2020-01-01 through 2022-12-31.
- **Confirmation**: sealed.
- **Trading effect**: none.

Two clean Nautilus cash replays of the provider-qualified BPVIX identity were
produced from commit `3bb7163`. The pair has identical fills, zero shorts, no
effective blockers, and no event in the 30 verified no-kline hours.

| Candidate | Gross | Base | Stress | Positive years | Positive months | Positions | Leave-best base | Decision |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| Pound FX vol relief | 5.295400 | 1.457418 | 0.497923 | 1/3 | 11/36 | 41 | -7.836344 | reject |

Unchanged BPVIX five-observation relief is cost-positive but fails year
breadth, monthly breadth, and leave-best. EUVIX and JYVIX remain
provider-rejected. None may be retuned, sign-flipped, ensembled, or
confirmed.

Confirmation values and PnL stay sealed. Existing paper-shadow policies,
SourcePolicy, testnet, live trading, and the future blind are unchanged.
