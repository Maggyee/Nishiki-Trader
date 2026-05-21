# infra

基础设施配置。

**当前 Phase**：3 entry。`docker-compose.yml` 启用观测栈
（prometheus + grafana + loki + promtail + node_exporter），其余服务仍占位。

## 服务激活时间表（摘自 ADR-001 §6，含观测栈提前启用补丁）

| 服务 | 计划 Phase | 实际启用 |
|---|:-:|:-:|
| SQLite + Parquet（非独立服务） | 0 | 0 |
| nautilus（backtest 模式） | 0 | 0 |
| freqtrade + signal bridge | 1 | 1 |
| postgres + TimescaleDB + pgvector | 2 | **3 entry（仅启服务，不迁移）** |
| redis（Stream） | 2 | （未启用，待 ADR-010） |
| nautilus 连 Binance **testnet** | 3 | 3 |
| **grafana + prometheus + loki + promtail + node_exporter** | 5 | **3 entry（提前）** |
| agent-orchestrator / mcp-server / n8n | 4 | （未启用） |
| frontend | 5 | （未启用） |
| nautilus 连 Binance **真实账户** | 6 | （未启用，需 live-risk ADR） |

观测栈提前到 Phase 3 entry 的依据：testnet canary 已经在产
heartbeat / alerts / manifest / sidecar 数据，被监控对象已齐；
观测栈不动信号/订单路径，破坏风险最低。

## 子目录

| 路径 | 用途 | 激活状态 |
|---|---|:-:|
| `prometheus/` | scrape 配置 | 3 entry |
| `loki/` | Loki 单机配置 | 3 entry |
| `promtail/` | jsonl 日志采集 | 3 entry |
| `grafana/provisioning/` | 数据源 + dashboards 自动注册 | 3 entry |
| `grafana/dashboards/` | 看板 JSON | 3 entry |
| `watchdog/` | Phase 3 testnet heartbeat watchdog（不读凭证，超时调用 emergency flatten） | 3 |
| `postgres/` | `init.sql`（启 Timescale + pgvector + 占位 schema + trader_ro） | 3 entry |
| `n8n/workflows/` | 工作流 JSON | 占位（未启用） |

## 部署

Phase 0–5 都跑在**单台 VPS** + `docker compose`。
Phase 6 实盘后是否分离机器，由 ADR-005（待写）决定。
