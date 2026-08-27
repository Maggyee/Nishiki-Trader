# Research Protocol v51 — BTC Funding-Rate Positioning States (v50 provider recovery)

- **Status**: Pre-registered (frozen before any funding value was fetched)
- **Date frozen**: 2026-08-27
- **Recovers**: Protocol v50, closed at `blocked_provider_qualification`
  because its frozen 2019-12 development start month does not exist in the
  provider archive (evidence:
  `docs/progress/phase-2-research-v50-provider-qualification.json`). Rules,
  thresholds, windows, gates, and costs are UNCHANGED from v50; only the
  data-contract months (2020-01..2022-12 development fetch), the settlement
  count floor (3300 → 3200, matching the shorter warmup), and the identities
  are new — the v17 → v18 recovery pattern.
- **Mechanism family**: `crypto_derivatives_structure` (open)
- **Identities**:
  - `rule_crypto_funding_negative_v2 / crypto-btc-funding-sum72h-negative-v2`
  - `rule_crypto_funding_below_baseline_v2 / crypto-btc-funding-mean72h-below-1bp8h-v2`
  - `rule_crypto_funding_overheat_flat_v2 / crypto-btc-funding-mean72h-overheat5bp8h-flat-v2`
- **Contract**: `apps/ops/research_protocol_v51.py`
- **Pipeline**: `apps/ops/research_v51_funding.py`, a thin binding of the
  shared harness `apps/ops/research_funding_states.py` (ADR-014 §6.4:
  parameterized harness instead of per-protocol file copies)
- **Gates**: Gates v2 per ADR-014 §4 (same table as v50: both 36-month
  windows, ≥18/36 breadth, base/stress > 0, ≥2/3 years, ≥60 positions,
  leave-best > 0, base > exposure×B&H, bootstrap p ≤ 0.10 with 20,000 trials
  seed 20260827, two duplicate replays)

Hypothesis, orthogonality/non-duplication declarations, directional
declaration, weekend coverage, frozen rules, staged fetch boundary
(confirmation months 2023-01..2025-12 may not be fetched before a
development pass), data-quality gates, and the single-best-candidate advance
rule are as stated in `docs/progress/phase-2-research-protocol-v50.md` §1–§5
and frozen verbatim in the v51 contract module. The first three days of
January 2020 fall under the frozen fail-safe (fewer than 6 settlements in the
trailing 72h forces flat), so the corrected start month does not alter any
rule's semantics.

Stage outputs land in
`docs/progress/phase-2-research-v51-{provider-qualification,development-results,confirmation-results}.json`.
Development failures close their identities permanently; a confirmation
failure closes the advanced identity permanently. The 2026-09..2027-01 future
blind stays sealed.
