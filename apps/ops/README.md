# ops

运维脚本。

**当前 Phase**：2（catalog fixture / backtest operations）+ Phase 4/5 read-only
dashboard snapshot support + Phase 6 passive readiness gate support。

## 当前入口

`portfolio_installed_snapshot_book` 先回放受保护 v14 原始证据，再于普通
项目进程重建 Nautilus 原生 L2 盘口。只有所有标的双侧盘口、修订顺序、深度
覆盖及时间年龄都通过才输出历史 QuoteTick；当前安装夹具有效增量删除了
唯一买档，因此无报价。无凭证、网络或执行入口。见
[历史盘口重建](../../docs/progress/portfolio-installed-snapshot-book-2026-09-24.md)。

`portfolio_installed_joint_handoff` 按显式 SHA256 只读回放已安装 v14
快照夹具的原始六次读取及并发账户/市场/深度归档，对照完整联合采集预算输出
缺项和阻断结论。既不执行采集，也不授予真实网络或交易权限。见
[安装夹具交接审查](../../docs/progress/portfolio-installed-joint-handoff-2026-09-24.md)。

`portfolio_egress_ledger --ipc-profile` 仅重放安装隔离验收中的多操作 IPC 账本。
准备/确认记录不代表交易所请求、内核放行或真实额度，退出码仍为 2。
见 [专用 UID IPC 验收](../../docs/progress/portfolio-installed-joint-ipc-2026-09-17.md)。

`portfolio_joint_observation --tls-loopback-profile` 可配合 `--attempt-ledger`
和 `--attempt-ledger-sha256` 交叉回放完整联合采集及逐项消耗。
`portfolio_egress_ledger --joint-profile` 单独审查失败/中断的联合尝试账本，
仍以退出码 2 表示无网络准入。两者均无采集入口。
见 [联合采集记账验收](../../docs/progress/portfolio-joint-egress-accounting-2026-09-17.md)。

`portfolio_egress_ledger` 仅离线回放指定 SHA256 的本地尝试日志，保留失败、
不确定结果和已观察缺口；可显式指定成对的单调时钟区间。退出码 2 表示报告
已写入，但不授予网络准入；无创建、恢复或发送模式。见
[本地出口尝试账本](../../docs/progress/portfolio-egress-attempt-ledger-2026-09-17.md)。

`portfolio_joint_reservation` 仅重放显式选择的离线逐步预留验收日志，
重新验证每一步签名、剩余预算和已准备消耗，保留中断后的待决步骤。
返回 2 表示报告已写入；不预留真实网关额度、不激活采集。见
[离线逐步预留验收](../../docs/progress/portfolio-testnet-joint-reservation-2026-09-15.md)。

`portfolio_joint_attestation` 离线验证显式选定的来源/网关签名及证据哈希，
持久化新的私有报告。返回 2 表示签发者验证完成但网络准入仍被拒绝；
报告不会预留额度或激活一次性采集。输入与信任边界见
[联合证据签名验收](../../docs/progress/portfolio-testnet-joint-attestation-2026-09-15.md)。

`portfolio_joint_admission` 离线检查首个请求的额度与出口证据缺口；重新解析
原始额度字段并计算完整 17 GET / 468 权重和连接预算。缺少或仅有自报证据时
返回码为 2（已写报告、准入拒绝），不加载凭证、发送请求或激活采集。
输入格式与认证边界见 [联合准入检查](../../docs/progress/portfolio-testnet-joint-admission-review-2026-09-14.md)。
新增 `--bootstrap-plan/events/response` 及对应 SHA256 可接入已完成采集的原始
归档；按首次完整响应头落盘时间检查计数时效，保留实际字段和未满足条件，
不把完整正文接收或重放时间作为新样本时间。此模式与 candidate 互斥。
见 [真实 bootstrap 联合准入复核](../../docs/progress/portfolio-bootstrap-joint-review-2026-09-16.md)。

`portfolio_tls_provenance` 按原始哈希离线回放本机 TLS/Upgrade 来源归档，
验证原始字节、证书记录、准备/关闭顺序，写入新的私有报告；没有采集或凭证选项。
本机信任不等于交易所或共享出口认证。见
[TLS 来源证据验收](../../docs/progress/portfolio-testnet-tls-provenance-2026-09-14.md)。

`portfolio_joint_observation` 只重放显式哈希选择的合成联合归档，输出私有
原生行情/全账户报告。显式 `--loopback-profile` 重放独立的原生本机传输
归档并重算原始路由；`--tls-loopback-profile` 则从独立 TLS 归档的原始字节
重建消息并验证来源与关闭顺序。两个选项互斥，默认仍为旧合成 profile。
没有采集模式，不加载凭证或启动交易。见
[联合 TLS 传输验收](../../docs/progress/portfolio-testnet-joint-tls-transport-2026-09-14.md)、
[联合传输验收](../../docs/progress/portfolio-testnet-joint-transport-2026-09-14.md) 与
[联合日志验收](../../docs/progress/portfolio-testnet-joint-observation-acceptance-2026-09-14.md)。

`portfolio_testnet_observation_plan` 重放原始账户、市场和 v2 深度归档，生成
三枢纽路由覆盖、完整请求预算及独立观察区间的私有规划报告。零网络请求，
不授权联合采集；原始输入和下一步入口见
[联合观察设计](../../docs/progress/portfolio-testnet-joint-observation-design-2026-09-13.md)。

`portfolio_market_depth` 提供独立 BTCUSDT 公开深度诊断和显式哈希历史重放。
一次探针最多五个 GET、一个原生 WebSocket，零重试/重连；不读取 Key 或账户。
默认使用 v1；新版首段衔接和归档均须显式选择 `--revision 2`，依据见
[v2 合同](../../docs/progress/portfolio-testnet-public-depth-v2-contract-2026-09-13.md)。
[v2 单次实测](../../docs/progress/portfolio-testnet-public-depth-v2-2026-09-13.md)
已完成 20 条原生报价与两个独立重放；该单次范围已消耗。
原始响应先落盘，闭合归档通过快照/增量/时钟检查后才能重放原生 QuoteTick。
实现、单次探针结果与边界见
[公开深度验收](../../docs/progress/portfolio-testnet-public-depth-2026-09-13.md)。

`portfolio_testnet_observe` 是有时限的 Binance Spot 测试网全账户只读观察入口：
显式选择 Ed25519 配置、初始账户观察及哈希、新建私有归档；执行两次签名订阅、
四轮全资产/账户级挂单读取及心跳检查，断线后拒绝旧连接凭据，最后回放归档。
不启动执行引擎，权限未知、基线未认证及 `runtime_ready=false` 始终保留。
命令和真实测试网证据见
[测试网全账户观察与重连](../../docs/progress/portfolio-testnet-observation-2026-09-11.md)。

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

Research Protocol v3 以同样方式锁定三名新的宏/原生机制候选（算力恢复、DXY
走弱、VIX 回落），并明确不重开 v1 拒绝族或 v2 被阻塞数据通路：

```bash
uv run python -m apps.ops.research_protocol_v3
```

该命令只读预注册 JSON 并输出 canonical SHA-256；不读取因子数据、收益、凭证或
SignalStore，不运行 Nautilus，也不修改 SourcePolicy。

Research Protocol v5 的 Binance 原生快照 CLI 对范围下载逐 UTC 日 fail closed：
checksum、404、日内缺口或 schema 失败的日期不写快照并记录
`desired_state=flat`，但不会阻止后续有效日期被不可变保存。只要存在失败日，范围
命令最终仍返回非零；调用方必须保留 JSON failure ledger，不能把部分成功误报为
完整覆盖：

```bash
uv run python -m apps.ops.research_v5_snapshot \
  --kind delivery_curve --asset BTCUSDT \
  --start-date 2021-06-01 --end-date 2022-12-31 \
  --download
```

Spot 执行数据必须先走同一个 `research.raw_snapshot.v2` 不可变 envelope，再由
离线复验通过且无 vintage conflict 的 ZIP 导入 v5 Nautilus catalog。每个 UTC 日
必须恰好有 1,440 个分钟格；checksum、时间戳或 OHLCV 失败的日期不会写入 catalog：

```bash
uv run python -m apps.ops.research_v5_snapshot \
  --kind spot_execution --asset BTCUSDT \
  --start-date 2023-08-01 --end-date 2023-12-31 \
  --download \
  --catalog-path data/research-v5/spot-catalog
```

Curve/BVOL collector 不会导入 Nautilus，因而云端只读日采集仍不需要交易引擎
依赖；Nautilus 导入仅在显式选择 `spot_execution` 时延迟加载。

若某个锁定评分折的 Spot 执行 catalog 在信号/PnL 前已确定不完整，使用结构化
`research.v5.data_blocker.v1` 证据直接生成 fail-closed v5 review；不得用空回测
或补值伪造 fold report：

```bash
uv run python -m apps.ops.research_v5_review \
  --phase curve_fast_track \
  --data-blocker curve_carry=data/research-v5/reports/curve-data-blocker.json
```

该模式固定输出候选 `reject_v5_candidate`、总建议
`stop_before_testnet_resume` 和 `pnl_evaluated=false`，也不会启动 Nautilus。

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

成功采集后必须离线重算原始响应、解析结果、audit 摘要、envelope、vintage id
和文件名中的全部哈希；缺少 exact-byte base64 的早期草稿不合格：

```bash
uv run python -m apps.ops.research_v2_snapshot \
  --verify data/research-v2/raw/<snapshot>.json
```

已验证的 basis 快照可转换为候选 generator 的 point-in-time CSV。转换器把
`ts_event` 延后到抓取后的下一 UTC 日界，拒绝重复日、缺日、未来 observation、
篡改快照和覆盖写入；qualification 先用 `--dry-run`，不落文件、不生成信号：

```bash
uv run python -m apps.ops.research_v2_factors \
  --basis-snapshot data/research-v2/raw/<verified-basis-snapshot>.json \
  --dry-run
```

只有连续多日快照齐备后才允许写 `--output-csv`。输出仍是 factor 输入，不是
SignalEvent，也不计算 return/PnL 或运行 Nautilus。

期权和 basis 必须逐日成对积累。Coverage reviewer 固定要求至少7个连续 UTC
日期，每个 kind 每日恰好一份；缺日、重复日、非配对日期或任一快照篡改都会阻塞：

```bash
uv run python -m apps.ops.research_v2_snapshot_review \
  --snapshot data/research-v2/raw/options-<day1>.json \
  --snapshot data/research-v2/raw/basis-<day1>.json
```

不足7天时只返回 `collecting_insufficient_days`。该 reviewer 不汇总价格、不加载
returns、不生成 signals，也不计算 PnL。

在打开2020-2022 basis 历史 ZIP 前，先审计 Binance 官方 S3 key/size 元数据：

```bash
uv run python -m apps.ops.research_v2_archive_availability
```

该 gate 只调用 S3 LIST metadata，不读取 ZIP/CHECKSUM 正文。当前结果为
`blocked_incomplete_historical_reserve`：BTCUSD index 1d 月归档从2020-06才开始，
锁定的2020-01～05及校验和不存在。禁止把半个2020算作完整年份、改用已打开的
2023补足，或在 gate 失败后下载价格正文。

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
| `research_protocol_v3.py` | 校验宏/原生机制预注册、证据分区和不可调参数 | 2 |
| `research_protocol_v5.py` | 校验 Binance 原生双资产候选、分区、闸门和指纹 | 2 |
| `research_protocol_v7.py` | 校验 Cboe VIX/OVX/GVZ 候选、分区、闸门和不可调参数 | 2 |
| `research_v2_snapshot.py` | 保存无凭证 provider qualification 不可变快照 | 2 |
| `research_v2_factors.py` | 把已验证 basis 快照转换为无收益 point-in-time 因子 | 2 |
| `research_v2_snapshot_review.py` | 审计期权/basis 多日配对、缺口、重复和篡改 | 2 |
| `research_v2_archive_availability.py` | 在读取价格前审计 basis 历史归档元数据覆盖 | 2 |
| `research_v5_snapshot.py` | 下载/校验不可变 curve/BVOL 归档、checksum、审计和 Parquet | 2 |
| `research_v5_daily.py` | 从锁定干净 commit 执行四路只读日采集 | 2 |
| `research_v5_review.py` | 汇总 v5 folds、成本、风险、benchmark 与固定结论 | 2 |
| `research_v7_snapshot.py` | 保存并离线复验 Cboe 历史 CSV、生成 point-in-time 因子 | 2 |
| `research_v7_review.py` | 汇总 v7 重复回放、年度/月度成本门槛和执行数据阻塞项 | 2 |
| `research_v7_downtime_sensitivity.py` | 生成隔离的零量停机占位 catalog，仅用于 v7 事后敏感性分析 | 2 |
| `research_protocol_v8.py` | 校验 GVZ 2023–2025 独立确认协议与数据源锁 | 2 |
| `research_v8_execution.py` | 下载并校验官方 Binance 月包，按 REST 证据审计停机窗口 | 2 |
| `research_v8_factor.py` | 从冻结 Cboe vintage 构建 v8 point-in-time GVZ factor | 2 |
| `research_v8_review.py` | 汇总 v8 双重回放并执行固定收益、广度、集中度和 session 门槛 | 2 |
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

`python -m apps.ops.portfolio_execution_plan` 只读重验原始证据并输出固定离线
组合方案。缺少留存数据或证据变化时退出 2，不自动替换策略；退出 0 仅表示
证据锁通过，不是模拟交易、测试网或实盘授权。见
[组合执行契约](../../docs/progress/portfolio-execution-contract-2026-09-09.md)。
默认输出当前资金约束接纳方案 v2；`--revision 1` 可复现原始整批方案。
版本差异见 [v2 接纳规则](../../docs/progress/portfolio-funded-admission-2026-09-09.md)。

`python -m apps.ops.portfolio_venue_check <captured-bundle.json>` 只读解析本地
Binance 规则/手续费响应，输出哈希、约束和不兼容方向；不请求网络、不读取凭证。
退出 0 仅代表解析及手续费兼容性通过，账户对账和运行就绪状态始终为 false。
详见 [交易所适配与输入格式](../../docs/progress/portfolio-venue-adapter-2026-09-09.md)。

`python -m apps.ops.portfolio_downtime_risk_check --help` 提供只读本地停机风险
审核入口，核对原生账户/报价观察与恢复前后检查点，保留期中越线和已有锁存。
退出 0 仅表示所供记录未发现越线，不代表覆盖完整或可以恢复交易；不修改输入、
不加载凭证、不连接网络。输入格式见
[停机风险审核](../../docs/progress/portfolio-downtime-risk-2026-09-10.md)。

`python -m apps.ops.portfolio_account_archive_check --help` 提供本地只读账户归档
复核。显式选择归档 SHA256、采集 ID、来源绑定及独立基线后，复用采集器验证
原始分页响应。退出 0 仅表示历史采集可复现，不表示真实来源验收或可以重启；
输出不含账户响应原文。详见
[账户归档与重放](../../docs/progress/portfolio-account-archive-2026-09-10.md)。

- 应急脚本必须有**二次确认**参数，避免误触发
- 任何写真实账户的脚本（Phase 6+）走 `EMERGENCY_*` 前缀，醒目
- Phase 2 ops 脚本只能写本地 `data/`，不能接真实账户或下单 API


只读测试网全账户复核入口：`apps.ops.portfolio_testnet_account_review`。
它重放指定归档、比较全部资产/挂单/账户字段，并可使用指定的 testnet exchangeInfo
在独立进程中验证完整 Nautilus 余额映射。不会默认猜测未知币种精度或省略资产。
详细输出以 0600 权限独占创建；相等结果和 CLI exit 0 均不代表恢复或交易许可。
实现与私有证据引用见
[全账户映射验收](../../docs/progress/portfolio-testnet-account-mapping-2026-09-11.md)。


测试网观察准入与估值入口：`apps.ops.portfolio_testnet_admission`。
它验证初始账户原始记录、归档和行情快照的关联，记录完整观察起点，计算直接或两跳
USDT 参考估值，并生成固定 0.0001 BTC / 10 测试 USDT 的订单验收草案。
缺价资产保持未知，参考小计不会变成完整权益；日初权益、日亏损和风险上限在未合格
时保持空值。此入口没有执行引擎或下单能力。见
[准入及基线规则](../../docs/decisions/016-testnet-observation-admission.md)和
[本次验收](../../docs/progress/portfolio-testnet-admission-2026-09-11.md)。

独立测试网工程检查：`apps.ops.portfolio_testnet_capabilities` 使用现有 Ed25519
配置，读取完整账户、手续费、myFilters 和有效价格参考。可显式添加
`--validate-order` 调用不进入撮合引擎的 `/api/v3/order/test`；固定
0.0001 BTC、最多 10 测试 USDT，要求本次费率全部为零。
原始账户与校验响应独占写入 0600 本地文件，stdout 只输出脱敏诊断。
`portfolio_testnet_session.py` 保存独立会话规则和校验边界；尚无原生会话账本
或撮合订单 runner，CLI 成功不能放开实盘/组合准入。说明见
[ADR-017](../../docs/decisions/017-testnet-engineering-session.md)。

`portfolio_session_transport`：现有 Ed25519 Key 的限定测试网只读启动/恢复探针。
默认使用固定私有账户会话目录，完整映射原生账户并用新订阅下的签名 GET 对账。
`--checkpoint` 只接受该目录内已有的只读探针快照，不恢复交易或消耗撮合额度。
入口：`.venv/bin/python -m apps.ops.portfolio_session_transport`；后续接入边界见
[验收报告](../../docs/progress/portfolio-testnet-session-transport-2026-09-11.md)。

The bounded ADR-017 matching profile is `portfolio_session_runtime.py`, operated
by `apps.ops.portfolio_session_run --execute` from clean pushed code. It uses one
fixed testnet scope, native risk/strategy/execution, durable single-attempt requests
and timed cancellation. `--recover` is signed GET-only original-ID reconciliation.
See `docs/progress/portfolio-testnet-session-runtime-2026-09-11.md` for limitations;
never delete activation or state to repeat a BUY. Production remains blocked.

`apps.ops.portfolio_session_run --recover-cancel` adds explicit signed recovery
followed only by an original active order's unused cancellation. A terminal order
returns without modifying the fixed checkpoint. Old cancellation intents/attempts
and all BUY allowances stay consumed; new orders remain forbidden. Implementation:
`portfolio_session_cancel_recovery.py`; acceptance/boundaries are documented in
`docs/progress/portfolio-testnet-cancel-recovery-2026-09-11.md`.

`apps.ops.portfolio_session_run --status` inspects the fixed local checkpoint with
no credentials, network or writes. It reports original order IDs, consumed attempts,
recorded ownership and the shared 24-hour history bound. It grants no action and
never equates an old terminal record with current venue confirmation. See the
[fixed-session recovery runbook](../../docs/runbook-testnet-session-recovery.md).

`apps.ops.portfolio_session_archive` reviews explicitly pinned historical session
archives in a fresh standalone process, including after the collection window
expires. `portfolio_session_archive.py` validates the full archive chain, original
checkpoint/collection binding, exact GET receipts and original evidence seal before
native historical reconciliation. Only a new private diagnostic report is written;
no credentials, network, live fence, session writer or execution permission. See
[historical session replay](../../docs/progress/portfolio-testnet-session-archive-2026-09-13.md)
and the [fixed-session recovery runbook](../../docs/runbook-testnet-session-recovery.md).

`apps.ops.portfolio_testnet_baseline_review` replays the five explicitly selected
original account/market/session inputs, compares complete asset-unit deltas after
native fills/fees, and reports UTC/valuation/cash-flow evidence gaps. Run `--help`
for required paths, historical hashes and collection IDs; run the review in a
fresh process. It writes only a new private diagnostic and keeps qualified equity,
losses, baseline and runtime readiness unavailable. See the
[full-account baseline gap review](../../docs/progress/portfolio-testnet-baseline-gap-2026-09-13.md).
