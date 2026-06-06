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

## 当前展示

- Operational posture：live gate、strict continuity、生成时间、当前目标
- Guardrail metrics：AgentAdvice 记录数、paper/testnet bundle 输入、阻塞项、order-path 边界
- Evidence matrix：paper / testnet bundle 数量、审阅阻塞、promotion 阻塞
- AgentAdvice queue：最近 advice 记录、类型、状态、置信度
- Operator checklist：刷新 snapshot、边界检查、AgentAdvice 审阅、连续性阻塞、SourcePolicy 流程
- Watchlist / Verification：从 `docs/project-status.md` 解析 blocked/deferred、next steps、latest verification
- Boundary ledger：确认前端相关 live/order mutation flags 仍关闭

## 后续可加

- Grafana / frontend source-of-truth-neutral cross-links
- Passive service-liveness and data-lag summaries from existing observability outputs
- Read-only signal-source distribution and rejection summaries from approved reports

## 锁定边界

- 当前前端是**只读**界面，只消费 `dashboard.snapshot.v1`
- **不**在前端做下单按钮
- **不**在前端写策略代码
- **不**写 `SignalEvent`
- **不**修改 `SourcePolicy`
- **不**调用交易所 API
- 所有"看起来要改实盘"的动作必须经过 ops 脚本和二次确认，且不属于当前前端范围

参考 `docs/decisions/012-phase5-readonly-dashboard.md`。
