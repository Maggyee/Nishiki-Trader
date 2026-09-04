# Retro: Protocol v53 — Cross-Sectional Momentum Re-Test under ADR-014 §11

- **Date**: 2026-08-28
- **Context**: ADR-014 §11 (class-adaptive breadth gate) was Accepted by
  explicit operator directive this day; v53 is its first application — the
  unchanged v52 30d cross-sectional momentum rule under the new identity
  `rule_crypto_xs_momentum_ls_v2 / crypto-xs-mom30d-top3-bottom3-weekly-v2`.
- **Outcome**: development passed under the adaptive gate; **confirmation on
  the never-before-fetched 2023-2025 window REJECTED the mechanism**
  (`confirmation_rejected`). The identity is permanently closed. The
  cross-sectional momentum thread is now resolved on the merits, on pristine
  out-of-sample data.
- **Evidence**: `docs/progress/phase-2-research-v53-provider-qualification.json`,
  `docs/progress/phase-2-research-v53-development-results.json`,
  `docs/progress/phase-2-research-v53-confirmation-results.json`.

## 1. What ran

Frozen at `eff4335` with a conditional re-test disclosure (v52's development
numbers were known in advance; evidentiary weight assigned to confirmation
only). Qualification re-verified all 22 pool symbols (universe 22/22).
Development reproduced the known numbers and applied the §11 gate for the
first time: 17/36 positive months vs a null-median breadth of 16.0 → passed
(the fixed 18/36 floor would still have failed it, exactly the §11 point),
permutation p = 0.0556, all other gates green → confirmation opened.

The confirmation fetch was the first access ever to the 2023-2025 archives
for this construction (v52's staged boundary had held). XMRUSDT truncated at
its 2024 delisting and was force-closed per the frozen delisting rule.

## 2. The confirmation verdict (2023-01-01..2025-12-31, 36 months)

| Metric | Development (2020-2022) | Confirmation (2023-2025) |
|---|---|---|
| Gross / base / stress | — / **+426.71** / +400.97 | +138.49 / **+42.25** / +18.19 |
| Positive months vs null median | 17/36 vs 16.0 → pass | 18/36 vs 15.0 → pass |
| Positive years | 2/3 | 2/3 |
| Closed leg positions | 429 | 401 |
| **Leave-best leg** | +226.36 | **−226.35 → FAIL** |
| **Permutation p** | 0.0556 | **0.1695 → FAIL** |
| BTC B&H (100 USDT basis) | +129.73 | +427.47 |

The out-of-sample story is unambiguous: the edge shrank tenfold, the
remaining +42.25 rides entirely on one leg episode (remove it and the book
loses 226), and the ranking is statistically indistinguishable from random
(p = 0.17). A single 100-USDT buy-and-hold BTC leg earned ten times the
whole neutral book over the same window. Development-period strength was
regime-specific and/or selection luck; the sealed confirmation window did
exactly the job it exists for.

## 3. What this validates

- **The §11 adaptive gate behaved correctly on both sides**: it removed the
  arbitrary fixed-floor rejection (17 > 16 in development; 18 > 15 in
  confirmation — breadth was never the real problem), and the remaining
  skill/concentration gates delivered the verdict. The gate redesign made
  the program *fairer without making it looser*.
- **The staged fetch boundary is the program's most valuable control**: v52
  never touching 2023-2025 is what made this a genuine test.
- The `cross_sectional_relative` family now has a clean merits-based answer
  for its strongest member; the family stays `open` but any future member
  needs a genuinely different construction (not a lookback/k variant of
  this one — warnings W2/W3 apply).

## 4. Closure

- All v53 identities permanently closed; no retuning, no variant search.
- Program tally after v49–v53: 5 protocols, 12 identities under Gates
  v2/v2.1, zero survivors — and zero false promotions. The ten legacy
  `paper_shadow` survivors and their forward collection continue unchanged.
- Remaining open backlog: B5 event/calendar, B6 OI/taker flow, B7 portfolio
  overlay, B8 stablecoin forward (in progress via v12). The negative-funding
  episodic mechanism (v51's fund_neg_3d shape) is now re-testable under §11
  with a new identity, since its blocking gate was breadth — that is the
  natural next protocol if the operator wants one.

## 5. Boundaries honored

Confirmation data fetched only after the development pass; no SignalEvent
writes; no SourcePolicy changes; sealed protocols and the 2026-09..2027-01
future blind untouched; the ten `paper_shadow` survivors unchanged.
