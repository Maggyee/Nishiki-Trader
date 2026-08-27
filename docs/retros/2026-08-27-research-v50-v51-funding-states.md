# Retro: Protocols v50/v51 — BTC Funding-Rate Positioning States (B2)

- **Date**: 2026-08-27
- **Outcome**: v50 closed at `blocked_provider_qualification` (zero values
  opened); its recovery v51 closed at `development_rejected` under Gates v2.
  All six identities are permanently dead. Backlog B2 is resolved for these
  rule shapes; the next open backlog step is **B3 cross-sectional relative
  value**.
- **Evidence**: `docs/progress/phase-2-research-v50-provider-qualification.json`,
  `docs/progress/phase-2-research-v51-provider-qualification.json`,
  `docs/progress/phase-2-research-v51-development-results.json`.

## 1. v50 provider closure and the v51 recovery

v50 froze a development fetch range starting 2019-12; the Binance Vision
USD-M `fundingRate` archive for BTCUSDT starts at 2020-01, so the very first
GET returned HTTP 404 before any archive or value landed (zero files on
disk; existence-probe HTTP codes recorded in the qualification JSON). Per
the v17 → v18 precedent, v51 re-registered the UNCHANGED rules under `_v2`
identities with development months corrected to 2020-01..2022-12. The
pipeline was consolidated into the contract-parameterized shared harness
`apps/ops/research_funding_states.py` (ADR-014 §6.4), replacing per-protocol
file copies.

## 2. v51 development results (2020-2022, 36 months; B&H +9.34 USDT, 18/36 months)

| Candidate | Base | Stress | Months+ | Years+ | Positions | Leave-best | Exposure | p | Failed gates |
|---|---|---|---|---|---|---|---|---|---|
| `fund_neg_3d` | **+16.68** | +16.24 | 13/36 | **3/3** | 31 | **+6.54** | 12.1% | **0.096** | activity_floor (31<60), months_breadth (13<18) |
| `fund_below_baseline_3d` | −1.10 | −1.48 | 19/36 | 2/3 | 21 | −13.36 | 60.9% | 0.601 | six gates incl. base/stress/bootstrap |
| `fund_overheat_flat_3d` | +6.55 | +6.19 | 18/36 | 2/3 | 18 | −5.13 | 91.1% | 0.517 | benchmark, bootstrap, leave-best, activity |

Duplicate replays reproduced for all three. No development passer →
confirmation was never opened; the 2023-2025 funding archives were never
fetched (the staged fetch boundary held).

## 3. Interpretation

- The below-baseline and overheat-flat states carry no edge: both are
  exposure-heavy states that lose to their exposure-matched benchmark and to
  random timing.
- `fund_neg_3d` (contrarian long when trailing 72h funding is net negative)
  is the strongest raw signal any Gates-v2 candidate has shown: positive all
  three years, leave-best robust, 15× its exposure-matched benchmark floor,
  bootstrap p = 0.096 — and it still failed, on the activity floor and
  monthly breadth. Under program multiplicity (~115 PnL-opened identities),
  one p≈0.10 result is unremarkable; the rejection stands and the identities
  stay dead.

## 4. Gate-design observation (prospective only — NOT a reopening)

The `months_breadth ≥ 50%` and `positions ≥ 60/window` gates were designed
for always-in-market-ish relief rules. For an episodic low-exposure
mechanism (12% time in market, ~10 episodes/year), months without exposure
have ≈0 PnL and can never count positive, so the breadth gate is
structurally unreachable regardless of edge quality. This is a real blind
spot in Gates v2 for the episodic strategy class.

Governance for any follow-up (warnings W2/W3 apply in full):

- Any gate change must be a **prospective ADR-014 amendment** (e.g., breadth
  measured over exposure months with a minimum episode count), motivated in
  writing, applying only to protocols frozen AFTER the amendment.
- A future study of the negative-funding mechanism requires BOTH that
  amendment and a genuinely new pre-registered identity. v51's dead
  identities, thresholds, and windows may not be resurrected, and this
  retro's numbers may not be used to tune the successor's thresholds beyond
  the frozen structural constants already public in the v50/v51 contracts.

## 5. Boundaries honored

Zero v50 data access; v51 confirmation data never fetched; no SignalEvent
writes; no SourcePolicy changes; sealed protocols and the 2026-09..2027-01
future blind untouched; the ten `paper_shadow` survivors and their
collectors unchanged.
