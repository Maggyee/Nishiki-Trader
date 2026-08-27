# Retro: Protocol v52 — Cross-Sectional Long/Short States (B3) Development Rejection

- **Date**: 2026-08-27
- **Outcome**: `development_rejected` under Gates v2 — all three identities
  permanently closed, confirmation never opened, confirmation data never
  fetched (the staged fetch boundary held).
- **Evidence**: `docs/progress/phase-2-research-v52-provider-qualification.json`,
  `docs/progress/phase-2-research-v52-development-results.json`.

## 1. What ran

First two-sided, multi-asset protocol. All 22 pool symbols passed archive
coverage (universe = 22, zero exclusions — including XMRUSDT through
2022-12). Dollar-neutral weekly top-3/bottom-3 books, 100 USDT legs, 156
rebalances over 2020-2022, duplicate replays reproducible, rank-permutation
null with 20,000 trials. BTC buy-and-hold on the same 100-USDT basis:
+129.73 USDT.

## 2. Results

| Candidate | Base | Stress | Months+ | Years+ | Legs | Leave-best | p (perm) | Verdict |
|---|---|---|---|---|---|---|---|---|
| `xs_mom_30d` | **+426.71** | +400.97 | **17/36** | 2/3 | 429 | **+226.36** | **0.0556** | failed months_breadth ONLY |
| `xs_rev_7d` | −739.10 | −785.36 | 17/36 | 0/3 | 771 | −811.06 | 0.919 | failed 7 gates |
| `xs_lowvol_30d` | −492.89 | −507.89 | 19/36 | 2/3 | 250 | −648.10 | 0.778 | failed 5 gates |

7-day reversal and 30-day low-volatility are decisively negative after
costs — both mechanisms rejected on the merits. Cross-sectional 30d momentum
is the strongest signal measured since Gates v2 exist: +426.71 USDT on a
600-USDT gross book over three years, robust to stress costs, leave-best
+226.36 across 429 leg episodes, dollar-neutral (benchmark floor ≈ 0), and
distinguishable from random ranking at p = 0.0556. It failed exactly one
gate: 17/36 positive months versus the ≥18 breadth floor — the same margin
that rejected VXD (v19) and VIX1Y (v35), so the precedent is applied
consistently and the rejection stands. No retuning, no lookback/k search,
no ensemble; identities dead.

## 3. Second gate-design observation (prospective only)

v51 showed the 50% monthly-breadth gate is structurally unreachable for
episodic low-exposure rules. v52 now shows it also binds against continuous
dollar-neutral books whose monthly PnL is right-skewed (momentum's hit rate
sits naturally below 50% while the tail carries the PnL). Two independent
protocol outcomes point at the same design flaw: the fixed 18/36 rule
implicitly assumes a symmetric, always-in-market monthly distribution.

A principled, class-adaptive fix is drafted as **ADR-014 §11 (Draft)**:
replace the fixed floor with "monthly breadth must exceed the median monthly
breadth of the protocol's own null distribution" — the permutation/timing
null already computed for the p-value gate, which self-calibrates per
strategy class and cannot be reverse-engineered from any single candidate.
The draft is NOT in force: it requires explicit operator acceptance, applies
only to protocols frozen after acceptance, and may not resurrect the dead
v51/v52 identities — a re-test of cross-sectional momentum (or negative
funding) would need a new pre-registered identity under the amended gates.

## 4. Boundaries honored

Confirmation months never fetched; no SignalEvent writes; no SourcePolicy
changes; sealed protocols and the 2026-09..2027-01 future blind untouched;
the ten `paper_shadow` survivors and their collectors unchanged. Known v52
limitations as frozen: survivorship-biased universe, no short-leg
funding/borrow drag (both recorded in the contract before data access).
