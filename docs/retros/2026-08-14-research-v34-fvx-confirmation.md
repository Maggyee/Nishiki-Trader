# 2026-08-14 Protocol v34 FVX Confirmation and Paper-Shadow Entry

- **Confirmation result**: **PASS** (`paper_shadow_review_eligible`).
- **Current stage**: `hold @ paper_shadow`.
- **Source / model**: `rule_cboe_fvx_relief_v1 / cboe-fvx-diff5-negative-lag1d-v1`.
- **SourcePolicy**: `dry_run=True`, `position_pct_multiplier=0.2`, `min_confidence_override=None`.
- **Future blind**: 2026-09-01 through 2027-01-31 remains sealed.
- **Trading effect**: dry-run only; no live orders.

## Pre-access integrity

Protocol v34 confirmation was frozen and committed at `2358572` before opening the 2023-2025 BTCUSDT execution holdout or calculating confirmation PnL. The contract locked the unchanged FVX candidate identity, the 5-observation negative difference rule, cost scenarios, 36-month confirmation window, performance gates, and market continuity rules.

The 2023-2025 factor observations (752 confirmation rows, 42 warmup rows) were extracted from the qualified snapshot (`data/research-v34/raw/fvx-20260814T014407Z-75b2f82d3153.json`) without any new network requests.

## Independent confirmation results

Two clean-commit Nautilus replays returned `MATCH` on duplicate runs:

| Metric | Frozen requirement | Result | Pass |
|---|---:|---:|---|
| **Base net PnL** | > 0 | **+70.707544 USDT** | **yes** |
| **Stress net PnL** | > 0 | **+67.571342 USDT** | **yes** |
| **Gross net PnL** | -- | **+83.252350 USDT** | **yes** |
| **Positive calendar years** | >= 2/3 | **3/3** | **yes** |
| **Positive calendar months** | >= 18/36 | **23/36** | **yes** |
| **Closed positions** | >= 30 | **79** | **yes** |
| **Leave-best base PnL** | > 0 | **+58.357464 USDT** | **yes** |
| **Duplicate replays** | 2 matching | **2, MATCH** | **yes** |
| **Short positions** | 0 | **0** | **yes** |

Yearly base PnL is consistently positive across all three confirmation years:
- **2023**: +26.315343 USDT
- **2024**: +36.891258 USDT
- **2025**: +7.500943 USDT

The candidate passed all frozen confirmation gates without parameter tuning or post-data selection.

## Paper-shadow entry

Paper-shadow session `data/research-v34/paper/20260814-014818Z-4cec982c` executed across the 2023-2025 confirmation window under `SourcePolicy(dry_run=True, position_pct_multiplier=0.2)`:
- 157 accepted signals (79 long entries, 78 flat exits)
- 157 dry-run signals, 0 orders, 0 fills, 0 positions
- 0 expired signals, 0 unauthorized signals, 0 kill-switch triggers
- Truthfully records 1 runtime data gap matching the pre-registered and REST-verified Binance downtime window (2023-03-24 13:00 UTC)

This places `rule_cboe_fvx_relief_v1 / cboe-fvx-diff5-negative-lag1d-v1` at `hold @ paper_shadow` alongside `rule_gold_vol_relief_v1 / cboe-gvz5obs-negative-1d-v1`.

## Next steps

1. Collect forward paper-shadow evidence using refreshed official FVX observations and public BTC market data.
2. Require forward shadow evidence (at least 7 forward days or 50 new signals) and explicit review before considering `paper_simulated`. Testnet and live trading remain blocked by the Phase 6 gate.

Machine details:
- Contract: `docs/progress/phase-2-research-v34-confirmation.json`
- Data Sources: `docs/progress/phase-2-research-v34-confirmation-data-sources.json`
- Confirmation Results: `docs/progress/phase-2-research-v34-confirmation-results.json`
