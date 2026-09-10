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
不撮合、不下单；现由独立的合成输入验收 runner 调用。它要求已对账的账户快照，覆盖挂单预留、
部分成交/待撤单、组合敞口及损失阈值；快照检查不等于原子资金预留。
`select_funded_batch` 在此基础上按减仓优先、事件时间、固定策略顺序选择可负担
订单，并保留跳过原因；不缩量、不预支卖单收入、不排队重试。详见
[v2 接纳规则](../../docs/progress/portfolio-funded-admission-2026-09-09.md)。
`portfolio_simulation.py` 已接入 Nautilus 原生模拟订单、持仓及账户，完成预留、
部分/延迟成交、撤单确认、策略热重启和风控锁存验收。只接受测试 SignalEvent 身份；
冷启动缺少原生状态时拒绝恢复。现有 paper/testnet/live runner 未接入。

```bash
.venv/bin/python -m apps.strategies_nautilus.runners.portfolio_simulation_acceptance
```

`portfolio_venue.py` 将本地保存的 Binance exchangeInfo、commission、myFilters
响应转换为预检查规则，覆盖价格区间、订单名额和资产上限。现有只收 USDT 手续费
假设不支持 BTC 买入扣费或 BNB 扣费，适配层会明确拒绝，不自动缩量。
独立验收模式 `--fee-mode received_asset` 已通过 Nautilus 原生 BTC 买入手续费、
净持仓和 8 位账务精度验证，交易数量步长仍不变。`portfolio_inventory.py` 报告
步长余数；默认 `exact_v1` 完整平仓数量不合规时仍拒绝。显式 `whole_steps_v1`
离线退出策略只提出整步长卖出数量，再执行完整预检查；余量留在原策略原生持仓，
计入权益并阻止超额再买入。不会归集、核销或自动重试。BNB 仍不支持。

```bash
.venv/bin/python -m apps.strategies_nautilus.runners.portfolio_simulation_acceptance --fee-mode received_asset
.venv/bin/python -m apps.strategies_nautilus.runners.portfolio_simulation_acceptance --fee-mode received_asset --exit-policy whole_steps_v1
```

`portfolio_account_collector.py` 提供显式签名 GET 只读采集接口，支持只读 key，
不自动加载凭证。`portfolio_account.py` 精确比较总额/可用/锁定余额、全订单历史、
逐笔成交和手续费；REST 相符仍不代表实时账户版本原子一致。
`portfolio_recovery.py` 在显式原生持久化模式下，用 Nautilus 事件重建新进程的
账户、订单和持仓，保留余量、去重与风控锁存；未知提交、待撤单及对账差异均阻断。

```bash
.venv/bin/python -m apps.strategies_nautilus.runners.portfolio_recovery_acceptance
```

该验收会终止首个进程并在第二个进程继续原生挂单，仅使用合成账户观察；不恢复
模拟交易所的完整市场队列，不构成真实账户或实盘恢复验收。详见
[账户对账与进程恢复](../../docs/progress/portfolio-account-recovery-2026-09-09.md)。
`portfolio_stream.py` 现提供来源绑定、订阅代次、持久化事件链与 REST 核对凭据；
新事件、断线或过期会使旧凭据失效。`portfolio_adapter_recovery.py` 用真实 Nautilus
Binance 转换器及原生对账引擎验证合成订单恢复，拒绝推断成交、执行客户端与交易命令。
这些恢复验证只使用合成账户，也未接入进程恢复或现有 runner。
本地回执无法证明交易所用户流全局无丢包。详见
[来源、用户流及适配器验收](../../docs/progress/portfolio-source-stream-adapter-2026-09-10.md)。
`portfolio_user_stream.py` 现通过 Nautilus 原生签名与 Rust WebSocket I/O 实现
只读签名订阅，保留完整事件信封，按真实连接状态验证核对凭据，断线后要求重新订阅。
配套 `BinanceAccountReadOnlyHttpClient` 限定账户 GET 路径并避开签名 URL 调试日志。
真实网络收发已在本机 WebSocket 服务验收，尚未连接 Binance 私有账户。
调用示例和清理约定见
[原生只读传输验收](../../docs/progress/portfolio-readonly-transport-2026-09-10.md)。
`portfolio_adapter_checkpoint.py` 现提供隔离的数字订单号检查点恢复：原生事件重建后，
应用 Binance 原始成交报告，再精确检查账户余额、锁定金额、手续费和持仓归属。
三进程验收验证突然退出、恢复和幂等重放；原检查点、策略状态及风险锁存保持不变。
它不启动策略，不认定停机风险历史完整，也不允许数字检查点进入默认 UUID 模拟恢复。

```bash
.venv/bin/python -m apps.strategies_nautilus.runners.portfolio_adapter_checkpoint_acceptance
```

见[适配器检查点恢复验收](../../docs/progress/portfolio-adapter-checkpoint-2026-09-10.md)。
`portfolio_downtime_risk.py` 将停机期原生账户快照和买一报价绑定到恢复前后检查点，
只读识别日内 5% 越线及规划风险阈值，不会因恢复时回升而清除记录或已有锁存。
它报告 500 USDT 日初权益下 25 USDT 与规划 50 USDT 的差异，不改变任何配置。
采样无法证明完整覆盖，跨 UTC 日缺少新基线时拒绝审核；结果永远不放行交易。
见[停机风险审核](../../docs/progress/portfolio-downtime-risk-2026-09-10.md)。
绑定用户流的账户采集现将每页原始 REST 响应刷盘，并记录采集 ID 和完成标记。
`portfolio_account_archive.py` 按指定归档哈希、来源和独立基线离线重放采集器，
复核权限、UID、分页和前后账户一致性；旧哈希日志及中断采集不能补充认定为完整证据。
历史结果没有可复用的连接核对凭据，详见
[账户原始响应归档与重放](../../docs/progress/portfolio-account-archive-2026-09-10.md)。
下一入口为明确账户环境、凭证变量名/配置路径、预期 UID 和独立账户基线，验证真实
来源、账户/行情归档、资金流和 UTC 日初基线及策略风险政策；部署前还需明确余量入场政策。
详见[原生手续费验收](../../docs/progress/portfolio-base-fee-acceptance-2026-09-09.md)及
[残余库存退出验收](../../docs/progress/portfolio-residual-exit-2026-09-09.md)。

- 不直接接交易所 API（用 nautilus 的 binance adapter）
- 不绕过 `RiskEngine`
- 不修改 `nautilus_trader/` 上游源码
- Phase 1–5 都是 backtest / dry-run / testnet；真实账户只在 Phase 6 接入
