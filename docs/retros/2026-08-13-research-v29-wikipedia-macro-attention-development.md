# 2026-08-13 Protocol v29 Wikipedia Macro-Attention Development Review

- **Status**: development complete; zero confirmation-open eligible candidates.
- **Development window**: 2020-01-01 through 2022-12-31.
- **Confirmation**: sealed.
- **Trading effect**: none.

Two clean Nautilus cash replays per provider-qualified candidate were produced
from commit `a19c207`. Each pair has identical fills, zero shorts, no effective
blockers, and no event in the 30 verified no-kline hours.

| Candidate | Gross | Base | Stress | Positive years | Positive months | Positions | Leave-best base | Decision |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| Fed attention relief | 6.255360 | -5.226623 | -8.097119 | 1/3 | 18/36 | 162 | -16.838198 | reject |
| Inflation attention relief | -6.054170 | -17.588427 | -20.471992 | 1/3 | 16/36 | 172 | -25.278376 | reject |
| Recession attention relief | 23.473160 | 11.952139 | 9.071884 | 1/3 | 23/36 | 167 | 4.615017 | reject |

Recession attention relief is cost-positive, meets monthly breadth and
leave-best, but fails the two-positive-year gate (2020 carries the PnL). Fed
and Inflation fail after costs. None may be retuned, sign-flipped, article-
substituted, ensembled, or confirmed.

Confirmation values and PnL stay sealed. Existing paper-shadow policies,
SourcePolicy, testnet, live trading, and the future blind are unchanged.
