# ADR-010：Redis Stream 作为 SignalEvent 旁路传输

- **状态**：Draft（占位草稿；触发条件未达成，**不实现、不部署任何代码或服务**）
- **日期**：2026-05-21
- **作者 / 维护者**：nishiki（个人开发者，唯一负责人）
- **范围**：定义 `SignalEvent v1` 从 `apps/bridge/store.py::SignalStore`
  （SQLite，bridge 默认 backend）切换/旁路到 Redis Stream 的**触发条件、
  设计契约、迁移路径、验收清单**；定义本 ADR 在被触发前**保持 0 行
  实现**这件事本身。
- **依赖**：
  - ADR-001（技术栈、五条铁律、阶段时间表 — Redis 计划在 Phase 2，本 ADR
    解释为何 Phase 3 entry 仍**不**启）
  - ADR-002（`SignalEvent v1` 是唯一允许的研究信号桥；本 ADR 不改 schema）
  - ADR-004（`run_manifest.json` + sidecar 是 promotion source of truth；
    Redis 永远只是 transport，不能成为 promotion 证据）
  - ADR-006（`SourcePolicy` / dry_run / multiplier 是消费侧配置，与
    transport 解耦）
  - ADR-007（paper runtime，§2.6 promotion review 不读 Redis）
  - ADR-008（Phase 3 risk runbook，§6 testnet canary 仍走 SignalStore；
    Redis 落地后必须重新过 §6.6 的 6 h 稳定性 soak）
- **复审周期**：触发条件之一（§2）真正出现时立即复审；否则每跨一个 Phase
  门复审一次以确认 deferment 仍然合理

---

## 1. 背景

ADR-001 §6 阶段表里 redis (Stream) 标记的是 Phase 2，但实际项目走到
2026-05-21、Phase 3 entry 时仍然没有启 Redis。原因是 ADR-001 §6 的两条
"瓶颈出现后再做"规则：

- "SQLite polling 真的不够 → 才考虑 NATS（不直接上 Kafka）" → 同理也只在
  SQLite 不够后才上 Redis Stream。
- "Redis Stream 真的不够 → 才考虑 NATS"（这条本 ADR 不展开）。

到 2026-05-21 为止：

- `apps/bridge/store.py::SignalStore` 在 SQLite/WAL 模式下持有 3745 条
  `SignalEvent v1`，覆盖 freqai_linear_v1 / rule_baseline_v1 /
  manual_research 三个 source family；写入侧 freqtrade 研究脚本顺序
  append，读取侧 `SignalStorePollingSource` 在 testnet canary 里以 ≤1s
  cadence poll，60 个 heartbeat 全部读到 fresh 行，没有 lock 竞争记录、
  没有 `database is locked` 错误。
- ADR-008 §6.6 的两次 6 h 真单 testnet canary（2026-05-19 +
  2026-05-20）+ 一次 30 min 观测栈 smoke（2026-05-21）都跑通 SQLite
  polling 路径；`run_manifest.json` 的 `runtime.signal_lag*` 在阈值内。
- `apps/bridge/store.py::PostgresSignalStore` 已经实装并通过 7+5 个单元
  测试（2026-05-21 commit `9cbf364` + `80956a8`），是 SQLite 之外**第一个**
  正式可用的 backend 选项。但 bridge 默认仍走 SQLite。

也就是说：**SQLite 还没暴露过瓶颈**。Redis 在本项目当前规模下是一个
**预先设计、按需启用**的旁路，不是一个被任何已知问题驱动的方案。本 ADR
的目的是：在瓶颈真的出现的当天，能直接拿出可执行的设计，而不是从零开始
争论 Redis 还是 Postgres。

---

## 2. 触发条件（must-trigger 任意一条）

只要下面任意一条变成"真"，立即把本 ADR 切到 `Accepted` 并按 §6/§7 实施。
**不**满足任意一条时一律保持 `Draft`。

| # | 触发条件 | 测量方式 | 阈值 |
|---|---|---|---|
| T1 | SQLite `signals` 表上的 polling cursor 在生产 canary 中频繁失误（漏读 fresh 行或被 lock 撞回） | `signal_lag_exceeded_threshold` 出现在 `data/testnet/<run_id>/logs/alerts.log` 中**不是**因为生产侧停产而出现（即生产侧 ts_event 持续推进但消费侧 cursor 落后） | 同一 canary session 内 ≥3 次，连续 2 个 canary session 都复现 |
| T2 | 跨进程 / 跨机器读写：出现 ≥2 个独立 `BaselineNautilusStrategy` 进程同时消费同一 source（多策略同源、不同参数 / 不同 multiplier） | 进程级心跳列表 ≥2 个对同一 `(source, model_version)` 的 active 消费者 | ≥2 个进程已经在运行（不是计划） |
| T3 | bridge 写入侧从单进程 freqtrade 演化到多个并发生产者（FreqAI 在线训练 + rule baseline 实时 + LLM dual-sign 在线评分） | git/journal 中并发生产者进程数 | ≥3 个独立生产者 |
| T4 | SQLite 文件大小或 `sqlite3` query latency 影响 testnet canary heartbeat cadence | `signals.db` >2 GiB **或** `SignalStore.replay()` p99 >50 ms 在 30 s 监控窗口内出现 ≥5 次 | 任一阈值 |
| T5 | nautilus 与 bridge 物理拆分（运行在不同主机 / 不同容器集群，bridge 不再共享本地文件系统） | 部署清单里 `bridge.host != nautilus.host` | 部署决定一旦落地 |

注意：**T1 是软触发**（信号路径 lag），其它四条是硬触发（拓扑级变化）。
任意一条满足都需要把 ADR 状态从 Draft 改成 Accepted 之后再开始实现，不
允许"先实现再写 ADR"。

---

## 3. 非触发条件（must-NOT-trigger）

下面这些场景**不**构成触发：

- **想要更花的 dashboard**：Grafana 直接走 `apps/ops/sync_signals_to_postgres.py`
  把数据镜像到 PG，已经覆盖看板需求，不要把 Redis 拿来当显示层。
- **想要 pubsub-style 通知 ops 终端**：用 `infra/watchdog/history.jsonl` +
  Promtail/Loki 已经够了；不要为通知引入消息中间件。
- **想要"现代化感"**：永远不构成项目级技术决策，参见 ADR-001 §2 五条铁律。
- **agent-orchestrator / MCP server 想做消息总线**：Phase 4 范畴，且 Phase 4
  的设计文档（未来 ADR）必须先自证不能用现有 SignalStore 完成，再讨论
  Redis。

---

## 4. SignalEvent v1 schema 边界

**本 ADR 不改 ADR-002 §3 字段集合。** Stream message body 必须是
`SignalEvent.model_dump_json()` 产生的 JSON 字符串，跟 SQLite
`signals.raw_json` 字段完全一致。`signal_id` 仍是全局唯一键。

不允许：
- 在 stream 上添加 ADR-002 未定义的字段（比如 `redis_offset`、`partition`、
  `consumer_id`）作为 payload；要存放消费者状态，用 Stream consumer group
  自带的 `XACK`/PEL 机制，不要污染 payload。
- 用 Redis Stream 的 message ID 顶替 `signal_id`。`signal_id` 是 ADR-002
  契约里的 dedup 键，必须保留。

---

## 5. 设计契约（被触发后才实现）

### 5.1 Stream 拓扑

每个 `(source, model_version)` 二元组一个 Stream key，命名格式：

```
trader:signals:<source>:<model_version>
```

例：`trader:signals:freqai_linear_v1:linear-mom-train20240105`。

理由：消费端的 `SourcePolicy` 本身就是 per-source / per-model_version 的；
把 Stream 也按这个粒度切开，让 `XREADGROUP` 的 cursor 自然与 SourcePolicy
对齐，避免一个慢消费者堵住整条线。

**不**使用 channel pattern matching（`PSUBSCRIBE`）。Stream 是显式列表，
新 source 要在 producer / consumer 两边都明确登记。

### 5.2 Consumer group

每个 nautilus 消费进程一个 consumer group，命名：

```
nautilus:<role>:<run_id_prefix>
```

`<role>` ∈ {`backtest`, `paper`, `testnet`, `live`}。`<run_id_prefix>` 是
bundle `run_id` 的前 8 字符（与 ADR-004 `run_manifest.json` 中的
`run_id` 是同一字符串，便于审计联动）。

消费动作：
- `XREADGROUP GROUP <group> <consumer> COUNT N BLOCK <ms> STREAMS <key> >`
- 处理成功（已经 `add_strategy` 提交 SubmitOrder）后 `XACK`；
- 启动时先 `XPENDING` + `XCLAIM` 把上一次崩溃前未 ACK 的 message 全部
  重做（幂等保证由 `signal_id` 提供，nautilus 端的 `BaselineNautilusStrategy`
  已经天然支持，无新增）。

### 5.3 Producer 写入路径

freqtrade / 研究脚本仍然 **先写 SQLite**（bridge 默认）、**再写 Stream**：

```python
store.write(event)              # SQLite, ADR-002 contract
stream.xadd(key, payload)       # Redis Stream, ADR-010 contract
```

顺序不变：SQLite 是 promotion source of truth（ADR-004），Stream 只是
低延迟旁路。如果 `xadd` 失败，**不**回滚 SQLite 写入，**不**重试
`xadd`，只在 producer 日志里 ERROR。Bridge SQLite polling 是兜底路径，
能在 Stream 完全宕机时继续工作。

这意味着 nautilus 消费侧可以二选一：
- **A：仅消费 Stream**（低延迟，强假设 producer Stream 写入不丢）
- **B：Stream + SQLite polling 双读**（牺牲一点延迟做兜底，dedup 靠
  `signal_id`）

ADR-010 默认 B，让 Stream 作为旁路而不是替换。`SignalStorePollingSource`
保持现状，新增一个 `RedisStreamSource` 与之 OR 合并。这样关停 Redis 容器
不会让 testnet/live 自动断流。

### 5.4 Retention / 持久化

- `MAXLEN ~ 100000` 近似裁剪。1 m bar cadence 下，~70 天的信号上限，
  足够 nautilus 重启 reconnect。
- AOF appendonly = `everysec`，匹配 ADR-001 §3.2 SQLite WAL 的"丢最多 1 s"
  的容忍度。
- 不开 RDB snapshot（重复 + 占盘）。
- 单实例，不部署 Sentinel/Cluster。多实例的需要由后续 ADR 触发（参见
  §2 T5 之后的）。

### 5.5 Idempotency / 重复消费

ADR-002 已经规定 `signal_id` 全局唯一。`BaselineNautilusStrategy` 在
session 内维护 `_seen_signal_ids: set[str]`，跨重启用 bundle
`signal_lineage.parquet` 还原。Stream 不参与 dedup，纯粹是 transport。

### 5.6 不做

- **不**把 `SourcePolicy` 序列化进 Stream payload；SourcePolicy 是消费侧
  配置，与 transport 解耦。
- **不**用 Stream 做 backtest 历史回放；backtest 永远走 `SignalStore.replay()`
  和 catalog parquet（ADR-004）。
- **不**用 Stream 做 LLM agent → 订单的"快速通道"——ADR-001 五条铁律之一
  是 LLM 不进订单路径，本 ADR 不放松。

---

## 6. 部署拓扑（被触发后才落地）

`infra/docker-compose.yml` 中现存的 `redis:` 服务块**已经在文件里被注释
掉**。被触发后只允许打开两件事：

```yaml
redis:
  image: redis:7.4-alpine
  container_name: trader-redis
  command: ["redis-server", "--appendonly", "yes", "--appendfsync", "everysec",
            "--maxmemory", "512mb", "--maxmemory-policy", "noeviction"]
  ports:
    - "127.0.0.1:6379:6379"   # loopback only, 与全栈一致
  volumes:
    - redis_data:/data
  healthcheck:
    test: ["CMD", "redis-cli", "ping"]
    interval: 10s
```

绑 127.0.0.1，与 prometheus / grafana / loki / promtail / node_exporter /
postgres 一致。**不**暴露公网端口；**不**接 auth/TLS（Phase 4 多机时再
讨论）。volume 走 named volume `redis_data` 让 `docker compose down` 不
丢数据。

---

## 7. 迁移路径

被触发后按此顺序，每一步独立 commit + 独立 retro：

### 7.1 Step A：bridge 写入侧加 dual-write

- `apps/bridge/store.py` 新增 `RedisStreamSink`（writer-only，没有 read
  surface），dataclass `RedisConnInfo`（默认 host=127.0.0.1, port=6379,
  无密码，loopback dev only）。
- freqtrade research script / CLI 加 `--redis-stream-sink` 可选 flag。
  **默认关**，即使 docker compose 起了 redis 也不会自动开始写。
- 关键性质：**SQLite 是主，Redis 是从**。Redis 写失败只 ERROR，不抛、不
  重试、不阻塞 SQLite。
- 单元测试：3 个，覆盖 (写 SQLite + 写 Stream 都成功 / Redis 不可达时
  SQLite 仍成功 / payload 与 SQLite raw_json 完全一致)。

### 7.2 Step B：nautilus 消费侧加 `RedisStreamSource`

- `apps/strategies_nautilus/baseline_nautilus_strategy.py` 已经有
  `SignalSource` protocol（per ADR-008 §6.6 实施记录）。新增
  `RedisStreamSource` 实现该 protocol，与 `SignalStorePollingSource`
  互不依赖。
- 新增 `OrSignalSource(*sources)` 合并多 source，按 ts_event 排序、按
  `signal_id` 去重。
- 单元测试：4 个，覆盖 (Redis 单独工作 / SQLite 单独工作 / 两者合并去
  重 / 一边掉线另一边接管)。

### 7.3 Step C：testnet 重新过 ADR-008 §6.6

- launcher 多接一段开关，先单跑一个 30 min smoke（同当前
  `infra/launchers/first-testnet-canary-30min-smoke.py` 模板）验证
  Stream + SQLite 双源不增加 signal_lag。
- 然后跑一个 6 h canary，强制要求与现有 2026-05-19 / 2026-05-20 两次
  6 h baseline 同等清洁（0 ERROR、0 reconnect、0 advisory alert）。
- 通过后才把"Redis Stream 是默认 transport"写进 ADR-001 §6 修订。

### 7.4 Step D：观测栈接 Redis（可选，不阻塞 §7.1-§7.3）

- Prometheus 通过 `redis-exporter` sidecar 抓 `XLEN` / `XPENDING` /
  consumer lag。
- Grafana 新看板 `signals-transport` 显示 Stream 长度、ACK 延迟、未
  ACK 计数。
- 不强制；§7.3 通过后再做。

### 7.5 Step E：评估是否还要切默认

**默认仍可以是 SQLite。** Redis 上线后跑 ≥1 个月 paper + ≥2 次 6 h
canary 之后，复审"消费侧默认走 Redis 而不是 SQLite polling"这件事是否
真的能省错误预算。这不属于本 ADR 必须 commit 的范围，是一个**后续
ADR-011** 的题目（届时再定）。

---

## 8. 不做（不重复 §3，列出操作侧）

- **不**让 Redis 取代 `signal_lineage.parquet` 做 ADR-004 audit。
- **不**把 LLM agent 直连 Redis Stream 发信号——`Authorization`
  allowed-sources 仍是唯一闸门，Stream 不是绕过它的快速通道。
- **不**为 Redis 写"统一封装层"。`SignalStore` 与
  `RedisStreamSource` 各自直接用 sqlite3 / redis-py，不要 ORM、不要
  asyncio 全家桶。
- **不**为消费动作引入 retry/exponential backoff 框架。`signal_id`
  dedup 已经足够。
- **不**为 producer 写入失败做 retry 队列；ERROR 直接打日志，让 SQLite
  polling 兜底。

---

## 9. 验收清单（被触发后才用）

切到 Accepted 之后，落地动作必须满足：

- [ ] `infra/docker-compose.yml` 打开 redis 服务块；`docker compose up -d redis`
      → `redis-cli ping` PONG，端口 `127.0.0.1:6379`。
- [ ] `apps/bridge/store.py` 新增 `RedisStreamSink` + 单元测试 ≥3
      passed；SQLite 仍是默认 backend。
- [ ] `apps/strategies_nautilus/baseline_nautilus_strategy.py` 新增
      `RedisStreamSource` + `OrSignalSource` + 单元测试 ≥4 passed；
      `SignalStorePollingSource` 不动。
- [ ] freqtrade research script CLI 加 `--redis-stream-sink` flag；
      默认关。
- [ ] 一次 30 min testnet smoke（Redis + SQLite 双源、`--write-live-sidecars`）
      跑通；retro 写入 `docs/retros/`。
- [ ] 一次 6 h testnet canary 与现有 baseline 同等清洁。
- [ ] 本 ADR 状态从 Draft → Accepted；ADR-001 §6 阶段表更新 redis
      行的"实际启用"列。
- [ ] `docs/project-status.md` 加里程碑摘要。

---

## 10. 不变 / 不破

- ADR-001 五条铁律（无 LLM 进单、单 VPS、SQLite/Parquet 优先、风控不绕、
  $250 起家阶梯）全保留。
- ADR-002 `SignalEvent v1` 字段集合不动。
- ADR-004 `run_manifest.json` + sidecar parquet 仍是 promotion source of
  truth，Redis 永远是 transport。
- ADR-006 `SourcePolicy` / dry_run / multiplier 不动，与 transport 解
  耦。
- ADR-007 §2.6 promotion review 不读 Redis；§2.5 stage table 不动。
- ADR-008 §6.6 testnet runbook 在 Redis 启用后**必须重新跑一次完整 6 h**，
  不允许在不重跑的情况下声称 Redis 通过 Phase 3 验收。
- bridge 默认 backend 仍是 SQLite（直到 §7.5 出 ADR-011 决定切换）。
- Grafana `canary-current` / `signals-overview` 看板继续工作；Redis 不
  接入也不影响看板。
