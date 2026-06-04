# agents

LLM agent 编排（Claude SDK + tool-use）和 AgentAdvice 审计存储。

**当前 Phase**：4 entry（AgentAdvice audit foundation）。

## 当前入口

AgentAdvice 是 Phase 4 的第一条落地边界：它只能记录研究、复盘、journal
和参数候选建议，不能写 `SignalEvent`，不能下单，不能改 `SourcePolicy`。

写一条 journal：

```bash
uv run python -m apps.agents.cli \
  --db data/agents/advice.db \
  journal \
  --agent-name review_agent \
  --content "BTCUSDT testnet canary evidence remains operational, not alpha." \
  --tag testnet \
  --tag retro
```

从 JSON/JSONL 批量写入：

```bash
uv run python -m apps.agents.cli \
  --db data/agents/advice.db \
  write data/agents/advice.jsonl
```

按 JSONL 查询：

```bash
uv run python -m apps.agents.cli \
  --db data/agents/advice.db \
  list --agent-name review_agent --advice-type journal
```

人工复核：

```bash
uv run python -m apps.agents.cli \
  --db data/agents/advice.db \
  review '<advice_id>' --decision accepted --reviewed-by nishiki
```

## 计划 agent 列表

| Agent | 用途 | 最早 Phase |
|---|---|:-:|
| 复盘 agent | 每日读交易 + 新闻，写 journal | 4 |
| 数据分析 agent | 跑统计、出图、找异常 | 4 |
| 金融专家 agent | 宏观偏向（多/空/中性），作为仓位乘数 | 4 |
| 策略 brainstorm | 用户对话辅助 | 4+ |

## 锁定边界（contract §5）

- Agent 只产 `AgentAdvice` 记录，**不产 `SignalEvent`**
- Agent **不调用真实交易 API**
- Agent **不绕过** nautilus RiskEngine
- AgentAdvice payload 会拒绝结构化下单字段（如 `order_type` / `quantity` /
  `leverage` / `take_profit`）
- Agent 异常 / 超时 / 输出格式错误 → 仓位乘数回到 1.0，按裸策略继续跑（ADR-001 铁律 3）
- 阶段 4 同时只跑 1 个 agent；多 agent 协作要 ADR 单独决策
