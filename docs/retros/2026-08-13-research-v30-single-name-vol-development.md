# 2026-08-13 Protocol v30 Cboe Single-Name Vol Development Review

- **Status**: development complete; one confirmation-open eligible candidate.
- **Development window**: 2020-01-01 through 2022-12-31.
- **Confirmation**: sealed until a separately frozen contract.
- **Trading effect**: none.

Two clean Nautilus cash replays per provider-qualified candidate were produced
from commit `b2c85b2`. Each pair has identical fills, zero shorts, no effective
blockers, and no event in the 30 verified no-kline hours.

| Candidate | Gross | Base | Stress | Positive years | Positive months | Positions | Leave-best base | Decision |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| Apple vol relief | 22.628050 | 16.647100 | 15.151863 | 2/3 | 18/36 | 83 | -0.998831 | reject |
| Amazon vol relief | 28.190890 | 22.557444 | 21.149082 | 2/3 | 14/36 | 77 | 6.531217 | reject |
| Google vol relief | 21.529860 | 15.307939 | 13.752459 | 2/3 | 24/36 | 87 | 4.083723 | pass |

Unchanged Google/Alphabet five-observation VXGOG relief is the only identity
that may enter a separately frozen 2023-2025 confirmation contract. Apple and
Amazon may not be retuned, sign-flipped, ensembled, or confirmed.

Existing paper-shadow policies, SourcePolicy, testnet, live trading, and the
future blind are unchanged.
