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
