# Phase 2 Research Protocol v8 — GVZ Independent Confirmation

- **Frozen**: 2026-08-11, before opening BTCUSDT 2023-2025 execution archives or strategy-specific PnL.
- **Machine contract**: `docs/progress/phase-2-research-protocol-v8.json`
- **Provider contract**: `docs/progress/phase-2-research-v8-data-sources.json`
- **Status**: confirmation passed; candidate entered `paper_shadow` dry-run.
- **Trading effect**: none.

## Why this stage exists

Protocol v7's strict clock-hour continuity rule incorrectly treated verified
Binance Spot downtime as local data loss. The later sensitivity showed that the
30 official no-kline hours caused no order, fill, or PnL change. The immutable
v7 decision remains historical evidence, while GVZ is retained at the research
program level as a provisional survivor requiring genuinely independent
confirmation.

## Frozen confirmation

Only `rule_gold_vol_relief_v1 / cboe-gvz5obs-negative-1d-v1` is allowed. Its
five-observation negative-change rule, zero threshold, long/flat behavior,
confidence, TTL, trade size, costs, and gates are unchanged. No VIX/OVX retry,
parameter search, sign change, ensemble, or subperiod selection is allowed.

The strategy-specific holdout is BTCUSDT Spot 1h from 2023-01-01 through
2025-12-31. The exact already-frozen Cboe snapshot supplies point-in-time GVZ
observations; no refreshed vintage is permitted. The 2026-09 through 2027-01
future blind remains sealed.

## Market-session-aware continuity

Every Binance monthly archive must match its official checksum. A clock-hour
gap is acceptable only when the exact same window returns zero klines from the
official Spot REST API; it is then classified as exchange unavailable rather
than missing market data. Official bars remain unmodified. Synthetic bars,
interpolation, archive/REST disagreement, unexplained gaps, and orders or fills
during verified no-kline windows all fail closed before promotion.

If all fixed performance, breadth, concentration, lineage, data, and duplicate
replay gates pass, GVZ becomes eligible for a human `paper_shadow` review. v8
cannot authorize testnet or live trading.

## Result

The one allowed 2023-2025 opening passed every fixed gate: base/stress PnL
+25.180955/+21.737949 USDT, 2/3 positive years, 19/36 positive months, 83
positions, +12.855628 USDT after removing the best position, and matching
duplicate replays. Thirty-six official execution archives qualified; one
official/REST-empty hour was treated as exchange unavailable with no synthetic
bar and no order or fill in that window.

The candidate is now `hold @ paper_shadow` under
`SourcePolicy(dry_run=True, position_pct_multiplier=0.2,
min_confidence_override=None)`. See
`docs/retros/2026-08-11-research-v8-gvz-confirmation.md`.
