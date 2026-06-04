# apps/

项目自有代码。两个 upstream 仓库（`freqtrade/`、`nautilus_trader/`）不在这里、不可改。

| 子目录 | 用途 | 激活 Phase | 状态 |
|---|---|:-:|:-:|
| `bridge/` | SignalEvent v1 schema + 验证 + SQLite 落地 | 1 | live |
| `strategies_nautilus/` | nautilus 自定义 Strategy / Actor / 风控 | 1 | Phase 3 testnet |
| `strategies_freqtrade/` | freqtrade 策略（通过 `--userdir` 加载） | 2 | research signals |
| `ops/` | 运维脚本、应急平仓、健康检查 | 1 | fixture / mirror / snapshot ops |
| `agents/` | LLM agent（Claude SDK） | 4 | AgentAdvice audit + review agent |
| `mcp_server/` | 给 agent / Claude Code 用的工具 | 4 | AgentAdvice wrappers |
| `frontend/` | Next.js 监控面板 | 5 | read-only dashboard shell |

**当前 Phase 5 entry**：只读 frontend 已经开始消费 `dashboard.snapshot.v1`；
Agent research 仍通过 AgentAdvice 审计表、deterministic review agent、
MCP-facing wrappers、以及只读 dashboard snapshot 工作。
Phase 3 live-readiness gate 仍未满足；Phase 5 代码不得进入订单路径。
参考 `docs/decisions/001-tech-stack.md` §6 服务激活时间表。

## 跨模块边界（contract §5）

```text
freqtrade / FreqAI / research
  -> bridge (SignalEvent v1)
  -> strategies_nautilus (NautilusTrader Strategy)
  -> NautilusTrader RiskEngine
  -> NautilusTrader ExecutionEngine
  -> Exchange (binance testnet/live)
```

- `agents/` / `mcp_server` / `frontend/` **不进入这条路径**；agent 侧只写
  AgentAdvice，frontend 只读 snapshot
- `bridge/` 是研究层向执行层的**唯一**入口
