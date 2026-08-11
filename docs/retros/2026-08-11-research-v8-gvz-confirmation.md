# 2026-08-11 Research v8 GVZ Confirmation and Paper-Shadow Entry

- **Confirmation result**: pass.
- **Current stage**: `hold @ paper_shadow`.
- **Source / model**: `rule_gold_vol_relief_v1 / cboe-gvz5obs-negative-1d-v1`.
- **SourcePolicy**: `dry_run=True`, `position_pct_multiplier=0.2`, `min_confidence_override=None`.
- **Future blind**: 2026-09 through 2027-01 remains sealed.
- **Trading effect**: dry-run only; no orders.

## Pre-access integrity

Protocol v8 was frozen and pushed at commit `138cf35` before BTCUSDT 2023-2025
execution archives or strategy-specific PnL were opened. It locked the one
unchanged GVZ identity, the original five-observation negative-change rule,
costs, 36-month holdout, performance gates, and market-session-aware
continuity. Confirmation code was pushed at `20ec74d` before the data opening.

## Data qualification

All 36 official Binance monthly archives match their official SHA-256 files.
The catalog contains 26,303 official bars against 26,304 clock hours. The one
absent hour is also empty in the exact official Spot REST query and therefore
qualifies as an exchange-unavailable window under the pre-registered rule.
No synthetic or interpolated bar was added. There are zero duplicates and no
orders or fills in that unavailable hour.

The generic alpha reader initially emitted its legacy strict row-count blocker.
Commit `4270a0d` corrected the v8 adapter to remove only the exact
`26303 != 26304` blocker when `26303 official + 1 REST-verified unavailable ==
26304 clock hours`. All other blockers remain fail-closed. No performance gate
or strategy parameter changed.

## Independent confirmation result

Two clean-commit Nautilus replays returned `MATCH`.

| Metric | Frozen requirement | Result | Pass |
|---|---:|---:|---|
| Base net PnL | > 0 | +25.180955 USDT | yes |
| Stress net PnL | > 0 | +21.737949 USDT | yes |
| Positive years | >= 2/3 | 2/3 | yes |
| Positive months | >= 18/36 | 19/36 | yes |
| Closed positions | >= 30 | 83 | yes |
| Leave-best base PnL | > 0 | +12.855628 USDT | yes |
| Duplicate replays | 2 matching | 2, `MATCH` | yes |

Yearly base PnL is +4.234836 in 2023, +37.942251 in 2024, and -16.996132 in
2025. The negative 2025 year is material and must remain visible, but the
candidate passes the frozen two-of-three breadth rule without tuning or
subperiod selection.

## Paper-shadow entry

Bundle `data/research-v8/paper/20260811-083146Z-993b25e0` ran on clean commit
`4270a0d` with the paper-shadow policy. It records 166 accepted signals, all
166 as dry-run lineage, with zero orders, fills, positions, expired signals,
unauthorized signals, kill-switch events, or signals inside the verified
unavailable hour.

The generic paper report truthfully records one runtime gap. That gap exactly
matches the pre-registered and REST-verified unavailable window, so it is not
an effective v8 stage-entry blocker. This operator-directed review places the
candidate at `paper_shadow`; it does not authorize `paper_simulated`.

## Next gate

Collect genuinely forward paper-shadow evidence using refreshed official GVZ
observations and public BTC market data. Require at least seven forward days or
50 new signals, clean lineage/freshness/schema behavior, and explicit human
review before considering `paper_simulated`. Testnet and live remain blocked.

Machine detail is in
`docs/progress/phase-2-research-v8-confirmation-results.json`.
