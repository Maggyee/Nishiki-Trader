# ADR-007：paper trading runtime 与 SourcePolicy 升档

- **状态**：Accepted
- **日期**：2026-05-17
- **作者 / 维护者**：nishiki（个人开发者，唯一负责人）
- **范围**：`kind="paper"` 的运行语义、结果落盘、从 backtest 到 paper/testnet/live 的 `SourcePolicy` 升档规则
- **依赖**：
  - ADR-001（技术栈、五条铁律、资金阶梯、5% 单日亏损停机）
  - ADR-002（`SignalEvent v1` 是唯一允许的研究信号桥）
  - ADR-004（`run_manifest.json.kind` 已预留 `backtest | paper | live`）
  - ADR-005（`source` 家族命名与新信号源 baseline 流程）
  - ADR-006（`SourcePolicy`、position multiplier、dry-run）
- **复审周期**：第一个 paper session bundle 落盘后复审；Phase 3 testnet 前必须复审一次

---

## 1. 背景

Phase 2 已经能把 catalog-backed 历史数据、`SignalStore` 中的
`SignalEvent v1`、NautilusTrader strategy/risk path 串成可重放 backtest。
第一个 `freqai_*` 源 `freqai_linear_v1 / linear-mom-train20240105` 也已经用
`SourcePolicy(position_pct_multiplier=0.2, dry_run=True)` 记录了 dry-run
fingerprint。

下一步不能直接跳到 Binance testnet 或真实账户。需要先定义一个 paper runtime：

- 让同一条 `SignalEvent v1 -> NautilusTrader Strategy -> RiskEngine` 路径在前向运行中被观察；
- 让新模型可以先 shadow / dry-run，再模拟下单；
- 保留 ADR-004 的 bundle 与 manifest 可审计格式；
- 明确何时允许 `SourcePolicy` 从 `dry_run=True` 升到 paper 模拟订单，再进入 testnet；
- 继续禁止 LLM、freqtrade、FreqAI 直接进入真实订单路径。

本 ADR 是运行语义和升档规则，不启用真实交易、不添加 API keys、不引入新服务。

---

## 2. 决策

### 2.1 `kind="paper"` 的定义

`paper` 是**前向运行的模拟交易**：

```text
SignalEvent v1
  -> NautilusTrader Strategy
  -> RiskEngine / hard gates
  -> simulated execution account
  -> ADR-004-compatible paper bundle
```

约束：

- 不允许使用真实交易账户。
- 不允许提交真实订单。
- 不允许读取 gitignored secrets 或真实 exchange API keys。
- Phase 2 允许第一版 `kind="paper"` 使用本地 catalog polling / replay 做
  **simulated paper session**，前提是 `runtime.data_mode="catalog_polling"`、
  `runtime.order_mode="simulated"` 且不接真实交易所。它只能验证 bundle、lineage、
  policy、risk gate 和模拟撮合链路；不能单独作为升 testnet/live 的证据。
- 真正可用于升 testnet 的 paper 必须是持续进程，按墙钟消费新 market events /
  signals，并在 manifest 的 `runtime.data_mode` 中与 catalog polling 区分开。
- 初期数据源继续优先 SQLite `SignalStore` + 本地/public market data。Redis Stream
  只有在 SQLite polling 暴露实际瓶颈后再引入。

### 2.2 与 backtest / testnet / live 的边界

| kind | 数据时间 | 订单去向 | 允许资金 | 目的 |
|---|---|---|---:|---|
| `backtest` | 历史 catalog，加速或离线 | Nautilus backtest engine | 0 | 可重放策略评估 |
| `paper` | catalog polling 或前向墙钟 | 模拟账户 / 模拟撮合 | 0 | 观察运行稳定性、信号新鲜度、risk gate 行为 |
| `testnet` | 前向墙钟 | Binance testnet adapter | 0 | 验证交易所连接、API 限流、重启恢复 |
| `live` | 前向墙钟 | Binance live adapter | ADR-001 资金阶梯 | 小钱实盘，严格风控 |

`paper` 不是 `testnet`。Paper simulated bundle 通过只说明本地链路可审计；墙钟
paper 通过之前，禁止添加真实 exchange credentials；testnet 通过之前，禁止 live。

### 2.3 Paper bundle 格式

Paper runtime 复用 ADR-004 bundle 思路，落盘在：

```text
data/paper/<run_id>/
├── run_manifest.json
├── orders.parquet
├── fills.parquet
├── positions.parquet
├── account_balances.parquet
├── signal_lineage.parquet
└── logs/
    ├── strategy.log
    └── risk.log
```

`run_manifest.json` 使用 `schema_version="backtest.v1"`，`kind="paper"`。
ADR-004 的 `backtest_start` / `backtest_end` 在 paper 中表示本次 session
处理到的 first / last market event time，而不是墙钟启动/结束时间。墙钟时间仍
写入 `started_at` / `finished_at`。

Paper manifest 允许追加一个 `runtime` 对象：

```json
{
  "runtime": {
    "mode": "paper",
    "data_mode": "catalog_polling",
    "order_mode": "simulated",
    "heartbeat_interval_seconds": 30,
    "heartbeat_count": 10080,
    "polling_mode": "incremental",
    "poll_interval_seconds": 60,
    "poll_batch_size": 1,
    "poll_count": 10080,
    "processed_until_ns": 1704671940000000000,
    "max_signal_lag_seconds": 120,
    "data_gap_tolerance_intervals": 1,
    "data_gap_count": 0,
    "data_gaps": [],
    "restart_sequence": 0,
    "operator": "nishiki"
  }
}
```

`runtime` 是追加字段，不改变 `backtest.v1` 的既有字段。未来若字段需要强校验，
在 `apps/strategies_nautilus/result_schema.py` 追加兼容模型字段，不升
`backtest.v2`。

### 2.4 Session 写入规则

Paper session 是运行中的目录，结束后才视为不可变。

要求：

- 启动时记录 `git_commit` / `git_dirty`。`git_dirty=true` 的 paper session 不能
  用作升档依据。
- 每个被消费的 signal 必须写入 `signal_lineage.parquet`，包括 rejected、
  expired、dry-run、simulated-order。
- Paper 模拟订单也必须保留 `signal_id` 到 orders / fills / positions。
- 日志必须能区分 strategy decision、risk rejection、runtime heartbeat。
- 运行中断重启不能复用同一个 `<run_id>` 追加覆盖；要新建 session，并在日志或
  manifest runtime 字段记录 `previous_run_id`。
- Catalog polling paper runtime 必须按 event-time cursor 增量处理 bars/signals，
  在 `logs/heartbeat.jsonl` 和 `logs/runtime.log` 写 heartbeat / poll 记录，并在
  manifest runtime 字段记录 `processed_until_ns`，用于下一次 session 续跑。
- 使用 `previous_run_id` 续跑时，如果上次 manifest 可读，runner 必须从上次
  `processed_until_ns + 1` 自动设置 catalog / signal cursor，并记录
  `previous_manifest_sha256`、`restart_sequence`、`restart_reason` 等审计字段。
- 检测到 market-data gap 时必须记录 `data_gap` runtime 事件；gap 内的开仓/翻仓
  signal 必须跳过并进入 review blocker，不能作为升档依据。

### 2.5 SourcePolicy 升档表

升档只针对单一 `(source, model_version)`。不同 source/model 不互相继承成绩。

| 阶段 | 默认 policy | 最高 multiplier | 进入下一档前置 |
|---|---|---:|---|
| backtest baseline | 可按研究需要设置，但必须记录 manifest | 1.0 | ADR-005 fingerprint 已记录；重放无漂移 |
| paper shadow | `dry_run=True` | 0.2 | ≥ 7 天或 ≥ 50 条 signals；无 schema/auth/freshness 批量异常 |
| paper simulated | `dry_run=False` | 0.2 | shadow 通过；simulated fills/positions/lineage 完整；kill-switch 未被真实触发 |
| testnet canary | `dry_run=False` | 0.2 | paper simulated ≥ 7 天稳定；人工复盘通过；Phase 3 testnet runbook 就绪 |
| live canary | `dry_run=False` | 0.1 | testnet 连续 14 天不需手动干预；ADR-001 资金阶梯从 100-500 USDT 开始 |
| live normal | `dry_run=False` | 1.0 | 真实小钱阶段满 30 天，不亏到本金一半；之后按连续 3 个月正收益才加资金 |

说明：

- multiplier 乘在策略级 `max_position_pct` 上，不替代全局仓位上限。
- 任何阶段触发 5% 单日亏损 kill-switch，自动降回 `dry_run=True` 或停用 source，
  直到人工复盘。
- `min_confidence_override` 只能收紧，不允许用升档流程放宽策略默认值。
- LLM family (`llm_*`) 在单独的 LLM SignalEvent 升档 ADR 落地前最高只能停留在
  `paper shadow`，且默认 `dry_run=True`。ADR-009 只允许 LLM/agent 输出写入
  AgentAdvice，不授权进入信号桥。

### 2.6 Promotion review checklist

每次升档必须在 PR / commit / retro 里记录：

1. `(source, model_version)`。
2. 当前 policy 与目标 policy。
3. 最近 backtest/paper/testnet bundle 路径与 manifest fingerprint。
4. signal rows、accepted/rejected/expired 数、lineage decisions。
5. fills、positions、PnL、最大回撤、kill-switch 状态。
6. 是否存在 manual intervention、runtime restart、data gap。
7. 明确结论：升档、保持、降档、停用。

没有这些材料，不允许把 `SourcePolicy.dry_run` 从 `True` 改为 `False`，也不允许提高
`position_pct_multiplier`。

### 2.7 降级行为

Paper/runtime 层的默认降级：

| 故障 | 行为 |
|---|---|
| 无新 signal | 不开新仓；已有 paper position 按策略规则管理 |
| signal lag 超过 `max_signal_lag_seconds` | 拒绝新开仓，只允许 flat / reduce-risk |
| SignalStore 不可读 | 停止消费并报警；不复用过期信号 |
| market data gap | 暂停模拟撮合，记录 `data_gap`，不升档 |
| policy config 缺失 | 默认 `SourcePolicy(dry_run=True, position_pct_multiplier=0.0)` |
| kill-switch 触发 | 停止新开仓；记录 runbook action；该 source 降档 |
| agent 输出异常 | 不进入 signals，只写未来 AgentAdvice 审计表 |

### 2.8 明确不做

- 不在本 ADR 启动 live trading。
- 不添加真实 Binance API key、secret、配置模板或交易权限。
- 不引入 Redis/Postgres 作为 paper 的前置条件。
- 不让 freqtrade/FreqAI 直接管理 paper/live orders。
- 不让 LLM agent 修改 `SourcePolicy` 或授权列表。
- 不把 `SourcePolicy` 写进 `signals` 表；policy 仍是消费侧配置。
- 不把 paper 的模拟正收益当作实盘盈利证据；它只验证运行稳定性和审计链路。

---

## 3. 验证标准

后续实现 paper runtime 时必须满足：

1. `run_manifest.json.kind == "paper"`，且 manifest 保留 ADR-004 必填字段。
2. Paper bundle 写在 `data/paper/<run_id>/`，`data/` 仍 gitignored。
3. 测试覆盖：paper runtime 不读取真实 API key，不实例化 live exchange adapter，不提交真实订单。
4. 测试覆盖：`dry_run=True` 的 source 只写 lineage，不写 paper orders/fills。
5. 测试覆盖：`dry_run=False` 的 paper simulated source 写 orders/fills/positions，且都带 `signal_id`。
6. 测试覆盖：signal lag、expired signal、unauthorized source/model、kill-switch 都会阻止新开仓。
7. 文档覆盖：runbook 增加 paper session 启停、故障、降档流程。

---

## 4. 后续 ADR

- **ADR-008**：Phase 3 风控、testnet runtime 与运行手册。已起草（Draft），
  规定 `paper_simulated → testnet_canary` 升档前的 testnet runtime、真实
  exchange credentials 管理、emergency flatten、重启恢复和报警。
  运行时实现按其 §6 路线分子阶段进行，
  `promotion_review` 的 `phase_3_not_ready` gate 不放开直到 §6 子阶段全部
  完成。
- **ADR-009**：AgentAdvice 审计与 LLM 隔离。定义 AgentAdvice 与 SignalEvent
  的隔离表；`llm_*` 是否能从 paper shadow 升到 simulated 仍需未来单独 ADR。
- **ADR-010**：Redis Stream 桥接通道。Draft 已写于 2026-05-21
  （`docs/decisions/010-redis-stream-signal-transport.md`），定义触发条件、
  消息拓扑、迁移路径与验收清单。**实现 0 行**，等 §2 触发条件任一为真后
  才落地。

---

**Decided. `kind="paper"` 是真实账户之前的前向模拟运行层；它复用
`SignalEvent v1`、NautilusTrader strategy/risk path、ADR-004 bundle 格式和
ADR-006 `SourcePolicy`。任何 source/model 从 backtest 升到 paper/testnet/live
都必须按本 ADR 的 policy 阶梯、promotion checklist 和降级规则执行。**
