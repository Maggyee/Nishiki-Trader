# Trader

个人量化交易系统：LLM 多 agent 研究层 + freqtrade ML 信号层 + nautilus_trader 执行层。

## 必读（动手前）

1. [`AGENTS.md`](AGENTS.md) / [`CLAUDE.md`](CLAUDE.md) — agent 入口约束
2. [`PLAN.md`](PLAN.md) — 长期路线
3. [`docs/agent-operating-contract.md`](docs/agent-operating-contract.md) — 操作契约
4. [`docs/decisions/001-tech-stack.md`](docs/decisions/001-tech-stack.md) — 技术栈与五条铁律
5. [`docs/decisions/002-signal-bridge-protocol.md`](docs/decisions/002-signal-bridge-protocol.md) — SignalEvent v1

## 目录

| 路径 | 用途 | 是否修改 |
|---|---|---|
| `freqtrade/` | upstream | 只读 |
| `nautilus_trader/` | upstream | 只读 |
| `apps/` | 项目自有代码 | 主要工作区 |
| `infra/` | docker-compose / DB init / dashboards | 主要工作区 |
| `docs/` | ADR、runbook、retros | 文档区 |
| `notebooks/` | 研究脚本 | 草稿区 |
| `data/` | 本地数据缓存 | gitignored |
| `tests/` | 镜像 `apps/` 的测试 | 跟着 apps 走 |

## 当前阶段

**Phase 0** — 项目骨架。仅允许：

- SQLite + Parquet（本地文件，非长驻服务）
- nautilus_trader（backtest 模式）

PG / Redis / Grafana / Frontend / agent / n8n 都还没激活。
长期服务激活时间表见 [`docs/decisions/001-tech-stack.md`](docs/decisions/001-tech-stack.md) §6。

## 开发环境

```bash
# 安装 uv（如未安装）
curl -LsSf https://astral.sh/uv/install.sh | sh

# 同步开发依赖
uv sync

# 跑测试 / lint
uv run pytest
uv run ruff check .
uv run ruff format --check .
```
