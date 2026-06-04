# mcp_server

MCP server，向 Claude Code / Claude Desktop / agents 暴露工具调用。

**当前 Phase**：0（占位）。代码 Phase 4 开始写。

## 计划工具

只读类（安全）：

- `query_bars(symbol, timeframe, from, to)`
- `query_trades(symbol, from, to)`
- `query_positions()`
- `query_pnl(period)`
- `query_signals(filter)`
- `query_agent_advice(filter)`

只写 `AgentAdvice` 类：

- `write_journal(content, tags)`
- `write_agent_advice(advice_type, payload, confidence)`

当前 AgentAdvice 本地审计存储已经落在 `apps.agents`：

```bash
uv run python -m apps.agents.cli list --db data/agents/advice.db
```

MCP server 后续只允许包装这类审计写入 / 查询接口；不能绕过
`apps.agents.advice.AgentAdvice` schema，也不能写 `signals` 表。

触发类（Phase 5+ 才开放，且要二次确认）：

- `run_backtest(strategy, params, period)` — 触发回测，不影响实盘

## 锁定边界

- **不**暴露下单工具
- **不**暴露写 `signals` 表的工具
- **不**暴露修改运行中策略参数的工具
- 所有调用都记审计日志
