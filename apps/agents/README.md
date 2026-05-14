# agents

LLM agent 编排（Claude SDK + tool-use）。

**当前 Phase**：0（占位）。代码 Phase 4 开始写。

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
- Agent 异常 / 超时 / 输出格式错误 → 仓位乘数回到 1.0，按裸策略继续跑（ADR-001 铁律 3）
- 阶段 4 同时只跑 1 个 agent；多 agent 协作要 ADR 单独决策
