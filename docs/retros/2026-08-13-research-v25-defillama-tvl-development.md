# 2026-08-13 Protocol v25 DefiLlama TVL Development Review

- **Status**: development complete; one confirmation-open eligible candidate.
- **Development window**: 2020-01-01 through 2022-12-31.
- **Confirmation**: sealed until a separate contract is frozen.
- **Trading effect**: none.

Two clean Nautilus cash replays per provider-qualified candidate were produced
from commit `e4b22c0`. Each pair has identical fills, zero shorts, no effective
blockers, and no event in the 30 verified no-kline hours. Bitcoin-chain TVL
remains provider-rejected and was not replayed.

| Candidate | Gross | Base | Stress | Positive years | Positive months | Positions | Leave-best base | Decision |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| All-chain TVL expansion | 30.655530 | 24.445097 | 22.892488 | 2/3 | 19/36 | 94 | 9.220236 | pass |
| Ethereum TVL expansion | 13.417560 | 5.876019 | 3.990634 | 2/3 | 15/36 | 110 | -12.057323 | reject |

Ethereum TVL expansion fails monthly breadth and leave-best concentration. It
must not be retuned, sign-flipped, ensembled, or confirmed.

All-chain TVL expansion passes every frozen development gate. It may enter
only a separately frozen 2023-2025 confirmation contract that reuses the
already-captured all-chain snapshot without a new GET. Confirmation values
and PnL remain sealed until that contract is committed. Existing paper-shadow
policies, SourcePolicy, testnet, live trading, and the future blind are
unchanged.
