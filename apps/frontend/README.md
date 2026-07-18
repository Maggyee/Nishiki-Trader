# frontend

Next.js + Tailwind 只读运维观察台。

**当前 Phase**：5 entry（只读 operations console）。

## 当前入口

先生成本地只读 snapshot（文件在 `data/` 下，gitignored）：

```bash
uv run python -m apps.ops.research_v5_collector_status \
  --ssh-host oracle \
  --data-root /var/lib/nishiki-trader/research-v5 \
  --checkout /opt/nishiki-trader-v5-d37d227 \
  --image nishiki-research-v5:d37d227874d49e88e8e8857f1bf45ea426ee7a3d \
  > data/frontend/research-v5-collector-status.json

uv run python -m apps.ops.dashboard_snapshot \
  --project-status-path docs/project-status.md \
  --agent-advice-db data/agents/advice.db \
  --research-v5-collector-status data/frontend/research-v5-collector-status.json \
  > data/frontend/dashboard-snapshot.json
```

`--ssh-host` 只通过 BatchMode SSH 执行 `systemctl`、`journalctl`、`git`、
`docker image inspect` 和 `find` 读取；不会向云主机写文件，也不会加载凭据、
启动采集器或触发重试。未附加 collector status artifact 时，前端显示
`not attached`，不会自行连接远端。

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
快照年龄的 aging/stale 阈值来自 snapshot 内的 `snapshot_freshness` 策略；需要
调整时在生成 snapshot 时传入 `--snapshot-warning-after-seconds` 和
`--snapshot-stale-after-seconds`，前端不会自行刷新或触发 runner。

语言切换是只读 URL 状态：

- `/?lang=en`：英文
- `/?lang=zh-CN`：简体中文

## 当前展示

- 顶部语言切换：English / 简体中文，不写 cookie、不调用 API
- Operational posture：live gate、strict continuity、生成时间、快照年龄、当前目标
- Guardrail metrics：AgentAdvice 记录数、paper/testnet bundle 输入、阻塞项、order-path 边界
- Runtime health：从 `observability` 读取 Prometheus textfile 摘要，显示心跳、WS、open state、alert 与数据延迟
- Protocol v5 Collector：显示最近运行时间与数据日期、BTC/ETH curve/BVOL
  四路成功/失败、失败类型与计划重试、snapshot/Parquet/conflict 数量，以及
  部署 commit、镜像 SHA 和 revision；该面板只消费
  `research.v5.collector_status.v1`
- Signals & Rejections：从已附加的 passive paper/testnet bundle report 读取
  signal lineage 摘要，按 source/model 显示 accepted、skipped、rejection 原因与
  最新信号 freshness，并展示只读 evidence 链接（Grafana source/model
  drill-down、本地 bundle 路径、testnet evidence ledger）
- Evidence matrix：paper / testnet bundle 数量、审阅阻塞、promotion 阻塞
- AgentAdvice queue：最近 advice 记录、类型、状态、置信度
- Operator checklist：刷新 snapshot、边界检查、AgentAdvice 审阅、连续性阻塞、SourcePolicy 流程
- Snapshot Source：显示当前页面读取的 snapshot 路径、加载状态、生成时间、
  freshness 阈值、评估方与加载错误
- Snapshot Inputs：显示生成 snapshot 时声明的只读输入路径、是否附加、是否存在，
  包括 project status、AgentAdvice DB、bundle、Phase 6 artifact 与 observability textfile
- Phase 6 Gates：显示已附加 readiness/startup guard artifact 的只读状态、
  阻塞项、检查数量，以及 promotion review artifact / SHA-256 匹配证据
- Watchlist / Verification：从 `docs/project-status.md` 解析 blocked/deferred、next steps、latest verification
- Reference links：文档、证据 ledger、runbook、本地 Grafana 只读看板和其源 JSON
- Boundary ledger：确认前端相关 live/order mutation flags 仍关闭

## 锁定边界

- 当前前端是**只读**界面，只消费 `dashboard.snapshot.v1`
- **不**在前端做下单按钮
- **不**在前端写策略代码
- **不**写 `SignalEvent`
- **不**修改 `SourcePolicy`
- **不**调用交易所 API
- **不**从前端触发 collector、timer 或重试
- 所有"看起来要改实盘"的动作必须经过 ops 脚本和二次确认，且不属于当前前端范围

参考 `docs/decisions/012-phase5-readonly-dashboard.md`。
