# 2026-08-11 Research Protocol v7 Replication Review

- **Status**: complete; all three candidates rejected.
- **Decision**: `stop_before_testnet_resume`.
- **Selected candidates**: 0.
- **Backtest commit**: clean `d91ac5241f6207a94e466eeda47d69424e093892`.
- **Future blind**: 2026-09-01 through 2027-01-31 remains sealed.
- **Trading effect**: none.

## Evidence

The official Cboe VIX/OVX/GVZ snapshots passed offline raw-byte, schema,
publication-lag, vintage, and snapshot-hash verification. They produced
171/175/162 isolated Spot long/flat state-change signals. The official Binance
BTCUSDT 1h catalog covers 2020-01-01 through 2022-12-31 with 26,274 bars,
zero duplicates, but 30 missing hourly intervals across 14 irregular steps.
No data was filled or interpolated.

Each candidate ran twice through NautilusTrader with CASH/NETTING, 0.001 BTC,
100,000 USDT starting balance, and the frozen gross/base/stress costs. All three
duplicate comparisons returned `MATCH` for normalized manifests, fills,
orders, positions, and signal lineage.

| Candidate | Gross | Base | Stress | Positive years | Positive months | Positions | Leave-best base | Decision |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| VIX relief | +15.529080 | +9.538828 | +8.041265 | 2/3 | 21/36 | 86 | -1.373440 | reject |
| OVX relief | +3.726060 | -2.443604 | -3.986020 | 2/3 | 15/36 | 88 | -13.355872 | reject |
| GVZ relief | +24.618450 | +18.871408 | +17.434647 | 2/3 | 24/36 | 81 | +6.266502 | reject |

VIX fails the concentration gate even before considering catalog continuity.
OVX fails base/stress, monthly breadth, and concentration. GVZ passes every
numeric and reproducibility gate, but the pre-registered execution-data hard
blocker is binding: the catalog is short 30 hours. Because the missing-data
rule was fixed before PnL, it cannot be relaxed after seeing GVZ's result.

## Decision

No candidate advances to the future blind or `paper_shadow`. Do not fill the
missing hours, change the execution interval, tune the five-observation rule,
or create a replacement identity merely to preserve GVZ's positive result.
A future study requires genuinely new independent evidence and a new protocol
defined before data access.

Machine detail is in
`docs/progress/phase-2-research-v7-replication-results.json`. Generated raw
snapshots, factors, SignalStores, catalog, bundles, and the full review remain
gitignored under `data/research-v7/`.
