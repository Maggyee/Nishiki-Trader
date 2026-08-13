# 2026-08-13 Protocol v24 Fear and Greed Development Review

- **Status**: development complete; zero confirmation-open eligible candidates.
- **Development window**: 2020-01-01 through 2022-12-31.
- **Confirmation**: sealed.
- **Trading effect**: none.

Two clean Nautilus cash replays per provider-qualified candidate were produced
from commit `7127677`. Each pair has identical fills, zero shorts, no effective
blockers, and no event in the 30 verified no-kline hours.

| Candidate | Gross | Base | Stress | Positive years | Positive months | Positions | Leave-best base | Decision |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| Extreme Fear hold | -5.848030 | -9.876116 | -10.883138 | 1/3 | 8/36 | 47 | -15.990349 | reject |
| Fear hold | -26.247850 | -28.166744 | -28.646468 | 1/3 | 10/36 | 30 | -34.315567 | reject |
| Non-greed hold | -27.940480 | -29.504746 | -29.895812 | 2/3 | 10/36 | 24 | -34.650504 | reject |

All three identities fail frozen cost and breadth gates. Non-greed also has
only 24 closed positions. None may be retuned, given numeric cutoffs,
sign-flipped, ensembled, or confirmed. The 2023-2025 Fear and Greed range and
the shared future blind remain sealed. Existing paper-shadow policies are
unchanged.
