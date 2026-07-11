# ops

运维脚本。

**当前 Phase**：2（catalog fixture / backtest operations）+ Phase 4/5 read-only
dashboard snapshot support + Phase 6 passive readiness gate support。

## 当前入口

准备一份本地 BTCUSDT Binance 1m catalog fixture，并写入只用于冒烟测试的
`SignalEvent v1` demo signals：

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

等价地，也可以先手动下载 Binance public data ZIP，再用 `--raw-path` 导入：

```bash
uv run python -m apps.ops.backfill_bars \
  --raw-path data/raw/binance/spot/daily/klines/BTCUSDT-1m-2024-01-01.zip \
  --catalog-path data/catalog \
  --seed-demo-signals
```

fixture importer 支持锁定研究宇宙 `BTCUSDT`、`ETHUSDT`、`SOLUSDT` Binance
Spot，并生成对应 Nautilus instrument/bar type 命名供 backtest runner 使用：

- instrument id: `BTCUSDT.BINANCE`
- bar type: `BTCUSDT.BINANCE-1-MINUTE-LAST-EXTERNAL`

`--seed-demo-signals` 写入的 `manual_research/binance-fixture-v1` 信号只用于
确认 catalog-backed runner 可以端到端产出 ADR-004 bundle，不代表可交易 alpha。

按包含首尾日期的范围幂等补齐公共历史数据：

```bash
uv run python -m apps.ops.backfill_bars \
  --download \
  --start-date 2024-01-01 \
  --end-date 2024-12-31 \
  --symbol BTCUSDT \
  --interval 1m \
  --catalog-path data/catalog
```

`--date` 与范围参数互斥；范围模式不支持 demo signal 或 `--max-rows`，避免把
逐日测试选项误当成全年数据策略。

完整自然月也可使用 Binance 月度归档，减少下载请求数：

```bash
uv run python -m apps.ops.backfill_bars \
  --download --archive-period monthly \
  --start-date 2024-01-01 --end-date 2025-12-31 \
  --symbol ETHUSDT --interval 1m \
  --raw-output-dir data/raw/binance/spot/monthly/klines \
  --catalog-path data/catalog
```

月度模式拒绝不完整自然月，重复运行会复用已有 ZIP 并按 Nautilus 的确定性
catalog 文件名幂等写入。

下载后使用只读 `catalog_audit` 同时检查精确行数、时间边界、重复、缺口、OHLCV
fingerprint 和跨资产时间戳对齐；任一条件失败时 CLI 返回非零：

```bash
uv run python -m apps.ops.catalog_audit \
  --catalog-path data/catalog \
  --bar-type BTCUSDT.BINANCE-1-MINUTE-LAST-EXTERNAL \
  --bar-type ETHUSDT.BINANCE-1-MINUTE-LAST-EXTERNAL \
  --bar-type SOLUSDT.BINANCE-1-MINUTE-LAST-EXTERNAL \
  --start-date 2024-01-01 --end-date 2025-12-31
```

Binance Spot archive 在 2025-01-01 起把 kline 时间戳从毫秒切换为微秒；
importer 会按数值量级检测 ms/us（并防御性接受 ns），拒绝混合或不合理单位。

对已完成的 backtest/paper bundle 做被动成本审查：

```bash
uv run python -m apps.ops.alpha_review \
  --candidate walkforward=data/backtests/<run-id-1> \
  --candidate walkforward=data/backtests/<run-id-2> \
  --blind-start 2024-08-01 \
  --blind-end 2024-12-31 \
  --catalog-path data/catalog \
  --bar-type BTCUSDT.BINANCE-1-MINUTE-LAST-EXTERNAL \
  --markdown
```

`alpha_review` 固定重算 gross、base（10 bps fee + 2 bps slippage）和 stress
（10 + 5 bps）情景，输出 `alpha.review.v1`。它不启动 Nautilus、不写信号、
不加载凭证、不改 `SourcePolicy`，也不恢复 testnet continuity。

`strategy_tournament` 被动聚合每个策略的四份严格 `alpha.review.v1` 开发折，
校验 source/model 和窗口一致性，并应用总成本收益、正收益折、正收益月份、样本量、
移除最佳单笔、Spot-only 与复现闸门。它只对完整通过者排序，不运行回测或修改交易状态。

多资产研究先对每个 symbol 产生严格 `alpha.review.v1`，再由
`apps.ops.multi_asset_review` 汇总成本与月度 PnL，并从原始 lineage 验证同一时刻
最多持有一个资产。输出 `multi_asset.review.v1` 可交给同一个
`strategy_tournament`；12-29 个仓位的低频经济通过者只进入历史证据 watchlist，
不会被排名或进入 paper。

Research Protocol v2 在接触真实独立因子前锁定三名候选、证据分区、成本、参数、
数据字段和淘汰闸门。验证器对日期漂移、阈值变更、候选身份漂移、候选数量增加及
反多重试验保护关闭全部 fail closed：

```bash
uv run python -m apps.ops.research_protocol_v2
```

该命令只读预注册 JSON 并输出 canonical SHA-256；不读取因子数据、收益、凭证或
SignalStore，不运行 Nautilus，也不修改 SourcePolicy。

预注册提交后，使用无凭证的一次性 collector 保存 July 2026 provider
qualification 快照。每份响应保留原始 payload、请求 URL、payload SHA-256、
snapshot SHA-256 和 vintage id；同一文件名禁止覆盖：

```bash
uv run python -m apps.ops.research_v2_snapshot --kind options
uv run python -m apps.ops.research_v2_snapshot --kind basis
uv run python -m apps.ops.research_v2_snapshot \
  --kind stablecoin --start-date 2026-07-01 --end-date 2026-07-10
```

这些快照只能审计 schema、覆盖率、发布时间和 lineage；collector 明确记录
`pnl_computed=false`，不会派生收益或信号。Deribit 当前曲面、Binance 最近30天
basis 和 Coin Metrics 当前可修订历史都不能单独证明 2020-2022 point-in-time
复制集。

Qualification 已确认 Community tier 不提供 USDT 1d `TxTfrValUSD`。稳定币
collector 因此保持 fail closed，直到取得该锁定指标的许可 point-in-time 数据；
不得因为 `TxCnt` / `AdrActCnt` 免费可用就替换预注册的传输金额机制。

生成 Phase 4 只读 dashboard snapshot（JSON 默认输出到 stdout）：

```bash
uv run python -m apps.ops.dashboard_snapshot \
  --project-status-path docs/project-status.md \
  --agent-advice-db data/agents/advice.db
```

默认 snapshot 还会带只读 `reference_links`：

- 本地 Grafana：`http://127.0.0.1:3000/d/signals-overview/signals-overview`
  和 `http://127.0.0.1:3000/d/canary-current/canary-current`
- 对应源文件：`infra/grafana/dashboards/*.json`
- 当前状态、ADR、证据 ledger、runbook 的本地源路径

snapshot 也会携带 `snapshot_freshness` 策略：默认 15 分钟进入 aging、60 分钟
进入 stale，可用 `--snapshot-warning-after-seconds` /
`--snapshot-stale-after-seconds` 调整。前端只用它显示快照年龄，不会自动刷新或
触发任何 runner。

可用空字符串关闭 Grafana URL，只保留本地源路径；也可以传入仓库浏览基准
URL，让文档路径变成浏览器可打开的只读链接：

```bash
uv run python -m apps.ops.dashboard_snapshot \
  --grafana-base-url "" \
  --repo-browser-base-url https://github.com/Maggyee/Nishiki-Trader/blob/main
```

默认还会被动读取 `data/observability/textfile/*.prom`，把 Prometheus textfile
collector 中的最近 runner 心跳、WS 状态、open orders / positions、alert 计数和
bar / signal 数据延迟压缩到 `observability` 字段。可用空字符串关闭：

```bash
uv run python -m apps.ops.dashboard_snapshot \
  --observability-textfile-dir "" \
  > data/frontend/dashboard-snapshot.json
```

也可以追加已完成的 passive bundle reports 作为压缩摘要输入：

```bash
uv run python -m apps.ops.dashboard_snapshot \
  --testnet-bundle data/testnet/<run_id> \
  --paper-bundle data/paper/<run_id> \
  --markdown
```

`dashboard_snapshot` 只读取 `docs/`、AgentAdvice SQLite、既有 paper/testnet bundle
report reader、Prometheus textfile `.prom`、以及静态链接配置；不写
`SignalEvent`、不改 `SourcePolicy`、不读取交易所凭证。

当传入 paper/testnet bundle 时，snapshot 还会从 passive report 的
`signal_lineage` 汇总出只读 `signal_summary`：source/model 分布、accepted /
skipped 计数、以及 expired / unauthorized / signal_lag / kill_switch /
data_gap 等 rejection 原因。该摘要来自已落盘证据，不重新消费 SignalStore。
`signal_summary` 同时携带每个 run 与 source/model 的首尾 `ts_event`、最新
信号年龄、最新 run id、以及 source/model 证据链接，用于前端只读展示
source/model freshness 与证据 drill-down。证据链接只指向 Grafana read-only
source/model 过滤视图、已附加的本地 bundle 路径和既有证据文档；不会触发
runner、写 `SignalEvent` 或修改 `SourcePolicy`。

也可以附加已保存的 Phase 6 passive gate JSON artifact，让 dashboard 只读展示
readiness/startup guard 阻塞状态：

```bash
uv run python -m apps.ops.dashboard_snapshot \
  --phase6-live-readiness-report docs/retros/<readiness-report>.json \
  --phase6-live-startup-guard-report docs/retros/<startup-guard-report>.json \
  > data/frontend/dashboard-snapshot.json
```

这些参数只读取 `phase6.live_readiness.v1` 和
`phase6.live_startup_guard.v1` JSON 文件并压缩到 `phase6` 字段；不会生成报告、
不会运行 `live_readiness` 或 `live_startup_guard`，也不会授权 live trading。

生成 Phase 6 只读 live-readiness gate（默认会阻塞，因为 ADR-013 仍是 Draft，
且 14 天 testnet continuity 仍未满足）：

```bash
uv run python -m apps.ops.live_readiness \
  --source freqai_linear_v1 \
  --model-version linear-mom-train20240105 \
  --starting-capital-usdt 100 \
  --markdown
```

`live_readiness` 只读取项目状态、ADR-013、可选的已完成 testnet bundle
continuity evidence、可选 promotion review artifact、以及显式声明的起步资金；
不读取 live/testnet 凭证、不启动 Nautilus、不写 `SignalEvent`、不改
`SourcePolicy`、不下单，也不授权 live trading。

当 Phase 6 证据最终齐备时，把 JSON 输出保存成 operator 审计材料，再交给
`apps.strategies_nautilus.runners.live_startup_guard` 做未来 live runner 的启动前
拒绝校验。当前仓库默认仍会阻塞，因为 ADR-013 是 Draft，14 天 continuity 未满足，
没有 live-canary promotion review，且 first-live-day runbook 仍是 Draft。

## 计划脚本

| 脚本 | 用途 | 最早 Phase |
|---|---|:-:|
| `emergency_flatten.py` | 应急一键平仓 + 停策略 | 3 |
| `daily_health.py` | 每日健康检查（数据延迟 / 服务存活 / 仓位漂移） | 1 |
| `backfill_bars.py` | 从 Binance public klines 导入 K 线到 ParquetDataCatalog | 1 |
| `alpha_review.py` | 被动成本情景、月度 alpha 闸门与复现审查 | 2 |
| `catalog_audit.py` | 被动检查 catalog 完整性、fingerprint 与跨资产对齐 | 2 |
| `multi_asset_review.py` | 聚合单标成本审查并验证组合持仓互斥 | 2 |
| `backfill_funding.py` | 下载并校验固定 USD-M 月度 funding 公共归档 | 2 |
| `feature_audit.py` | 审计 Spot 主动流/funding 完整性和 fingerprint | 2 |
| `daily_archive_audit.py` | 审计日线 warm-up/信号归档完整性与跨资产对齐 | 2 |
| `research_program_review.py` | 校验累计候选注册表并执行反多重试验停止规则 | 2 |
| `research_protocol_v2.py` | 校验独立机制预注册、证据分区和不可调参数 | 2 |
| `research_v2_snapshot.py` | 保存无凭证 provider qualification 不可变快照 | 2 |
| `signal_replay.py` | 重放 SQLite 中的历史 signals 跑回测 | 1 |
| `migrate_sqlite_to_pg.py` | Phase 2 数据迁移 | 2 |
| `dashboard_snapshot.py` | Phase 4 只读 AgentAdvice / report snapshot | 4 |
| `live_readiness.py` | Phase 6 只读 live-risk gate / blocker report | 5 |
| `testnet_handoff.py` | testnet ↔ live 切换前的检查清单 | 6 |

## 跑法

```bash
uv run python -m apps.ops.daily_health
uv run python -m apps.ops.emergency_flatten --confirm I_REALLY_MEAN_IT
```

## 边界

- 应急脚本必须有**二次确认**参数，避免误触发
- 任何写真实账户的脚本（Phase 6+）走 `EMERGENCY_*` 前缀，醒目
- Phase 2 ops 脚本只能写本地 `data/`，不能接真实账户或下单 API
