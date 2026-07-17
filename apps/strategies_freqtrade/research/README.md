# strategies_freqtrade / research

Lightweight research-layer signal generators that do **not** depend on
freqtrade's `IStrategy` framework. They exist so the Phase 2 pipeline

```
research → SignalEvent v1 (apps/bridge) → NautilusTrader backtest_runner
```

can be exercised end-to-end without first wiring up a full FreqAI training
loop.

**Current phase**: Phase 2 (signal-pipeline smoke).

## Boundary

- These generators output `SignalEvent v1` only (ADR-002 §3.1) — never orders.
- They write through `apps.bridge.store.SignalStore`; no exchange or trading
  API is imported.
- They are deterministic given the same input bars + parameters.
- They are **not** alpha. EMA-cross + RSI is a placeholder so the SignalEvent
  carry-through (orders/fills/positions/signal_lineage) can be smoke-tested
  against real Binance bars before FreqAI / model-driven signals land.

## Files

- `baseline_rule_signals.py` — EMA(5)/EMA(20) cross with RSI(14) overbought /
  oversold filter. `source="rule_baseline_v1"`,
  `model_version="ema5-20+rsi14"`.
- `freqai_linear_signals.py` — deterministic ridge-linear momentum export for
  the first `freqai_*` source-family smoke. It is classic-ML output under the
  ADR-005 `freqai` family, not the full freqtrade/FreqAI runtime loop yet.
  Default `source="freqai_linear_v1"`,
  `model_version="linear-mom-train20240105"`.
- `freqai_linear_walkforward_signals.py` — monthly 60-day walk-forward ridge
  candidate with a 30 bps threshold and long/flat Spot targets only.
  `source="freqai_linear_walkforward_v1"`,
  `model_version="ridge-wf60d-cost30bp-v1"`.
- `breakout_rule_signals.py` — 15m Donchian(20/10) + ATR(14) × 0.25
  transition-only long/flat candidate.
  `source="rule_breakout_v1"`,
  `model_version="donchian20-10-atr14x0.25-15m"`.
- `trend_regime_signals.py` — locked low-turnover 1h EMA(24/96), 24h
  momentum, ATR(14) × 0.5 long/flat hypothesis for the untouched
  2025-08..2025-12 window. `source="rule_trend_regime_v1"`,
  `model_version="ema24-96-1h-mom24-atr14x0.5-v1"`.
- `pullback_regime_signals.py` — pre-registered causal previous-day
  EMA(50/200) risk-on permission plus 1h EMA(24) pullback recovery, bounded
  ATR giveback, structural invalidation, and 72h failure timeout. Spot
  long/flat only; no parameter search. `source="rule_pullback_regime_v1"`,
  `model_version="daily50-200-1h24-pullback-giveback1.25-v1"`.
- `diverse_strategy_signals.py` — four simultaneously pre-registered,
  no-search Spot long/flat sources: 4h oversold mean reversion, 4h
  Bollinger/Keltner squeeze breakout, 4h price/OBV/volume breakout, and daily
  dual absolute momentum. Select one with `--strategy`; identities and gates
  are locked in `docs/progress/phase-2-diverse-strategy-tournament.md`.
- `independent_mechanism_signals.py` — three Research Protocol v2 daily,
  point-in-time candidates based on option-implied risk compensation,
  fixed-expiry futures basis, and stablecoin liquidity. The module rejects
  publication lookahead, gaps, duplicates, revisions without immutable
  fingerprints, non-finite factors, and runtime parameter changes. Identities,
  factor contracts, partitions, and gates are locked in
  `docs/progress/phase-2-research-protocol-v2.json`.
- `macro_native_mechanism_signals.py` — three Research Protocol v3 daily,
  point-in-time candidates based on miner hashrate recovery, multi-week USD
  weakness (DXY), and equity volatility relief (VIX). Parameters, signs, and
  lookbacks are frozen; the module reuses the point-in-time audit helpers and
  rejects runtime tuning. Identities and gates are locked in
  `docs/progress/phase-2-research-protocol-v3.json`.
- `binance_mechanism_signals.py` — the two Research Protocol v5 Binance-native
  curve-carry and BVOL-relief generators. The CLI can write both sleeves or
  isolate one `--asset` in its own SignalStore for independent Nautilus runs.
- `wall_clock_signal_replay.py` — testnet-canary helper that copies already
  reviewed historical `SignalEvent` rows, re-stamps `ts_event` into future
  wall-clock times, and writes them back to `SignalStore`. It preserves the
  original source/model for SourcePolicy authorization and records the
  historical source row in `metadata.wall_clock_replay`.

## CLI

```bash
uv run python -m apps.strategies_freqtrade.research.baseline_rule_signals \
  --catalog-path data/catalog \
  --signal-store-path data/bridge/signals.db \
  --symbol BTCUSDT \
  --venue BINANCE \
  --bar-type 'BTCUSDT.BINANCE-1-MINUTE-LAST-EXTERNAL'
```

Outputs the number of `SignalEvent`s written and ignored (duplicates). Pass
`--dry-run` to print events without touching the store.

```bash
uv run python -m apps.strategies_freqtrade.research.freqai_linear_signals \
  --catalog-path data/catalog \
  --signal-store-path data/bridge/signals.db \
  --symbol BTCUSDT \
  --venue BINANCE \
  --bar-type 'BTCUSDT.BINANCE-1-MINUTE-LAST-EXTERNAL' \
  --train-until '2024-01-05T23:59:00Z'
```

For an ADR-008 testnet canary, generate a small future-time signal stream from
the reviewed historical `freqai_linear_v1` rows:

```bash
uv run python -m apps.strategies_freqtrade.research.wall_clock_signal_replay \
  --input-store-path data/bridge/signals.db \
  --output-store-path data/bridge/signals.db \
  --source freqai_linear_v1 \
  --model-version linear-mom-train20240105 \
  --start-delay-seconds 180 \
  --interval-seconds 60 \
  --max-signals 3 \
  --min-confidence 0.55 \
  --side buy \
  --ttl-seconds 900
```

Pass `--dry-run` first to inspect the generated rows without touching the
store. Run the real write shortly before starting the canary so the runner's
initial SignalStore cursor is before the restamped `ts_event` values.

The two cost-aware candidate exporters use the same catalog/store arguments as
the existing generators and support `--dry-run`. They are fixed research
fingerprints: changing their training window, threshold, Donchian/ATR
parameters, or blind-test split requires a new `model_version`.

Research Protocol v2 inputs are daily point-in-time CSV files. Validate the
protocol before constructing any real factor dataset, then inspect a synthetic
or pipeline-qualification file without writing SignalStore:

```bash
uv run python -m apps.ops.research_protocol_v2
uv run python -m apps.strategies_freqtrade.research.independent_mechanism_signals \
  --strategy futures_basis_curve \
  --input-csv data/research-v2/futures-basis.csv \
  --dry-run
```

The July 2026 qualification interval permits schema/lineage/freshness checks
only. Do not inspect PnL, use opened 2023-2025 results for selection, or open
the 2020-2022 replication reserve before the factor pipeline and checksums are
complete on a committed tree.

```bash
uv run python -m apps.ops.research_protocol_v3
uv run python -m apps.strategies_freqtrade.research.macro_native_mechanism_signals \
  --strategy miner_hashrate_recovery \
  --input-csv data/research-v3/hashrate.csv \
  --dry-run
```

Protocol v3 inputs are also daily point-in-time CSV files. Validate the
protocol before constructing any real factor dataset. Do not inspect PnL, use
opened 2023-2025 results for selection, or open the 2020-2022 replication
reserve before the factor pipeline and checksums are complete on a committed
tree.

Protocol v5 normalized snapshots can be exported into one asset-isolated
SignalStore. Omit `--asset` only when a combined two-asset store is explicitly
needed:

```bash
uv run python -m apps.strategies_freqtrade.research.binance_mechanism_signals \
  --candidate bvol_relief \
  --asset BTCUSDT \
  --start-date 2023-08-01 \
  --end-date 2023-12-31 \
  --signal-db data/research-v5/signals/bvol-BTCUSDT-2023-08_12.db
```
