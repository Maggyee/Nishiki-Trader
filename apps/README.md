# apps/

项目自有代码。两个 upstream 仓库（`freqtrade/`、`nautilus_trader/`）不在这里、不可改。

| 子目录 | 用途 | 激活 Phase | 状态 |
|---|---|:-:|:-:|
| `bridge/` | SignalEvent v1 schema + 验证 + SQLite 落地 | 1 | 空骨架 |
| `strategies_nautilus/` | nautilus 自定义 Strategy / Actor / 风控 | 1 | 空骨架 |
| `strategies_freqtrade/` | freqtrade 策略（通过 `--userdir` 加载） | 2 | 空骨架 |
| `ops/` | 运维脚本、应急平仓、健康检查 | 1 | 空骨架 |
| `agents/` | LLM agent（Claude SDK） | 4 | 占位 |
| `mcp_server/` | 给 agent / Claude Code 用的工具 | 4 | 占位 |
| `frontend/` | Next.js 监控面板 | 5 | 占位 |

**当前 Phase 0**：除 README 占位外，Phase 2–5 的目录里不写代码。
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

- `agents/` / `mcp_server/` **不进入这条路径**，只写 AgentAdvice
- `bridge/` 是研究层向执行层的**唯一**入口
