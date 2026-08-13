# Phase 2 Research Protocol v20

- **Frozen**: 2026-08-13 before opening the OFR FSI JSON or CSV body.
- **Machine contract**: `docs/progress/phase-2-research-protocol-v20.json`
- **Provider contract**: `docs/progress/phase-2-research-v20-data-sources.json`
- **Status**: provider qualified; development PnL sealed pending committed qualification.
- **Trading effect**: none.

## Independent mechanism

Protocol v20 moves away from another volatility-index underlier. It asks
whether broad financial stress relief, credit stress relief, or reduced
flight-to-safety pressure precedes a BTC risk-on state. The Office of
Financial Research describes its Financial Stress Index as a daily,
market-based measure; the public application exposes the total index and
category series used here.

The mechanism is public financial intuition, not a claim of academic
originality. The exact BTC rules, identities, D+5 lag, gates, and partitions
are project-specific pre-registered hypotheses.

## Locked candidates

All candidates target BTCUSDT Spot, begin flat, and emit only state-changing
`buy`/`flat` events. Buy iff the latest value minus the value five common OFR
observations earlier is strictly negative; otherwise flat.

- `rule_ofr_systemic_stress_relief_v1 / ofr-fsi-total-diff5-negative-lag5d-v1`
- `rule_ofr_credit_stress_relief_v1 / ofr-fsi-credit-diff5-negative-lag5d-v1`
- `rule_ofr_safe_asset_stress_relief_v1 / ofr-fsi-safe-assets-diff5-negative-lag5d-v1`

There is no grid, alternate sign, after-the-fact ensemble, or failed-candidate
reparameterization. The development gates and gross/base/stress costs match
the recent independent mechanism batches.

## Point-in-time limitation

The official page says current data are published with an approximate
two-business-day delay. This protocol uses a more conservative five-calendar-
day decision lag. The historical download is nevertheless a current-history
reconstruction, not a collection of historical publication vintages. It
therefore makes no claim that past values were unrevised at their original
decision dates.

Any candidate can reach at most `paper_shadow` after a separately frozen
2023-2025 confirmation and ADR-007 review. A forward collector must preserve
each exact response and fail closed on historical revisions before later-stage
consideration.

## Access boundary

Before this freeze, only official descriptive pages, public frontend schema
code, and response headers were inspected. No FSI JSON/CSV data body, value,
return, signal, or PnL was opened. The contract must be committed and pushed
before the single allowed GET. Qualification reports only schema, series
names, counts, dates, gaps, and hashes. Confirmation and the shared future
blind stay sealed.

## Provider outcome

The single official JSON body was opened from pushed freeze `5d3a899`. All
three required series contain 6,733 rows and share identical timestamps. The
development reserve qualifies with 762 unfilled observations from 2020-01-02
through 2022-12-30, a four-day maximum gap, and 41 warmup rows. The immutable
snapshot is `sha256:20224061…3349a0b`.

No factor value, signal, or PnL was reported. Development may open only after
`docs/progress/phase-2-research-v20-provider-qualification.json` is committed
and pushed. The no-vintage claim, D+5 lag, confirmation seal, and future blind
remain unchanged.
