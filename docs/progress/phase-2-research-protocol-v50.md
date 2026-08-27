# Research Protocol v50 — BTC Funding-Rate Positioning States (ADR-014 / backlog B2)

- **Status**: Pre-registered (frozen before any funding value was fetched)
- **Date frozen**: 2026-08-27
- **Mechanism family**: `crypto_derivatives_structure` (open; registered in
  `docs/progress/research-mechanism-family-registry.json`)
- **Identities**:
  - `rule_crypto_funding_negative_v1 / crypto-btc-funding-sum72h-negative-v1`
  - `rule_crypto_funding_below_baseline_v1 / crypto-btc-funding-mean72h-below-1bp8h-v1`
  - `rule_crypto_funding_overheat_flat_v1 / crypto-btc-funding-mean72h-overheat5bp8h-flat-v1`
- **Contract**: `apps/ops/research_protocol_v50.py` (`contract_sha256()` stamped
  into every stage output)
- **Pipeline**: `apps/ops/research_v50_funding.py`
  (`fetch-dev` → `qualify` → `develop` → `confirm`)
- **Gates**: Gates v2 per ADR-014 §4

## 1. Hypothesis and non-duplication (ADR-014 §3.4, warning W2)

The settled perpetual funding rate is a *paid* positioning cost, not a quote:
persistent negative funding marks crowded shorts (contrarian long states) and
funding far above the structural baseline marks overheated longs. Distinct
from the saturated `external_index_relief` family (crypto-native observable;
level states against structural constants, no 5-observation delta shape),
from sealed v45/v46 (premium-index 5-day delta relief) and v48 (basis vs its
own MA) by observable and state construction, and from the legacy
`rule_funding_crowding_rotation_v1` reject (cross-alt rotation portfolio)
by being single-asset BTC regime rules under the modern ceremony.

Thresholds are structural, not tuned: 0 (sign of the paid rate), 0.0001
(Binance's fixed 0.01%/8h interest-rate component — neutral funding at zero
premium), and 0.0005 (5× baseline, plainly overheated).

- **Directional declaration**: spot long/flat only (paper venue parity); the
  symmetric short side is deferred to `two_sided_regime` (backlog B4). Spot
  execution earns/pays no funding — the test is purely directional.
- **Weekend coverage**: funding settles every 8h, 24/7, broadcast at
  settlement; no weekend vacuum, no vintage risk (immutable exchange archive).
  The last settlement feeding a day-D close decision is 16:00 UTC of day D.

## 2. Frozen data contract

- Binance Vision USD-M monthly `fundingRate` archives for BTCUSDT, one GET per
  month file, CHECKSUM-verified. **Staged fetch boundary**: development months
  2019-12..2022-12 at qualification; confirmation months 2023-01..2025-12 may
  be fetched only after development passes (enforced in `run_confirm`).
- Data-quality gates (fail closed): |rate| ≤ 0.05, settlement gap ≤ 16h,
  ≥3300 development settlements, ≥3200 confirmation settlements.
- Execution/benchmark closes: Binance Vision spot 1d 2019-12..2025-12 into
  `data/research-v50/closes/` (same fetcher as v49).

## 3. Frozen rules

Trailing window 72h ending at the day-D cutoff `(D+1)T00:00Z`; fewer than 6
settlements in the window forces flat.

| Candidate | Rule |
|---|---|
| `fund_neg_3d` | sum(rates, 72h) < 0 → long, else flat |
| `fund_below_baseline_3d` | mean(rates, 72h) < 0.0001 → long, else flat |
| `fund_overheat_flat_3d` | mean(rates, 72h) > 0.0005 → flat, else long |

State at day-D close held for day D+1; 0.001 BTC; gross/base/stress costs as
v48.

## 4. Windows, gates, advance rule

Development 2020-01-01..2022-12-31 and confirmation 2023-01-01..2025-12-31,
both 36 months with the ≥18/36 breadth gate plus the full Gates v2 set
(base/stress > 0, ≥2/3 years, ≥60 positions, leave-best > 0, base >
exposure×B&H, matched random-timing bootstrap p ≤ 0.10 with 20,000 trials
seed 20260827, two duplicate replays). Among development passers, only the
highest base-PnL candidate opens confirmation (ties → alphabetical); the
others record `development_passed_not_advanced`. A confirmation failure
closes the advanced identity permanently; development failures close their
identities permanently. No retuning, threshold search, or ensemble.

## 5. Boundaries

No `SignalEvent` writes, no `SourcePolicy` changes, no sealed-protocol
reopening, no future-blind access (2026-09..2027-01 stays sealed; all data
ends 2025-12-31), no live-path impact. Stage outputs land in
`docs/progress/phase-2-research-v50-{provider-qualification,development-results,confirmation-results}.json`.
