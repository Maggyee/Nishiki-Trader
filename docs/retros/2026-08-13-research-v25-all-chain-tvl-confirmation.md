# 2026-08-13 Protocol v25 All-Chain TVL Confirmation Review

- **Status**: confirmation failed; protocol closed.
- **Identity**: `rule_defillama_all_chains_tvl_expansion_v1 / defillama-all-chains-tvl-diff5-positive-lag2d-v1`.
- **Confirmation window**: 2023-01-01 through 2025-12-31.
- **Future blind**: sealed.
- **Trading effect**: none.

## Evidence

The confirmation contract was on `origin/main` at `318ea88` / `0bb16d3` before
holdout value extraction. The factor was taken from the already-captured
all-chain snapshot with no new GET, no fill, no interpolation, and no
historical-vintage claim. Coverage is 1,096 unfilled confirmation days, 61
warmup rows, a one-day maximum gap, and 225 later rows counted and ignored.

Two clean cash-account Nautilus replays from `0bb16d3` consume the same 229
signals and close 115 long-only positions. Fills match. There are zero
effective blockers, shorts, or events in the verified exchange-unavailable
hour.

## Result

| Gross | Base | Stress | Positive years | Positive months | Positions | Leave-best base |
|---:|---:|---:|---:|---:|---:|---:|
| +27.949010 | +9.738210 | +5.185511 | 2/3 | 14/36 | 115 | -12.753346 |

Annual base PnL is +12.177331 / +26.995276 / -29.434397 USDT for
2023/2024/2025. Monthly breadth fails at 14/36 versus 18 required, and
leave-best base PnL is negative.

## Decision

The unchanged identity is rejected. It cannot enter ADR-007 or `paper_shadow`.
Do not retune, sign-flip, or ensemble it, reopen Ethereum/Bitcoin TVL, or open
the future blind. Existing paper-shadow policies, SourcePolicy, testnet, and
live trading are unchanged.
