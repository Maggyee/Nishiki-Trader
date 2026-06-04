# mcp_server

MCP server，向 Claude Code / Claude Desktop / agents 暴露工具调用。

**当前 Phase**：4 entry（AgentAdvice 工具包装层）。

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

当前 Phase 4 代码入口是普通 Python wrapper，不启动 MCP 服务、不引入新依赖：

```python
from apps.mcp_server import AgentAdviceToolContext, query_agent_advice, write_journal

ctx = AgentAdviceToolContext(
    advice_db_path="data/agents/advice.db",
    audit_log_path="data/agents/mcp_tool_audit.jsonl",
)
write_journal(
    context=ctx,
    agent_name="review_agent",
    advice_id="review_agent:journal:1778760000000000000:manual",
    created_at_ns=1778760000000000000,
    content="Record a research note.",
)
rows = query_agent_advice(context=ctx, agent_name="review_agent")
```

MCP server 后续只允许包装这类审计写入 / 查询接口；不能绕过
`apps.agents.advice.AgentAdvice` schema，也不能写 `signals` 表。每次 wrapper
调用都会追加 `data/agents/mcp_tool_audit.jsonl` 审计行。

触发类（Phase 5+ 才开放，且要二次确认）：

- `run_backtest(strategy, params, period)` — 触发回测，不影响实盘

## 锁定边界

- **不**暴露下单工具
- **不**暴露写 `signals` 表的工具
- **不**暴露修改运行中策略参数的工具
- 所有调用都记审计日志
