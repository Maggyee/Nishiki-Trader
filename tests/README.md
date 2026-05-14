# tests

镜像 `apps/` 结构，每个模块独立测试目录。

```text
tests/
├── __init__.py
├── bridge/               # Phase 1
├── strategies_nautilus/  # Phase 1
├── ops/                  # Phase 1
├── strategies_freqtrade/ # Phase 2
├── agents/               # Phase 4
└── mcp_server/           # Phase 4
```

跑：

```bash
uv run pytest                       # 全部
uv run pytest tests/bridge/         # 只跑 bridge
uv run pytest -k "ttl"              # 按关键字筛选
```

## 优先级（按"破坏交易系统的能力"排）

| 优先级 | 模块 | 必测点 |
|---|---|---|
| 高 | bridge | SignalEvent schema / ttl 过期 / 重复 signal_id / ts_event ns 转换 / 未授权 source |
| 高 | strategies_nautilus | 风控拦截 / 降级行为 / 单日 5% 停机 |
| 中 | ops | 应急脚本 dry-run / 二次确认参数 |
| 中 | strategies_freqtrade | freqai 输出能转成合法 SignalEvent |
| 低 | agents | mock LLM，验证 AgentAdvice 不进 signals 表 |
| 低 | mcp_server | 工具白名单 / 审计日志 |
