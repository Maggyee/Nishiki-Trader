# frontend

Next.js + Tailwind 只读运维观察台。

**当前 Phase**：5 entry（只读 operations console）。

## 当前入口

先生成本地只读 snapshot（文件在 `data/` 下，gitignored）：

```bash
uv run python -m apps.ops.dashboard_snapshot \
  --project-status-path docs/project-status.md \
  --agent-advice-db data/agents/advice.db \
  > data/frontend/dashboard-snapshot.json
```

如果需要从前端打开仓库文档链接，可以生成 snapshot 时追加：

```bash
uv run python -m apps.ops.dashboard_snapshot \
  --repo-browser-base-url https://github.com/Maggyee/Nishiki-Trader/blob/main \
  > data/frontend/dashboard-snapshot.json
```

启动前端：

```bash
cd apps/frontend
npm install
npm run dev -- --port 3001
```

构建 / 校验：

```bash
npm audit --audit-level=moderate
npm run typecheck
npm run build
```

`TRADER_DASHBOARD_SNAPSHOT=/abs/path/to/dashboard-snapshot.json` 可以覆盖默认
snapshot 路径。默认路径是仓库根目录下的
`data/frontend/dashboard-snapshot.json`。

语言切换是只读 URL 状态：

- `/?lang=en`：英文
- `/?lang=zh-CN`：简体中文

## 当前展示

- 顶部语言切换：English / 简体中文，不写 cookie、不调用 API
- Operational posture：live gate、strict continuity、生成时间、当前目标
- Guardrail metrics：AgentAdvice 记录数、paper/testnet bundle 输入、阻塞项、order-path 边界
- Runtime health：从 `observability` 读取 Prometheus textfile 摘要，显示心跳、WS、open state、alert 与数据延迟
- Signals & Rejections：从已附加的 passive paper/testnet bundle report 读取
  signal lineage 摘要，按 source/model 显示 accepted、skipped 与 rejection 原因
- Evidence matrix：paper / testnet bundle 数量、审阅阻塞、promotion 阻塞
- AgentAdvice queue：最近 advice 记录、类型、状态、置信度
- Operator checklist：刷新 snapshot、边界检查、AgentAdvice 审阅、连续性阻塞、SourcePolicy 流程
- Watchlist / Verification：从 `docs/project-status.md` 解析 blocked/deferred、next steps、latest verification
- Reference links：文档、证据 ledger、runbook、本地 Grafana 只读看板和其源 JSON
- Boundary ledger：确认前端相关 live/order mutation flags 仍关闭

## 后续可加

- Read-only source/model freshness summaries once approved observability output exists

## 锁定边界

- 当前前端是**只读**界面，只消费 `dashboard.snapshot.v1`
- **不**在前端做下单按钮
- **不**在前端写策略代码
- **不**写 `SignalEvent`
- **不**修改 `SourcePolicy`
- **不**调用交易所 API
- 所有"看起来要改实盘"的动作必须经过 ops 脚本和二次确认，且不属于当前前端范围

参考 `docs/decisions/012-phase5-readonly-dashboard.md`。
