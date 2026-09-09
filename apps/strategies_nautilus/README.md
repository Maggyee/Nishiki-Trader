# strategies_nautilus

NautilusTrader 上的自定义 Strategy / Actor / 风控扩展。

**当前 Phase**：3 entry（testnet guard rails / emergency flatten）。

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
  --policy-dry-run \
  --heartbeat-interval-seconds 30 \
  --poll-interval-seconds 60 \
  --poll-batch-size 1
```

The paper runner writes a `kind="paper"` bundle under `data/paper/<run_id>/`.
It is local simulation only: no exchange keys, no exchange adapter, no live
orders. Catalog polling is processed through an event-time cursor, with
runtime heartbeats in `logs/heartbeat.jsonl`, poll/data-gap records in
`logs/runtime.log`, and restart metadata in `run_manifest.json.runtime`.
Use `--previous-run-id <run_id> --restart-reason <reason>` to start a new
session from the previous bundle's processed cursor.

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

Phase 3 guarded testnet runner:

```bash
uv run python -m apps.strategies_nautilus.runners.testnet_runner \
  --mode testnet \
  --kind testnet \
  --allow-real-credentials \
  --source freqai_linear_v1 \
  --model-version linear-mom-train20240105 \
  --policy-position-pct-multiplier 0.2 \
  --long-run \
  --instrument-id BTCUSDT.BINANCE \
  --starting-balance 100000 \
  --max-run-seconds 3600
```

The long-running shell reuses the Phase 3b Binance Spot testnet connection
guard, writes `data/testnet/<run_id>/run_manifest.json` plus runtime logs, and
auto-invokes the ADR-008 emergency flatten path when the 5% daily-loss,
exchange-error burst, or WS-reconnect burst thresholds fire. It writes only
the credential source and API key prefix to disk.

Phase 6 passive live startup guard:

```bash
uv run python -m apps.strategies_nautilus.runners.live_startup_guard \
  --mode live \
  --kind live \
  --allow-live-credentials \
  --source freqai_linear_v1 \
  --model-version linear-mom-train20240105 \
  --policy-position-pct-multiplier 0.1 \
  --starting-capital-usdt 100 \
  --live-readiness-report-path docs/retros/<phase6-live-readiness>.json \
  --live-promotion-review-path docs/retros/<live-canary-promotion-review>.md \
  --first-live-day-runbook-path docs/runbook-first-live-day.md \
  --markdown
```

The guard is a refusal contract for a future live runner. It reads only local
evidence paths and git state, returns exit code 2 when blocked, and does not
read live credential values, build a Nautilus node, connect to Binance, mutate
`SourcePolicy`, write `SignalEvent`, or place orders. Current repo evidence is
expected to block because Phase 6 is not open.

For a restart, pass `--previous-run-id <run_id> --restart-reason <reason>`;
the runner compares the previous bundle's open orders / positions with
exchange REST state before building a new node. Drift writes
`restart_drift_detected` to `logs/alerts.log` and exits 3. The external
heartbeat watchdog entrypoint is `python -m infra.watchdog.watchdog`.

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
    ├── live_startup_guard.py
    └── compare_backtests.py
```

测试：`tests/strategies_nautilus/`

## 边界

`portfolio_preflight.py` 是离线组合订单资金/风控预检查，不维护订单账本、
不撮合、不下单，目前未接入任何 runner。它要求已对账的账户快照，覆盖挂单预留、
部分成交/待撤单、组合敞口及损失阈值；快照检查不等于原子资金预留。
下一入口是 Nautilus 模拟执行的账户适配与生命周期测试，见
[固定组合契约](../../docs/progress/portfolio-execution-contract-2026-09-09.md)。

- 不直接接交易所 API（用 nautilus 的 binance adapter）
- 不绕过 `RiskEngine`
- 不修改 `nautilus_trader/` 上游源码
- Phase 1–5 都是 backtest / dry-run / testnet；真实账户只在 Phase 6 接入
