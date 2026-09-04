# Research Protocol v53 — Cross-Sectional Momentum Re-Test (first ADR-014 §11 protocol)

- **Status**: Pre-registered (frozen before any price value was opened for evaluation)
- **Date frozen**: 2026-08-28
- **Basis**: ADR-014 §11 class-adaptive breadth gate, **Accepted 2026-08-28 by
  explicit operator directive** ("接受 §11"). This is the first protocol frozen
  under it.
- **Mechanism family**: `cross_sectional_relative`
- **Identity**: `rule_crypto_xs_momentum_ls_v2 / crypto-xs-mom30d-top3-bottom3-weekly-v2`
  (new identity as §11 requires; the dead v52 identity is not resurrected)
- **Contract**: `apps/ops/research_protocol_v53.py`; **pipeline**:
  `apps/ops/research_v53_xs.py` binding the shared harness
  `apps/ops/research_xs_portfolio.py`

## 1. Conditional re-test disclosure (recorded before freezing)

Protocol v52 already opened this rule's 2020-2022 development data; its
development numbers (+426.71 USDT base, 429 legs, leave-best +226.36,
permutation p = 0.0556, 17/36 positive months) are known in advance and carry
no new evidentiary weight here. The only genuinely new development-stage
information is whether 17 positive months **exceeds the null distribution's
median breadth** — computed for the first time under this protocol. The real
evidentiary weight rests on the **2023-2025 confirmation window, whose
archives were never fetched by v52** (the staged fetch boundary held) and
which remains a true out-of-sample test. A development pass here is a
gate-recalibration outcome, not new alpha evidence; reviewers must weight the
confirmation result only.

## 2. What is identical to v52 (frozen verbatim)

Pool (22 pairs), mechanical universe and delisting rules (min 12,
force-close at last available close, flat fail-safe), construction (k=3 per
side, equal weight, 100 USDT legs, weekly Monday-close rebalance, 30d
lookback), costs (0/12/15 bps per leg fill), windows (dev 2020-2022, conf
2023-2025), staged fetch boundary, permutation null (20,000 trials, seed
20260827), and every other Gates v2 threshold. **No lookback search, no k
search, no threshold changes.** The v52 reversal and low-vol mechanisms are
NOT re-registered — they failed on the merits.

## 3. The §11 gate as applied

`positive_months > median(positive_months under the rank-permutation null)`,
with the identical calendar/universe/legs/costs. The fixed 18/36 floor stays
in every stage output as the reporting reference. All other gates unchanged:
base/stress > 0, ≥2/3 years, ≥60 closed leg positions, leave-best > 0,
benchmark floor = net exposure × 100-USDT BTC B&H, permutation p ≤ 0.10, two
duplicate replays. Single candidate: development pass opens confirmation;
any failure closes the identity permanently.

## 4. Boundaries

No `SignalEvent` writes, no `SourcePolicy` changes, no sealed-protocol
reopening, no future-blind access (data ends 2025-12-31), no live-path
impact. Known limitations carried over and recorded: survivorship-biased
universe; no short-leg funding/borrow drag. Stage outputs land in
`docs/progress/phase-2-research-v53-{provider-qualification,development-results,confirmation-results}.json`.
