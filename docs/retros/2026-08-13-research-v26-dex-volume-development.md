# 2026-08-13 Protocol v26 DefiLlama DEX Volume Development Review

- **Status**: development complete; zero confirmation-open eligible candidates.
- **Development window**: 2020-01-01 through 2022-12-31.
- **Confirmation**: sealed.
- **Trading effect**: none.

Two clean Nautilus cash replays per provider-qualified candidate were produced
from commit `8abaffb`. Each pair has identical fills, zero shorts, no effective
blockers, and no event in the 30 verified no-kline hours. Solana DEX volume
remains provider-rejected and was not replayed.

| Candidate | Gross | Base | Stress | Positive years | Positive months | Positions | Leave-best base | Decision |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| All-DEX volume expansion | 7.814730 | -6.320471 | -9.854272 | 2/3 | 20/36 | 195 | -14.245160 | reject |
| Ethereum DEX volume expansion | 12.396670 | -2.029904 | -5.636548 | 2/3 | 20/36 | 199 | -9.954593 | reject |

Both identities are gross-positive and meet monthly breadth, but fail frozen
base/stress cost gates and leave-best concentration. Neither may be retuned,
sign-flipped, ensembled, or confirmed.

Solana remains provider-rejected. Confirmation values and PnL stay sealed.
Existing paper-shadow policies, SourcePolicy, testnet, live trading, and the
future blind are unchanged.
