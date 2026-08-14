# 2026-08-14 Protocol v36 VPN Confirmation Review

- **Confirmation result**: **PASSED** (`paper_shadow_review_eligible`).
- **Primary candidate**: `vpn_expansion` (`rule_cboe_vpn_expansion_v1 / cboe-vpn-diff5-positive-lag1d-v1`).
- **Confirmation window**: 2023-01-01 through 2025-12-31.
- **Holdout catalog**: `data/research-v8/catalog` (BTCUSDT 1h Cash spot netting).
- **Future blind**: 2026-09-01 through 2027-01-31 remains sealed.
- **Trading effect**: none; live trading remains blocked by the Phase 6 gate.

## Confirmation Performance Summary

| Metric | Frozen requirement | Result | Pass |
|---|---:|---:|---|
| **Base net PnL** | > 0 | **+57.462442 USDT** | **yes** |
| **Stress net PnL** | > 0 | **+54.697557 USDT** | **yes** |
| **Gross net PnL** | -- | **+68.521980 USDT** | **yes** |
| **Positive calendar years** | >= 2/3 | **3/3** (2023: +12.61, 2024: +36.92, 2025: +7.93) | **yes** |
| **Positive calendar months** | >= 18/36 | **19/36** | **yes** |
| **Closed positions** | >= 30 | **65** | **yes** |
| **Leave-best base PnL** | > 0 | **+37.752997 USDT** | **yes** |
| **Duplicate replays** | 2 matching | **2, MATCH** | **yes** |
| **Short positions** | 0 | **0** | **yes** |
| **Verified no-kline event hits** | 0 | **0** | **yes** |
| **Effective blockers** | 0 | **0** | **yes** |

## Recommendation

Advance candidate `rule_cboe_vpn_expansion_v1 / cboe-vpn-diff5-positive-lag1d-v1` to `hold @ paper_shadow` under `SourcePolicy(dry_run=True, position_pct_multiplier=0.2, min_confidence_override=None)` and install its forward paper-shadow automated daily cron collector.
