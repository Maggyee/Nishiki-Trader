# 2026-08-13 Protocol v22 Option-Surface Development Review

- **Status**: development complete; COR1M relief is confirmation-open eligible.
- **Development window**: 2020-01-01 through 2022-12-31.
- **Confirmation**: sealed pending a separate committed contract.
- **Trading effect**: none.

Two clean Nautilus cash replays per provider-qualified candidate were produced
from commit `1861726` after the zero-PnL catalog correction was committed.
Each pair has identical fills, zero shorts, no effective blockers, and no event
in the 30 verified no-kline hours. DSPX remains provider-rejected without PnL.

| Candidate | Gross | Base | Stress | Positive years | Positive months | Positions | Leave-best base | Decision |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| SKEW relief | -21.720930 | -27.462310 | -28.897655 | 2/3 | 18/36 | 85 | -41.955474 | reject |
| COR1M relief | +19.959630 | +14.196850 | +12.756155 | 2/3 | 23/36 | 86 | +0.856160 | development pass |

SKEW relief fails base/stress cost and concentration gates and cannot be
retuned or confirmed. Unchanged COR1M relief passes every frozen gate, but its
leave-best margin is thin and 2022 base PnL is -5.849322 USDT. It may open only
a separately frozen 2023-2025 confirmation; it has no ADR-007 or
`paper_shadow` eligibility yet.
