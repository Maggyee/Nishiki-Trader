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

默认单元测试禁止 socket 网络连接，采集器使用注入的固定样本。联网集成测试
必须标记 `network`；CI 执行 `pytest -m 'not network and not postgres'`。

Postgres 测试不再探测或清空默认业务数据库。仅在显式设置
`TRADER_TEST_POSTGRES_DSN` 时运行；目标数据库名必须以 `_test` 结尾，
每个测试使用独立随机 schema，结束后仅删除自己创建的 schema。
业务库 `trader` 不可用作测试目标。未设置 DSN 时这些测试跳过。

前端 Phase 5 校验在 `apps/frontend` 内运行：

```bash
npm audit --audit-level=moderate
npm run typecheck
npm run build
```

## 优先级（按"破坏交易系统的能力"排）

| 优先级 | 模块 | 必测点 |
|---|---|---|
| 高 | bridge | SignalEvent schema / ttl 过期 / 重复 signal_id / ts_event ns 转换 / 未授权 source |
| 高 | strategies_nautilus | 风控拦截 / 降级行为 / 单日 5% 停机 |
| 中 | ops | 应急脚本 dry-run / 二次确认参数 / dashboard snapshot 只读汇总 |
| 中 | strategies_freqtrade | freqai 输出能转成合法 SignalEvent |
| 低 | agents | deterministic review agent，验证 AgentAdvice 不进 signals 表 |
| 低 | mcp_server | 工具白名单 / 审计日志 |
| 低 | frontend | 只读 dashboard build / snapshot contract display |
