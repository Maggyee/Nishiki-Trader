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
