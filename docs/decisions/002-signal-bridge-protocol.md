# ADR-002：freqtrade/FreqAI 到 NautilusTrader 的信号桥协议

- **状态**：Accepted
- **日期**：2026-05-14
- **作者 / 维护者**：nishiki（个人开发者，唯一负责人）
- **范围**：`freqtrade` / `FreqAI` 研究信号如何进入 `nautilus_trader` 执行层
- **依赖**：ADR-001 技术栈选型与五条铁律
- **复审周期**：阶段 1 完成后复审一次；之后每 6 个月随 retro 复审

---

## 1. 背景

本项目采用三层职责：

- `freqtrade` / `FreqAI`：研究、特征工程、ML 训练、信号生成。
- `nautilus_trader`：唯一订单、仓位、风控、执行核心。
- LLM Agent：异步研究、复盘、解释和参数建议。

这三层不能共享“下单权”。如果 `freqtrade`、ML 模型或 Agent 直接影响订单生命周期，系统会变成双执行核心，仓位和风险状态不可控。

因此需要一个固定桥接协议：上游只能输出**信号**，下游由 `nautilus_trader` 策略和风控决定是否交易。

---

## 2. 决策

### 2.1 桥接方向

信号桥是单向的：

```text
freqtrade / FreqAI / research code -> SignalEvent -> NautilusTrader Strategy -> RiskEngine -> ExecutionEngine
```

禁止反向调用：

- `nautilus_trader` 不调用 `freqtrade` 内部策略对象。
- `freqtrade` 不调用 `nautilus_trader` 下单接口。
- Agent 不调用任何真实交易 API。

### 2.2 信号不是订单

`SignalEvent` 只表达“研究层认为某个标的在某个时间窗口有某个方向和强度”。

它不包含：

- 订单类型
- 下单价格
- 下单数量
- 杠杆
- 止损止盈
- 是否立刻成交

这些必须由 `nautilus_trader` 策略、portfolio、risk engine 和执行配置决定。

### 2.3 阶段化传输

阶段 1 使用本地文件或 SQLite 表落地 `SignalEvent`，便于回测、复盘和调试。

阶段 2 继续优先使用本地 SQLite / 文件桥接；只有当 paper/testnet 前向运行证明
SQLite polling 不够用，才引入 Redis Stream 做近实时桥接：

```text
stream: signals.v1
consumer group: nautilus_signal_consumers
```

Redis Stream 被证明确实不够后，才评估 NATS；不直接上 Kafka。

---

## 3. SignalEvent v1

### 3.1 JSON 结构

```json
{
  "schema_version": "signal.v1",
  "signal_id": "freqai_v1:BTCUSDT:BINANCE:2026-05-14T12:00:00Z:15m",
  "symbol": "BTCUSDT",
  "venue": "BINANCE",
  "ts_event": 1778760000000000000,
  "horizon": "15m",
  "side": "buy",
  "score": 0.73,
  "confidence": 0.61,
  "source": "freqai_v1",
  "model_version": "2026-05-14",
  "ttl_seconds": 900,
  "features_hash": "sha256:optional",
  "metadata": {
    "timeframe": "15m",
    "strategy": "freqai_baseline_v1"
  }
}
```

### 3.2 字段约束

| 字段 | 必填 | 约束 |
|---|---:|---|
| `schema_version` | 是 | 固定为 `signal.v1` |
| `signal_id` | 是 | 全局唯一，可由 source/symbol/venue/time/horizon 拼接 |
| `symbol` | 是 | 上游使用交易所格式，如 `BTCUSDT` |
| `venue` | 是 | 初期固定 `BINANCE` |
| `ts_event` | 是 | Unix nanoseconds，表示信号对应的数据事件时间 |
| `horizon` | 是 | 例如 `5m`、`15m`、`1h` |
| `side` | 是 | 只能是 `buy`、`sell`、`flat` |
| `score` | 是 | `-1.0` 到 `1.0`，表示方向强度 |
| `confidence` | 是 | `0.0` 到 `1.0`，表示模型或研究层置信度 |
| `source` | 是 | 例如 `freqai_v1`、`manual_research`、`agent_research` |
| `model_version` | 是 | 可追踪的模型或规则版本 |
| `ttl_seconds` | 是 | 过期时间，过期信号必须忽略 |
| `features_hash` | 否 | 用于追踪训练/预测特征版本 |
| `metadata` | 否 | 只存调试信息，不允许放交易指令 |

### 3.3 方向语义

- `buy`：上游看多，不代表必须开多。
- `sell`：上游看空，不代表必须开空。
- `flat`：上游建议空仓或降低暴露。

如果 `side` 和 `score` 方向冲突，以 `side` 为准并记录 warning；后续实现可直接拒绝这类信号。

---

## 4. NautilusTrader 消费规则

### 4.1 策略侧规则

Nautilus 策略读取 `SignalEvent` 后，只能生成“订单意图”，不能绕过风险控制。

策略必须检查：

- `schema_version == "signal.v1"`
- `venue` 和运行 venue 一致
- `symbol` 可映射到 Nautilus `InstrumentId`
- 当前时间未超过 `ts_event + ttl_seconds`
- `confidence` 高于策略配置阈值
- `source` 在允许列表内
- `model_version` 在允许列表或灰度列表内

### 4.2 风控侧规则

风险控制必须能独立拦截订单，即使策略接受了信号。

最低风控规则：

- 单日亏损达到 5%，停止新开仓。
- 单标的最大资金占用不超过配置阈值。
- 连续亏损达到阈值，降低仓位或暂停策略。
- 信号过期、重复、乱序时不交易。
- 下单前检查当前账户、持仓、挂单和交易所状态。

### 4.3 降级行为

| 故障 | 行为 |
|---|---|
| 没有新信号 | 不开新仓；已有仓位按 Nautilus 策略规则管理 |
| 信号源挂掉 | 使用最后有效配置，但不复用过期信号 |
| Redis 挂掉 | 切到本地 SQLite/文件中最后已确认信号；只允许减仓或空仓 |
| 信号格式错误 | 丢弃并记录结构化错误 |
| source/model_version 未授权 | 丢弃并记录风控拒绝 |
| Agent 输出异常 | 不进入信号流，只写 AgentAdvice |

---

## 5. 存储和审计

每个 `SignalEvent` 必须可追踪：

- 原始 JSON 不可变保存。
- 记录接收时间、验证结果、消费结果。
- 如果触发交易，保存 signal_id 到订单/交易日志。
- 如果被拒绝，保存拒绝原因。

阶段 1 存 SQLite：

```text
signals(signal_id, schema_version, symbol, venue, ts_event, horizon, side, score,
        confidence, source, model_version, ttl_seconds, raw_json, status, reason,
        created_at, consumed_at)
```

未来可同步写 Postgres，并把 Redis Stream 作为传输层，不作为唯一历史存储。

---

## 6. 明确不做

- 不让 `freqtrade` 直接控制真实订单。
- 不让 Agent 直接输出订单。
- 不把策略参数热更新做进 v1。
- 不在信号里放仓位大小、杠杆和订单类型。
- 不为了桥接去 fork `freqtrade` 或 `nautilus_trader`。
- 不在阶段 1 引入复杂消息总线。

---

## 7. 测试标准

阶段 1 完成前，必须有以下测试：

- 合法 `SignalEvent` 能被写入、读取、校验。
- 缺失必填字段会被拒绝。
- 过期信号会被拒绝。
- 未授权 `source` 或 `model_version` 会被拒绝。
- 重复 `signal_id` 不会重复触发交易。
- 同一批历史信号重复回放，回测结果一致。
- AgentAdvice 不能进入 `signals` 表。
- `ts_event` 单位必须是 Unix **nanoseconds**。freqtrade / pandas 默认 `Timestamp` 是 ms 或 μs，桥接代码必须显式转 ns 整数；测试需覆盖 ms / μs / ns 三种输入边界，错误单位的信号必须被拒绝。

---

## 8. 后续 ADR

后续 ADR 已按阶段拆分为：

- ADR-003：阶段 0/1 的最小项目骨架和目录落地。
- ADR-004：NautilusTrader 回测结果标准格式。
- ADR-005：研究层信号源分类与命名。
- ADR-006：信号源灰度策略与 dry-run。
- ADR-007：paper trading runtime 与 SourcePolicy 升档。
- Future：实盘前硬风控和应急停机规则。

---

**Decided. `SignalEvent v1` 是研究层和执行层之间唯一允许的交易意图输入。**
