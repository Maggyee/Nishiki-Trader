# ADR-001：技术栈选型与五条铁律

- **状态**：Accepted
- **日期**：2026-05-14
- **作者 / 维护者**：nishiki（个人开发者，唯一负责人）
- **范围**：`/home/nishiki/projects/trader` 全项目，长期（≥ 2 年）
- **复审周期**：每 6 个月一次，retro 时滚动确认

> ADR (Architectural Decision Record) = 把一个重要决策、当时的背景、为什么这样选、放弃了什么、半年后会后悔什么——一次性写清楚。后来的我读这一份文档就能复原当时的判断。

---

## 1. 背景

本项目目标：构建一个 **LLM 多 agent 研究层 + freqtrade ML 信号层 + nautilus_trader 执行层** 的个人量化交易系统，跑在 binance 上，长期演进（≥ 2 年），由**一个人**在业余时间维护。

两个月前画了一张架构图（`/home/nishiki/projects/trader/architecture.png`），上面有十几个方块：决策师 / 数据分析师 / 金融专家 / n8n / MCP / SKILLS / 缓存区 / 学习数据库 / freqtrade / nautilus / 风控 / 应急 / 回测 / 监控 / 前端 / binance。

直接照图实现的话，复杂度对一个人来说是负担不起的。本 ADR 的目的：

1. **锁死一套技术栈**，避免半年后又换。
2. **写下五条铁律**，让未来的我在被新工具诱惑时有一份「劝退自己」的文档。
3. **明确放弃了什么**——这部分比"选了什么"更重要。

---

## 2. 五条铁律

> 任何时候想破坏这五条，先回来读这一节。

### 铁律 1：没赚钱前不优化任何东西

5ms 延迟、k8s、多 agent 协作、分布式消息总线——在策略**还没能稳定带来正期望收益**之前，全部是装饰品。**先证明 alpha 存在，再谈工程化**。

判定标准：策略在真实小钱实盘连续 30 天正期望，才允许做"性能优化"类工作。

### 铁律 2：AI 永远是研究员，不是交易员

任何 LLM 组件（Claude API、agent、MCP 工具）**都不进入订单决策的快路径**。它们只做：

- 研究 / 复盘 / 报告
- 调"参数旋钮"（仓位乘数、风险阈值、策略开关）

LLM 挂掉、抽风、幻觉、API 超时——主交易系统必须能继续按既定规则跑。

### 铁律 3：降级路径先于升级路径

每加一个新组件，**必须先想清楚它挂了会怎样**，并实现降级。

模板：

| 组件 | 挂了会怎样 | 降级行为 |
|---|---|---|
| Claude API | agent 不输出 | 仓位乘数回到 1.0，按裸策略跑 |
| 新闻源 | 没情绪标签 | 偏向回到中性 |
| Redis | 桥接断 | freqtrade 不影响，nautilus 用最后缓存的参数 |
| freqtrade | 没新信号 | nautilus 按 cache 中最后一组参数继续 |
| nautilus | 真的挂了 | Telegram 报警 + 手动登录交易所人工平仓 |

### 铁律 4：不造轮子

下面这四个东西**绝对不自己写**：

- 交易引擎 → nautilus_trader
- 策略 / ML 框架 → freqtrade + freqai
- 时序 / 关系 / 向量数据库 → PostgreSQL + TimescaleDB + pgvector（一个库）
- 回测引擎 → nautilus 的 backtest（快筛用 freqtrade）

**改 upstream 源码也算造轮子**。两个项目都有干净的扩展点（freqtrade 的 `external_message_consumer` + `ProducerPairList`；nautilus 的 `MessageBus` + 自定义 `Actor` / `Strategy`），用扩展点，不 fork。

### 铁律 5：小钱实盘 > 大钱模拟

100 USDT 实盘踩到的坑（滑点、API 限流、网络抖动、交易所维护、手续费计算错误、税务问题），是 100 万 USDT 回测永远遇不到的。

**资金阶梯**（绑死，不允许阶段提前跳）：

| 阶段 | 资金 | 升级前置条件 |
|---|---|---|
| 0：testnet | 0 | — |
| 1：真钱起步 | 100–500 USDT | testnet 连续 14 天不需手动干预 |
| 2：扩张 | 1000 USDT | 阶段 1 跑满 30 天，不亏到本金一半 |
| 3+ | 翻倍 | 连续 3 个月正收益 + 最大回撤可控（≤ 15%） |

**硬规则**：任何阶段，单日亏损达 5% → nautilus risk_engine 自动停机 + Telegram 报警 + 人工复盘后才允许重启。

---

## 3. 技术栈选型

### 3.1 总服务数上限：8 个

为什么有上限：一个人维护 8 个服务已经是极限。每多一个服务，**维护成本是线性增加，调试成本是指数增加**（服务间交互组合数）。

预计的 8 个：

1. `nautilus`（执行引擎）
2. `freqtrade`（ML 信号源 + freqai）
3. `postgres`（含 TimescaleDB + pgvector 扩展，一个库覆盖时序 / 关系 / 向量）
4. `redis`（消息桥 + 缓存 + agent buffer）
5. `n8n`（编排定时任务、复盘流、通知流）
6. `agent-orchestrator`（自写，调 Claude API + MCP，跑 agent）
7. `mcp-server`（自写，给 agent / Antigravity / Claude Code 用的工具层）
8. `frontend`（Next.js，看持仓 / PnL / 日志 / agent 报告）

监控（Grafana / Prometheus / Loki）算 1 个 stack，不单独计数。

### 3.2 选型详表

| 层 | 选 | 不选 | 理由 |
|---|---|---|---|
| 执行引擎 | nautilus_trader | 自己写 / 直接 ccxt | Rust 核 + 现成 binance adapter + 内置 risk_engine + 事件驱动 |
| 策略 / ML | freqtrade + freqai | 自己写 ML pipeline | RL / XGB / LGBM 框架开箱即用，社区策略多 |
| 数据库（阶段 0/1） | **SQLite + 本地 Parquet 文件** | 一上来就 PG | 数据模型未稳定前不引入长驻数据库服务（见 contract §7） |
| 数据库（阶段 2+） | **PostgreSQL + TimescaleDB + pgvector** | Qdrant + InfluxDB + Mongo | 一个 PG 搞定时序 + 关系 + 向量，少 2 个服务 |
| 消息 / 缓存 | Redis（含 Stream） | Kafka / NATS / RabbitMQ | 个人项目，Redis Stream 完全够用 |
| 编排 | n8n（自托管） | Airflow / Prefect / Dagster | 拖拽友好，写少量代码就能跑通定时任务 |
| LLM | Claude API + prompt caching | 本地 LLM / 多家混用 | 本地模型在个人时间成本下不划算；多家混用调试地狱 |
| Agent 框架 | Anthropic SDK 原生 tool-use | LangGraph / CrewAI / AutoGen | 减少抽象层，调试容易，控制 prompt |
| MCP | 自写 MCP server | — | 给 Claude / Antigravity 调行情 / 持仓 / 回测 / 复盘工具 |
| 监控 | Prometheus + Grafana | Datadog / NewRelic | 自托管够用，不付订阅费 |
| 日志 | Loki + Grafana | ELK | ELK 三件套对个人项目太重 |
| 前端 | Next.js + Tailwind + shadcn/ui | 自己搓 CSS / Vue / Svelte | 起步快，社区组件多，长期可维护 |
| 部署 | docker-compose + 1 台 VPS | k8s / Nomad / ECS | k8s 对一个人是纯负担 |
| 配置管理 | `.env` + git-ignored secrets | Vault / SOPS | 个人项目，复杂度收益不成正比 |
| CI | GitHub Actions + 自建 runner | Jenkins / GitLab CI | 已经在用 GitHub，免费额度够 |

### 3.3 编程语言分布

- **Python ~80%**：策略、agent、桥接、MCP server、ops 脚本
- **Rust ~5%**：**只**在 nautilus 内部 hot path 不够用、必须自定义时才写
- **TypeScript ~15%**：Next.js 前端

**禁止**：为了"看起来现代"把后端切到 Go / Rust。一个人的项目只用一门主语言。

### 3.4 数据库 schema 原则

阶段 0/1：

- 信号 / 回测结果 / 元数据进 **SQLite**（见 ADR-002 §3.3 `signals` 表）
- 历史 K 线 / tick 进 nautilus 的 **`ParquetDataCatalog`**
- 不上 migration 工具，schema 直接版本化在仓库里

阶段 2+（数据模型稳定后）：

- 所有时序数据进 TimescaleDB hypertable（tick、bar、order、fill、pnl）
- 所有结构化业务数据进普通 PG 表（strategy、position、agent_decision、journal）
- 所有 embedding 进 pgvector 列
- **schema 必须有 migration**（用 `alembic` 或 `atlas`），不允许手改 prod schema
- 从 SQLite 迁移到 PG 时，原 SQLite 文件归档，不删

---

## 4. 明确放弃的东西

> 这部分比"选了什么"更重要。半年后想加的时候，回来读这一节。

### 4.1 放弃的技术

| 放弃 | 为什么放弃 | 什么时候可以重新考虑 |
|---|---|---|
| Kubernetes | 一个人维护负担过大 | 跨 ≥ 3 台机器才考虑 |
| 微服务架构 | 服务间调试是个人项目杀手 | 永远不会，本项目最多 8 个进程而已 |
| Kafka / NATS | Redis Stream 完全够当前规模 | 真出现持久消息 + 跨数据中心需求 |
| Mongo / 多种数据库 | schema 蔓延 | 永远不会 |
| 高频 / tick 级套利 | Python 网络往返到不了 | 永远不会（除非整个项目用 Rust 重写） |
| 多交易所 | 复杂度爆炸，先在 binance 上证明 alpha | binance 上稳定盈利 6 个月后 |
| 自建撮合 / 自建回测 | 已有 nautilus | 永远不会 |
| 自己 fine-tune LLM | RAG + prompt 远没到瓶颈 | RAG 明显不够用 + 有量化收益证据 |
| 多 agent 协作（≥ 3 个 agent） | 1 个 agent 都没稳定起来 | 阶段 4 毕业后 |
| LLM 进入交易快路径 | 见铁律 2 | **永远不会** |

### 4.2 放弃的"专业感"

不会做的事：

- 不写 k8s manifest
- 不上 Helm chart
- 不搞 service mesh
- 不引入 OpenTelemetry 全链路（先用 Loki + 普通日志够了）
- 不上 feature flag 平台（环境变量够）
- 不写"企业级"抽象层（接口、工厂、依赖注入容器）
- 不追求 95%+ 测试覆盖率（关键路径覆盖 + 实盘 dry-run 验证就够）

---

## 5. 目录结构（一次定稿）

```
/home/nishiki/projects/trader/
├── architecture.png            # 两个月前画的图，不删
├── freqtrade/                  # upstream，不改源码
├── nautilus_trader/            # upstream，不改源码
├── apps/                       # 我自己写的代码全在这
│   ├── bridge/                 # freqtrade ↔ nautilus 信号桥
│   ├── strategies_nautilus/    # nautilus 自定义策略
│   ├── strategies_freqtrade/   # freqtrade 自定义策略
│   ├── agents/                 # LLM agent（Claude SDK）
│   ├── mcp_server/             # 给 agent 用的工具
│   ├── frontend/               # Next.js
│   └── ops/                    # 运维脚本、应急平仓
├── infra/
│   ├── docker-compose.yml
│   ├── postgres/init.sql       # schema + Timescale + pgvector 启用
│   ├── grafana/dashboards/
│   └── n8n/workflows/
├── notebooks/                  # 研究 / 分析 / 复盘
├── data/                       # 历史数据缓存，gitignore
└── docs/
    ├── runbook.md              # 怎么救火、怎么紧急平仓、怎么重启
    ├── decisions/              # 本文件所在
    │   └── 001-tech-stack.md
    └── retros/                 # 每月 retro，YYYY-MM.md
```

---

## 6. 阶段 → 服务激活时间表

> Phase 编号与命名以 `PLAN.md` 和 `docs/agent-operating-contract.md` §6 为准。
> 本表只规定：到每个 Phase 时，最多允许哪些服务长驻运行。

| 服务 | 0 骨架 | 1 数据+回测 | 2 ML 信号 | 3 风控+testnet | 4 Agent 研究 | 5 前端+监控 | 6 小钱实盘 |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| SQLite + Parquet 文件 | ✅ | ✅ | ✅* | ✅* | ✅* | ✅* | ✅* |
| nautilus（backtest 模式） | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| freqtrade / FreqAI |   | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| signal bridge（SignalEvent v1） |   | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| postgres + TimescaleDB + pgvector |   |   | ✅ | ✅ | ✅ | ✅ | ✅ |
| redis（Stream 桥接） |   |   | ✅ | ✅ | ✅ | ✅ | ✅ |
| nautilus 连 Binance **testnet** |   |   |   | ✅ | ✅ | ✅ | ✅ |
| agent-orchestrator |   |   |   |   | ✅ | ✅ | ✅ |
| mcp-server |   |   |   |   | ✅ | ✅ | ✅ |
| n8n |   |   |   |   | ✅ | ✅ | ✅ |
| grafana + prometheus + loki |   |   |   |   |   | ✅ | ✅ |
| frontend（Next.js） |   |   |   |   |   | ✅ | ✅ |
| nautilus 连 Binance **真实账户** |   |   |   |   |   |   | ✅ |

> ✅* = SQLite/Parquet 在 PG 上线后继续作为本地缓存 / 研究草稿用，不算独立服务。

**每个阶段不到毕业条件，不允许激活下一列。** Phase 毕业条件参考 `docs/agent-operating-contract.md` §6；具体数字门槛（testnet 14 天、真钱 30 天、单日 5% 停机、连续 3 月正收益翻倍）参考铁律 5。

---

## 7. 后悔条款

> 半年后如果有以下情况，回来更新本 ADR：

1. 跑了 6 个月仍未在 binance 上证明 alpha → 检讨是否在错的方向投入工程
2. nautilus 或 freqtrade 上游有破坏性变更，导致扩展点不可用 → 重新评估替代方案
3. 单 PG 撑不住时序写入 → 才考虑加 TimescaleDB 之外的存储
4. Redis Stream 真的不够 → 才考虑 NATS（不直接上 Kafka）
5. Claude API 不够用（成本 / 质量 / 速度）→ 评估是否引入 Sonnet/Haiku 分层，**仍不引入本地模型**
6. 一个人真的扛不动 → 不是改架构，是减阶段、砍范围

---

## 8. 备注

本 ADR 的存在意义：**当我半年后被一个新框架 / 新工具 / 新 buzzword 诱惑时，强迫自己先回来读一遍，再决定是否要破例**。

破例本身不可怕，**没意识到自己在破例**才可怕。

---

**Decided.**

后续 ADR：

- ADR-002（已 Accepted）：`SignalEvent v1` 桥接协议
- ADR-003：阶段 0/1 项目骨架与目录落地
- ADR-004：NautilusTrader 回测结果标准格式
- ADR-005：实盘前硬风控与应急停机规则

---

**2026-05-14 修订**：

- §3.2 / §3.4 / §6 已根据 Codex 框架优化对齐：阶段 0/1 默认 SQLite + Parquet，PG/Redis 推迟到阶段 2，监控/前端推迟到阶段 5，真实 Binance 账户推迟到阶段 6。
- Phase 命名以 PLAN.md / agent-operating-contract.md 为准。

---

**2026-05-21 修订**：

- §6 表对 grafana + prometheus + loki 的列从「Phase 5 才允许」修订为「Phase 3 entry
  即可提前启用」。同时新增 promtail 与 node_exporter 两个支撑组件，
  视作 grafana + prometheus + loki 的组成部分。
- 触发条件：Phase 3 testnet canary 已经在产 heartbeat / alerts / manifest /
  sidecar 数据，**被监控对象已齐**，等到 Phase 5 才接观测栈反而让 canary
  调试继续依赖手动 `grep + jq`。
- 范围限定：观测栈**只读** `data/testnet/<run_id>/logs/` / `data/paper/<run_id>/logs/`
  和 `data/observability/textfile/<kind>-<run_id>.prom`。不接触 SignalStore、
  不读凭证、不读取或改写订单/信号路径。
- ADR-007 §2.5 与 ADR-008 §6.6 的促进/降档证据仍以 bundle 内
  `run_manifest.json` + sidecar parquet 为准，**Grafana / Loki 不是 source of
  truth**。看板和 logs explorer 用于运行时观察和异常定位。
- 后悔条款：若观测栈成为 canary 评判依据（而非 bundle），回来撤销提前启用。

**2026-05-21 修订（第二段）**：

- §6 表对 postgres + TimescaleDB + pgvector 的列从「Phase 2 启用」修订为
  「Phase 3 entry **服务先启**」。「服务先启」≠ 数据迁移：bridge 默认仍是
  SQLite，`apps/bridge/store.py` 提供 `PostgresSignalStore` 作为可选 backend，
  不替换 `SignalStore` 的默认行为。
- 触发条件：观测栈已提前到 Phase 3 entry；Grafana 自然需要 SQL 数据源做时序
  查询；Phase 4 agent / mcp_server / n8n 后续依赖 pgvector。把服务先起好且
  schema 占位，后续迁移是配置而非新基建。SQLite 没出现真实瓶颈前**不迁移**。
- 范围限定：trader-postgres 仅本机 loopback (127.0.0.1:5433)；
  `infra/postgres/init.sql` 建 5 张占位表（signal_events / orders / fills /
  positions 是 hypertable；embeddings 用 pgvector(1536)）+ trader_ro 只读
  角色；Grafana 通过 trader_ro 读 PG。**不**自动迁移历史 SignalStore 数据。
- ADR-001 铁律 5（先 testnet 后 live）、ADR-002 / ADR-004 / ADR-007 / ADR-008
  全部不变；bundle 仍是 promotion source of truth。
- 后悔条款：若 SQLite 在 paper / testnet / live 表现出真实瓶颈，再开一个迁移
  ADR 做数据切换（`SignalStore` 默认从 SQLite 切到 Postgres）。
- ADR-010（Redis Stream 桥接通道）继续按"瓶颈出现后再写"的规则推迟。
