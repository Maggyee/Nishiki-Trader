# infra

基础设施配置。

**当前 Phase**：0。`docker-compose.yml` 暂为 stub，无长驻服务。

## 服务激活时间表（摘自 ADR-001 §6）

| 服务 | 激活 Phase |
|---|:-:|
| SQLite + Parquet（非独立服务） | 0 |
| nautilus（backtest 模式） | 0 |
| freqtrade + signal bridge | 1 |
| postgres + TimescaleDB + pgvector | 2 |
| redis（Stream） | 2 |
| nautilus 连 Binance **testnet** | 3 |
| agent-orchestrator / mcp-server / n8n | 4 |
| grafana + prometheus + loki | 5 |
| frontend | 5 |
| nautilus 连 Binance **真实账户** | 6 |

## 子目录

| 路径 | 用途 | 激活 Phase |
|---|---|:-:|
| `postgres/` | `init.sql`（启 Timescale + pgvector + 建库） | 2 |
| `grafana/dashboards/` | 看板 JSON | 5 |
| `n8n/workflows/` | 工作流 JSON | 4 |

## 部署

Phase 0–5 都跑在**单台 VPS** + `docker compose`。
Phase 6 实盘后是否分离机器，由 ADR-005（待写）决定。
