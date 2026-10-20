# strategies_nautilus

NautilusTrader 上的自定义 Strategy、runner 和风控扩展。这是唯一的执行路径。

- **当前 Phase**：3 runtime 已建成（testnet canary 已暂停），Phase 6 启动守卫按设计会拒绝启动。
- **边界**：只消费 `SignalEvent v1`。订单必须经过 Nautilus `RiskEngine` 和
  ADR-008 硬风控（单日亏损停机、连续亏损暂停、信号过期拦截）。LLM 不进入这条路径。
- **现货语义**：现金账户（现货，含 Spot testnet）上 `sell` 信号按 `flat` 处理，只平多不开空；
  保证金账户不变。仓位可用 `--trade-size`（固定数量）或 `--trade-notional`（固定金额）。
  回测也支持 `--target-equity-fraction`（权益比例），配合 `--rebalance-weekday`（0–6）在该 UTC 星期结束时每周再平衡。
- **下一步入口**：等有候选策略通过 Gates v2 后，按 `docs/runbook-first-testnet-canary.md`
  用 `runners/testnet_runner.py` 重启 canary。
- **已归档**：`portfolio_*` 多资产执行、testnet session 与 joint/egress 模块
  （tag `archive/pre-slim-2026-10-17`，见 `docs/history.md`）。

## 文件

| 文件 | 用途 |
|---|---|
| `signal_consumer.py` | 从 `bridge.store` 读取并校验 SignalEvent（ADR-002 §4.1） |
| `baseline_strategy.py` | 纯 Python 的 signal → order intent 决策层 |
| `baseline_nautilus_strategy.py` | Nautilus Strategy 适配 |
| `result_schema.py` | ADR-004 bundle schema |
| `runners/backtest_runner.py` | catalog + SignalStore 回测，输出到 `data/backtests/<run_id>/` |
| `runners/paper_runner.py`、`wall_clock_bar_feed.py` | 本地模拟 paper（不连交易所），支持断点续跑 |
| `runners/testnet_runner.py`、`binance_testnet_exchange.py` | Binance Spot testnet 长跑，触发阈值时自动应急平仓 |
| `runners/emergency_flatten.py` | ADR-008 应急平仓 |
| `runners/first_testnet_canary.py`、`promotion_review*.py` | canary 升档闸门与审查材料 |
| `runners/report_paper_bundle.py`、`report_testnet_bundle.py` | bundle 被动审查 |
| `runners/live_startup_guard.py` | Phase 6 启动前拒绝合约（只读证据，阻塞时 exit 2） |
| `runners/live_telemetry.py`、`textfile_metrics.py`、`sidecar_writer.py` | 心跳、Prometheus textfile、sidecar |
| `runners/compare_backtests.py` | 两次回测的确定性对比 |

## 常用命令

```bash
# 回测（先用 apps.ops.backfill_bars 准备 data/catalog）
uv run python -m apps.strategies_nautilus.runners.backtest_runner \
  --catalog-path data/catalog --instrument-id BTCUSDT.BINANCE \
  --bar-type BTCUSDT.BINANCE-1-MINUTE-LAST-EXTERNAL \
  --signal-store-path data/bridge/signals.db \
  --signal-source manual_research --signal-model-version binance-fixture-v1 \
  --trade-size 0.001 --starting-balance 100000

# 模拟 paper（kind="paper"，写入 data/paper/<run_id>/）
uv run python -m apps.strategies_nautilus.runners.paper_runner \
  --catalog-path data/catalog --instrument-id BTCUSDT.BINANCE \
  --bar-type BTCUSDT.BINANCE-1-MINUTE-LAST-EXTERNAL \
  --signal-store-path data/bridge/signals.db \
  --signal-source <source> --signal-model-version <version> \
  --trade-size 0.001 --starting-balance 100000 \
  --policy-position-pct-multiplier 0.2 --policy-dry-run

uv run python -m apps.strategies_nautilus.runners.report_paper_bundle --json data/paper/<run_id>

# testnet（需要 testnet 凭证；重启时传 --previous-run-id/--restart-reason 做对账）
uv run python -m apps.strategies_nautilus.runners.testnet_runner \
  --mode testnet --kind testnet --allow-real-credentials \
  --source <source> --model-version <version> \
  --policy-position-pct-multiplier 0.2 --long-run \
  --instrument-id BTCUSDT.BINANCE --starting-balance 100000 --max-run-seconds 3600

uv run python -m apps.strategies_nautilus.runners.compare_backtests \
  data/backtests/<run-a> data/backtests/<run-b>
```

外部心跳 watchdog 的入口是 `python -m infra.watchdog.watchdog`。

测试：`tests/strategies_nautilus/`
