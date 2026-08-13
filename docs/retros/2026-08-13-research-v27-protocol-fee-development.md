# 2026-08-13 Protocol v27 DefiLlama Protocol-Fee Development Review

- **Status**: development complete; zero confirmation-open eligible candidates.
- **Development window**: 2020-01-01 through 2022-12-31.
- **Confirmation**: sealed.
- **Trading effect**: none.

Two clean Nautilus cash replays per provider-qualified candidate were produced
from commit `66a725e`. Each pair has identical fills, zero shorts, no effective
blockers, and no event in the 30 verified no-kline hours.

| Candidate | Gross | Base | Stress | Positive years | Positive months | Positions | Leave-best base | Decision |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| All-chain fees expansion | 21.073880 | 9.206059 | 6.239104 | 2/3 | 19/36 | 171 | -1.639513 | reject |
| All-chain revenue expansion | 9.004960 | -1.892960 | -4.617440 | 2/3 | 18/36 | 163 | -14.005060 | reject |
| All-chain holder-revenue expansion | 11.725780 | -1.939506 | -5.355827 | 2/3 | 14/36 | 160 | -9.864195 | reject |

All-chain fees expansion is cost-positive and meets breadth, but fails
leave-best concentration. Revenue fails base/stress and leave-best.
Holder-revenue also fails monthly breadth at 14/36. None may be retuned,
sign-flipped, ensembled, or confirmed.

Confirmation values and PnL stay sealed. Existing paper-shadow policies,
SourcePolicy, testnet, live trading, and the future blind are unchanged.
