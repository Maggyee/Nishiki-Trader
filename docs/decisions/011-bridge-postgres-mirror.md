# ADR-011：bridge SignalStore → Postgres 自动镜像

- **状态**：Draft（占位草稿；触发条件未达成，**不实现、不部署任何代码或服务**）
- **日期**：2026-05-21
- **作者 / 维护者**：nishiki（个人开发者，唯一负责人）
- **范围**：定义 `apps/bridge/store.py::SignalStore`（SQLite，bridge 默认
  backend）**自动**镜像到 `apps/bridge/store.py::PostgresSignalStore`
  （Phase 3 entry 已起的 `trader-postgres.signal_events` hypertable）的
  **触发条件、写入语义、失败处理、测试隔离策略、迁移路径、验收清单**；
  定义本 ADR 在被触发前**保持 0 行实现**这件事本身。
- **依赖**：
  - ADR-001（技术栈、五条铁律、阶段时间表 — Postgres 计划在 Phase 2，
    实际 2026-05-21 已起服务，但 **不迁移历史数据**）
  - ADR-002（`SignalEvent v1` 是唯一允许的研究信号桥；本 ADR 不改 schema）
  - ADR-004（`run_manifest.json` + sidecar 是 promotion source of truth；
    Postgres 永远只是 mirror，不能成为 promotion 证据）
  - ADR-006（`SourcePolicy` / dry_run / multiplier 是消费侧配置，与
    backend 解耦）
  - ADR-008（Phase 3 risk runbook，§6 testnet canary 仍走 SignalStore；
    mirror 落地后必须重新过 §6.6 的 6 h 稳定性 soak）
  - ADR-010 Draft（Redis Stream 旁路；本 ADR 与之**正交**：Redis 是
    transport，PG 是分析/审计 mirror。两者都触发时可同时上线，互不依赖）
- **复审周期**：触发条件之一（§2）真正出现时立即复审；否则每跨一个 Phase
  门复审一次以确认 deferment 仍然合理

---

## 1. 背景

2026-05-21 commit `9cbf364` 把 Postgres + TimescaleDB + pgvector 提前从
Phase 2 拉到 Phase 3 entry，**仅启服务、不迁移**。当前现状：

- `trader-postgres` 容器健康运行（`timescale/timescaledb-ha:pg16`，
  端口 `127.0.0.1:5433`），`signal_events` 是 hypertable，schema 与
  SQLite `signals` 表一一对应，只差 PK 是 `(signal_id, ts_event)` 复合键
  以满足 hypertable 的 unique 约束。
- `apps/bridge/store.py::PostgresSignalStore` 已经实装，方法面与
  `SignalStore` 完全对齐（write/mark/get/list_by_status/replay），并通过
  7 个 PG round-trip 单元测试。
- `apps/ops/sync_signals_to_postgres.py` 是一个**一次性手动镜像**：
  幂等地把 SQLite 当前所有行 `INSERT` 进 PG；用 `DuplicateSignalError`
  跳过已存在 `signal_id`。需要 dashboard 有数据时手动跑一次。
- `infra/grafana/dashboards/signals-overview.json` 现在通过
  `postgres-trader` datasource + 只读角色 `trader_ro` 读 `signal_events`
  做 SQL 时序聚合（commit `80956a8` + `69c8f25`）。

也就是说：**PG 已经是 Grafana 看板的 query 端**，但 bridge **写入端**还
没自动镜像，每次想看 dashboard 最新数据都得手动跑 sync 脚本。这是个
**已知的 friction，不是 bottleneck**——研究 / 回测节奏下手动 sync 每天
一次就够，且 ADR-008 §6.6 testnet canary 期间的数据流不进 bridge
SignalStore（运行时数据走 `data/testnet/<run_id>/logs/`、`data/testnet/<run_id>/*.parquet`
等 bundle 内文件，被 Promtail / 后续 sidecar 写入路径接管，与 SQLite 桥
信号是两条线）。

本 ADR 的作用是：在 friction 真的演化成 bottleneck 的那一天，能直接拿
出可执行的设计，而不是临时拍脑袋。同 ADR-010 一样：**0 行实现，写在
账上备查**。

---

## 2. 触发条件（must-trigger 任意一条）

只要下面任意一条变成"真"，立即把本 ADR 切到 `Accepted` 并按 §7 实施。
**不**满足任意一条时一律保持 `Draft`。

| # | 触发条件 | 测量方式 | 阈值 |
|---|---|---|---|
| T1 | dashboard 实时性需求超出手动 sync 节奏 | Grafana `signals-overview` 看板上观察到的 freqai / rule producer ts_event 与 dashboard 数据之间的差距 | "每天手动跑一次"无法满足；需要 ≤1 h 时延 |
| T2 | 跨表分析（signal × order × fill × position）需要 SQL JOIN | Phase 4 agent / MCP server 或人类研究侧明确写出"需要把 signal_lineage.parquet 装进 PG 做 JOIN"的需求 | 至少 1 个真实查询无法在 SQLite + parquet 组合上实现，且 PG JOIN 能 trivially 解决 |
| T3 | SQLite size / lock 出现 ADR-010 §2 T4 的迹象 | `signals.db` >2 GiB **或** `SignalStore.replay()` p99 >50 ms 在 30 s 监控窗口内出现 ≥5 次 | 任一阈值。注意：ADR-010 T4 与本 T3 同源——同一阈值可能同时触发本 ADR 与 ADR-010 |
| T4 | 多个独立研究进程同时写 SQLite，写入 throttle 出现 | freqtrade research + LLM dual-sign + FreqAI 在线训练 ≥2 个进程并发 `INSERT` 同一 SQLite 文件，出现 `database is locked` 错误 | ≥1 次记录在 producer log |
| T5 | 数据持久性 / 备份策略需要 PG 的复制机制 | 备份策略写下"SQLite WAL 文件不够，需要 PG WAL + base backup" | 备份策略落地为运维 ADR / runbook |

注意：
- **T1 是软触发**，T2-T5 是硬触发。
- **T3 与 ADR-010 T4 同条件**——当 SQLite 真出瓶颈时，本 ADR 与 ADR-010
  会同时触发。届时优先看哪一边是真瓶颈：写入侧选 ADR-011 PG mirror，读
  延迟侧选 ADR-010 Redis bypass，**两者可以同时上线，互不冲突**。

---

## 3. 非触发条件（must-NOT-trigger）

下面这些场景**不**构成触发：

- **看板加更花的图**：可以继续靠手动 sync + `signals-overview` 现有 SQL
  panel 覆盖。先把 sync 改成 cron-on-host（不是新 ADR），观察 1 个月再
  说。
- **想"用上 TimescaleDB 的 continuous aggregate"**：聚合可以基于已经
  sync 过去的快照在 PG 内做，不需要实时写入。Continuous aggregate 的
  refresh policy 是 PG 配置题，不是 ADR-011 范围。
- **Phase 4 MCP / agent-orchestrator 想用 PG 当 agent 短期记忆**：那是
  `embeddings` 表 + pgvector 的事，跟 `signal_events` 镜像无关；属于
  未来的 agent ADR。
- **"PostgreSQL 比 SQLite 更专业"** / "现代化感"：不构成项目级技术决
  策，参见 ADR-001 §2 五条铁律。
- **想让 promotion review 读 PG 而不是 bundle**：违反 ADR-004 "bundle =
  source of truth"，绝对不行；本 ADR §10 已经把这条钉死。

---

## 4. SignalEvent v1 schema 边界

**本 ADR 不改 ADR-002 §3 字段集合。** PG `signal_events` 表的字段集合在
`infra/postgres/init.sql` 中已经与 SQLite `signals` 表对齐，只差 PK 改成
`(signal_id, ts_event)` 以满足 hypertable 约束。本 ADR 落地时**也不能**：

- 加 ADR-002 未定义的字段（例如 `mirrored_at`、`source_db`、
  `replication_lag_ms`）。镜像元数据如果需要，单独建一张
  `signal_events_mirror_meta` 表，不污染主表。
- 删除 / 重命名任何字段。
- 改 `signal_id` 的语义；它仍是 ADR-002 dedup 全局唯一键，跨 SQLite ↔ PG
  两边一一对应。

---

## 5. 设计契约（被触发后才实现）

### 5.1 写入模型：synchronous dual-write，SQLite 主、PG 从

`SignalStore.write(event)` 内部顺序：

```python
def write(self, event: SignalEvent, *, now_ns: int | None = None) -> None:
    # 1) SQLite 是真 backend，永远先成功
    with self._connect() as conn:
        conn.execute("INSERT INTO signals ...", (...))

    # 2) 可选 PG mirror，never blocks SQLite
    if self._mirror is not None:
        try:
            self._mirror.write(event, now_ns=now_ns)
        except DuplicateSignalError:
            pass  # benign: catch-up sync 已经写过
        except Exception as exc:
            logger.error("pg_mirror_failed", signal_id=event.signal_id, exc=repr(exc))
```

关键性质（与 ADR-010 §5.3 producer 路径同形）：

- **SQLite 先成功**才有 PG mirror。SQLite 失败抛异常，调用方按
  ADR-002 § 5 处理；PG 写入永远不影响 SQLite 写入语义。
- **PG 失败不重试**。靠 §5.3 启动 catch-up 兜底。
- **`DuplicateSignalError` 静默**：catch-up 已经把这条写过了，正常路径
  重写碰到唯一约束，吞掉即可。
- mirror 注入：`SignalStore(path, mirror=PostgresSignalStore(...))`；
  默认 `mirror=None`，行为与现在完全相同。

### 5.2 不做异步队列

不引入 `asyncio` / `threading.Thread` 在 `SignalStore.write` 之外发起
后台写。理由：
- producer 路径目前是同步 freqtrade research script + bridge CLI，
  没有 event loop。
- 加后台 thread 等于把"写入是否成功"从同步上下文里拿走，错误难以观察。
- 一次 PG `INSERT` 在 loopback 上 <5 ms，对 producer 节奏（≥1 s
  cadence）影响 <1%。

### 5.3 startup catch-up：bridge 启动时拉平 PG

`SignalStore.__init__()` 在 `mirror` 非空时执行一次 catch-up：

```python
def __init__(self, path, mirror=None) -> None:
    ...
    if mirror is not None:
        self._catch_up_mirror(mirror)

def _catch_up_mirror(self, mirror) -> None:
    # Find max ts_event already in PG, write everything strictly newer
    # from SQLite. Reuse apps.ops.sync_signals_to_postgres.sync().
```

实现层面直接调用 `apps.ops.sync_signals_to_postgres.sync(...)`，传入
`since_ns = max(PG.ts_event) + 1` 即可避免 N² 重写。

### 5.4 失败模型

| 故障 | SQLite | PG mirror | 行为 |
|---|---|---|---|
| 一切正常 | 写入成功 | 写入成功 | 调用方拿到 None 返回 |
| PG 容器关停 | 写入成功 | psycopg connect 失败 | logger.error，调用方仍拿到 None |
| PG 容器重启 | 写入成功 | 部分失败、部分成功 | logger.error；下次 startup 由 catch-up 兜底 |
| SQLite 锁 | 抛 OperationalError | 不进 PG 路径 | 调用方处理 |
| PG schema 不兼容（不该发生） | 写入成功 | psycopg DataError | logger.error；调用方仍拿到 None |
| 双库同时挂 | SQLite 写失败 | 跳过 | 调用方处理 SQLite 异常 |

**PG-down 永远是软故障**。任何"挂了就停止 producer"的逻辑都是反模式，
违反 §5.1。

### 5.5 测试隔离策略（关键差异点）

当前 `tests/bridge/test_postgres_store.py` 和
`tests/ops/test_sync_signals_to_postgres.py` 在 setup 时 `TRUNCATE
signal_events`，这是 ADR-011 实施后**必须废弃**的做法。

落地时同步实现以下三件事：

1. 测试 fixture **不再** TRUNCATE 真实 `trader-postgres.signal_events`
   表。改用 **schema-per-test** 隔离：每个 test session 自动建一个
   `pg_temp_*` 临时 schema，pytest 退出时 `DROP SCHEMA CASCADE` 清理。
2. CI / pytest 退出后**不需要**再跑
   `python -m apps.ops.sync_signals_to_postgres`。这是当前 `infra/README.md`
   提到的 friction，ADR-011 落地后直接消失。
3. `apps/ops/sync_signals_to_postgres.py` 改成"补漏"工具（disaster
   recovery），不再是日常路径。

如果隔离 schema 方案在 timescaledb-ha 镜像下不可行（hypertable 限定
public schema），改用 **dedicated test database** (`trader_test`)。

### 5.6 不做

- **不**让 PG 取代 SQLite 当默认 backend。bridge 默认仍是 SQLite。
- **不**做 PG → SQLite 反向同步。镜像方向严格单向。
- **不**用 PG 作为 promotion 评判依据（ADR-004 不变）。
- **不**把 PG 凭证写进 git；继续靠 `infra/.env` + dev-only loopback
  默认。
- **不**对 PG mirror 写"重试 + 死信队列"逻辑。靠 startup catch-up 兜
  底，足够。

---

## 6. 部署拓扑（已经满足，无需改动）

Phase 3 entry 已经满足部署侧的全部条件：

- `trader-postgres` 容器在 `infra/docker-compose.yml` 中起好，
  loopback 端口 `127.0.0.1:5433`。
- `infra/postgres/init.sql` 已经建好 `signal_events / orders / fills /
  positions / embeddings` 五张表（前 4 张是 hypertable），只读角色
  `trader_ro` 存在。
- `pyproject.toml` 已加 `psycopg[binary]>=3.2`。
- `PostgresSignalStore` + `PostgresConnInfo` 已经实装。

**ADR-011 落地不需要新加任何服务、镜像、卷、端口、依赖**。纯粹是把
`SignalStore.__init__` / `SignalStore.write` 多接一个可选 mirror 参数
+ catch-up 调用，外加测试隔离改造。

---

## 7. 迁移路径

被触发后按此顺序，每一步独立 commit + 独立 retro：

### 7.1 Step A：测试隔离重构

- 优先于 mirror 写入，因为现有 `TRUNCATE signal_events` 测试一旦 mirror
  打开会把生产数据一起干掉。
- 方案 A1（首选）：每个 test session 用 `pg_temp_*` schema，fixture
  自动建 + 自动清理；hypertable 创建在临时 schema 内。
- 方案 A2（fallback）：在 `trader-postgres` 中建第二个 database
  `trader_test`，pytest 通过 `PostgresConnInfo(dbname="trader_test")`
  连接，`init.sql` 也对该 DB 执行一次。
- 验收：两个 PG 测试文件不再 TRUNCATE 真实 `signal_events`；跑完
  pytest 之后 `signal_events` 行数不变。

### 7.2 Step B：mirror 写入路径

- `apps/bridge/store.py::SignalStore.__init__` 接 `mirror: PostgresSignalStore | None = None`。
- `SignalStore.write` 加 try/except PG mirror block，遵守 §5.1 的失败
  模型。
- 单元测试 ≥4 个：(mirror=None 行为不变 / mirror 写入成功 / mirror
  抛 DuplicateSignalError 时静默 / mirror connect 失败时 SQLite 仍成
  功且 logger.error 出现)。

### 7.3 Step C：startup catch-up

- `SignalStore.__init__` 在 mirror 非空时调用
  `apps.ops.sync_signals_to_postgres.sync(...)`，传入合适的
  `since_ns`。
- 单元测试 ≥2 个：(PG 比 SQLite 落后 N 行 → catch-up 写 N 行 / PG 与
  SQLite 完全一致 → catch-up 写 0 行)。

### 7.4 Step D：CLI / 生产路径接 mirror

- freqtrade research script + `apps/bridge/cli.py` 接受可选 flag
  `--enable-pg-mirror`（默认关）。
- 跑一个 30 min smoke：开 mirror 跑一段 freqtrade research 写信号，
  观察 PG 上有同步的行 + producer log 没有 PG 相关 ERROR。

### 7.5 Step E：testnet 重新过 ADR-008 §6.6

- 同 ADR-010 §7.3 的模式：先 30 min smoke，再 6 h canary。
- 关键 SLO：mirror 开启后的 canary `signal_lag` 与现有 baseline 对齐
  （±5%）；alerts.log 中 `signal_lag_exceeded_threshold` 不会因 PG
  写入抖动而多发。

### 7.6 Step F：把 `infra/README.md` 的 friction 段删掉

- 当前 README 写"跑完 pytest 之后 PG 表会被清空，看板回到空。需要看
  板有数据时，跑完 pytest 再重新执行 sync"——ADR-011 落地后这段必须
  删掉，否则会让人误以为 friction 还在。

### 7.7 Step G：评估 PG 是否切默认 backend

**默认仍是 SQLite。** Mirror 跑 ≥1 个月 + ≥2 次 6 h canary 之后，复审
"bridge 默认 backend 从 SQLite 切到 PG"。这一步**不在本 ADR 范围**，
是一个后续 ADR 的题目（届时再编号，注意：ADR-010 §7.5 提到的"切默认
transport"是 Redis 的事，与本 step 独立）。

---

## 8. 不做（不重复 §3，列出操作侧）

- **不**让 PG 取代 `signal_lineage.parquet` 做 ADR-004 audit。
- **不**把 LLM agent 直连 PG 写信号——`Authorization` allowed-sources
  仍是唯一闸门。
- **不**为 PG mirror 写"统一封装层"或抽象工厂。`SignalStore` 与
  `PostgresSignalStore` 各自直接用 sqlite3 / psycopg，不要 ORM。
- **不**为 mirror 写后台 thread / asyncio worker。同步 dual-write 已
  经够用。
- **不**让 mirror 状态参与 promotion / kill-switch / risk 决策。

---

## 9. 验收清单（被触发后才用）

切到 Accepted 之后，落地动作必须满足：

- [ ] 测试隔离重构落地：PG 测试不再 TRUNCATE 真实 `signal_events`；
      pytest 完毕后 `SELECT COUNT(*) FROM signal_events` 与跑测试前
      一致。
- [ ] `apps/bridge/store.py::SignalStore.__init__` 接受 `mirror=` 参
      数，默认 `None`；现有测试 478+ 全部 passed 不变。
- [ ] `apps/bridge/store.py::SignalStore.write` 在 mirror 注入时执行
      §5.1 的 dual-write，单元测试 ≥4 passed。
- [ ] `SignalStore.__init__` 在 mirror 非空时执行 catch-up，单元测试
      ≥2 passed。
- [ ] freqtrade research / bridge CLI 加 `--enable-pg-mirror`，默认
      关；CI baseline 路径行为不变。
- [ ] 30 min testnet smoke（mirror 开） + 6 h canary（mirror 开）跑
      通，retro 写入 `docs/retros/`。
- [ ] `infra/README.md` 删去"跑完 pytest 后重新 sync"那段。
- [ ] 本 ADR 状态从 Draft → Accepted；ADR-001 §6 阶段表更新 postgres
      行的"实际启用"说明（从"仅启服务，不迁移"改为"启服务 + 自动
      mirror"）。
- [ ] `docs/project-status.md` 加里程碑摘要。

---

## 10. 不变 / 不破

- ADR-001 五条铁律（无 LLM 进单、单 VPS、SQLite/Parquet 优先、风控不
  绕、$250 起家阶梯）全保留。
- ADR-002 `SignalEvent v1` 字段集合不动。
- ADR-004 `run_manifest.json` + sidecar parquet 仍是 promotion source
  of truth，PG 永远是 analytical mirror，不是 promotion 证据。
- ADR-006 `SourcePolicy` / dry_run / multiplier 不动，与 backend 解
  耦。
- ADR-007 §2.6 promotion review 不读 PG；§2.5 stage table 不动。
- ADR-008 §6.6 testnet runbook 在 mirror 启用后**必须重新跑一次完整
  6 h**，不允许在不重跑的情况下声称 PG mirror 通过 Phase 3 验收。
- ADR-010（Redis Stream 旁路）与本 ADR 互不阻塞、互不依赖，可以同时上
  线也可以单独上线。
- bridge 默认 backend 仍是 SQLite（直到 §7.7 出后续 ADR 决定切换）。
- Grafana `canary-current` / `signals-overview` 看板继续工作；mirror
  落地后 `signals-overview` 的实时性提升，但看板查询逻辑不需要任何
  改动（仍走 `trader_ro` + `signal_events`）。
