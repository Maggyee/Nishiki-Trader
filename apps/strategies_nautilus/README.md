# strategies_nautilus

NautilusTrader 上的自定义 Strategy / Actor / 风控扩展。

**当前 Phase**：2（ML signal layer / catalog-driven Nautilus backtests）。

## 职责

- 订阅 `bridge.SignalEvent`，生成订单意图
- 调用 NautilusTrader `RiskEngine` / `ExecutionEngine`
- 实现 ADR-002 §4.1 策略侧规则（schema / venue / ttl / confidence / source 校验）
- 实现 ADR-002 §4.2 风控侧规则（单日 5% 亏损停机、连续亏损暂停、信号过期拦截）
- 实现 ADR-002 §4.3 降级行为（信号源挂掉 / Redis 挂掉 / 信号格式错误）

## 当前入口

Phase 2 baseline backtest runner:

```bash
uv run python -m apps.strategies_nautilus.runners.backtest_runner \
  --catalog-path data/catalog \
  --instrument-id BTCUSDT.BINANCE \
  --bar-type BTCUSDT.BINANCE-1-MINUTE-LAST-EXTERNAL \
  --signal-store-path data/bridge/signals.db \
  --signal-source manual_research \
  --signal-model-version binance-fixture-v1 \
  --trade-size 0.001 \
  --starting-balance 100000
```

The runner loads bars and instruments through NautilusTrader
`ParquetDataCatalog`, loads signals through `SignalStore.replay(**filter)`,
and writes the ADR-004 bundle under `data/backtests/<run_id>/`.

Phase 2 simulated paper runner:

```bash
uv run python -m apps.strategies_nautilus.runners.paper_runner \
  --catalog-path data/catalog \
  --instrument-id BTCUSDT.BINANCE \
  --bar-type BTCUSDT.BINANCE-1-MINUTE-LAST-EXTERNAL \
  --signal-store-path data/bridge/signals.db \
  --signal-source freqai_linear_v1 \
  --signal-model-version linear-mom-train20240105 \
  --trade-size 0.001 \
  --starting-balance 100000 \
  --policy-position-pct-multiplier 0.2 \
  --policy-dry-run
```

The paper runner writes a `kind="paper"` bundle under `data/paper/<run_id>/`.
It is local simulation only: no exchange keys, no exchange adapter, no live
orders.

Paper bundle review summary:

```bash
uv run python -m apps.strategies_nautilus.runners.report_paper_bundle \
  --json \
  data/paper/<run_id>
```

The report CLI reads the manifest and sidecar Parquet files, summarizes
lineage decisions, risk blockers, policy state, PnL, and missing promotion
metrics, and prints whether the bundle is reviewable. It does not promote
sources or mutate policy.

For the local BTCUSDT fixture, build `data/catalog/` first with:

```bash
uv run python -m apps.ops.backfill_bars \
  --download \
  --symbol BTCUSDT \
  --interval 1m \
  --date 2024-01-01 \
  --catalog-path data/catalog \
  --seed-demo-signals \
  --signal-store-path data/bridge/signals.db
```

Replay comparison:

```bash
uv run python -m apps.strategies_nautilus.runners.compare_backtests \
  data/backtests/<run-a> \
  data/backtests/<run-b>
```

The comparison ignores `run_id`, `started_at`, `finished_at`, and
`elapsed_seconds`, then compares the normalized manifest plus `fills.parquet`
byte-for-byte.

## 文件布局

```text
strategies_nautilus/
├── __init__.py
├── signal_consumer.py    # 从 bridge.store 读 SignalEvent
├── baseline_strategy.py  # 纯 Python signal -> order intent 决策层
├── baseline_nautilus_strategy.py
├── result_schema.py
└── runners/
    ├── backtest_runner.py
    ├── paper_runner.py
    ├── report_paper_bundle.py
    └── compare_backtests.py
```

测试：`tests/strategies_nautilus/`

## 边界

- 不直接接交易所 API（用 nautilus 的 binance adapter）
- 不绕过 `RiskEngine`
- 不修改 `nautilus_trader/` 上游源码
- Phase 1–5 都是 backtest / dry-run / testnet；真实账户只在 Phase 6 接入
