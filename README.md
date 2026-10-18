# Trader

个人量化交易系统：研究层（freqtrade/FreqAI + 自研研究代码）产出 `SignalEvent v1`
信号，NautilusTrader 负责唯一的执行与风控，LLM agent 只做研究和复盘。

## 必读

1. [`AGENTS.md`](AGENTS.md)：所有 agent（Codex / Claude）的唯一入口
2. [`docs/project-status.md`](docs/project-status.md)：当前进度、下一步、阻塞
3. [`docs/decisions/`](docs/decisions/README.md)：ADR 索引（ADR-001 五条铁律、ADR-002 SignalEvent v1）
4. [`docs/research/`](docs/research/README.md)：研究结论与 W1–W10 警告
5. [`PLAN.md`](PLAN.md)：长期路线；[`docs/history.md`](docs/history.md)：历史与教训

## 目录

| 路径 | 用途 |
|---|---|
| `apps/bridge/` | SignalEvent v1、信号库、校验 |
| `apps/strategies_nautilus/` | baseline 策略、backtest / paper / testnet runner、应急平仓、实盘启动守卫 |
| `apps/strategies_freqtrade/` | freqtrade user_data，新的研究信号 exporter 放这里 |
| `apps/agents/`、`apps/mcp_server/` | AgentAdvice 审计库、review agent、MCP 工具 |
| `apps/ops/` | 数据回填、审计、live readiness、dashboard 快照、PG 同步 |
| `apps/frontend/` | 只读 dashboard（Next.js） |
| `infra/` | 观测栈、Postgres、testnet watchdog、CI 模板 |
| `docs/` | ADR、runbook、研究结论、状态 |
| `data/` | 本地数据和证据（gitignored） |
| `tests/` | 镜像 `apps/` |
| `freqtrade/`、`nautilus_trader/` | upstream，只读 |

## 当前阶段

Phase 5 entry：只读监控。实盘被阻塞，目前还没有策略被证明有 alpha。
2026-10-17 做过一次精简，研究协议 v2–v53 和 egress 验证链都已移出主线，
完整历史保存在 tag `archive/pre-slim-2026-10-17`。

## 开发环境

```bash
uv sync
uv run pytest
uv run ruff check apps tests
(cd apps/frontend && npm run typecheck)
```
