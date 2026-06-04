# frontend

Next.js + Tailwind 监控面板。

**当前 Phase**：5 entry（只读 dashboard shell）。

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

## 计划展示

- 策略版本 / 启停 / 回测曲线
- 持仓 / PnL / 回撤 / 风险状态
- 信号流 / 拒绝原因 / source 分布
- Agent 建议历史 / 准确率
- 服务存活 / 数据延迟 / 报警

## 锁定边界

- 当前前端是**只读**界面，只消费 `dashboard.snapshot.v1`
- **不**在前端做下单按钮
- **不**在前端写策略代码
- **不**写 `SignalEvent`
- **不**修改 `SourcePolicy`
- **不**调用交易所 API
- 所有"看起来要改实盘"的动作必须经过 ops 脚本和二次确认，且不属于当前前端范围

参考 `docs/decisions/012-phase5-readonly-dashboard.md`。
