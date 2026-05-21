# Postgres + TimescaleDB + pgvector 提前启服务 — Phase 3 entry

- **Date**: 2026-05-21 (UTC)
- **Phase**: 3 entry
- **Owner**: nishiki
- **Status**: Implemented + verified
- **Type**: infra retro
- **Related**:
  - `docs/decisions/001-tech-stack.md` §6 + 2026-05-21 修订（第二段）
  - `infra/docker-compose.yml`
  - `infra/postgres/init.sql`
  - `apps/bridge/store.py`
  - `infra/grafana/provisioning/datasources/datasources.yml`
  - 上一次基建 retro: `docs/retros/2026-05-21-observability-stack-phase3-entry.md`

---

## 1. Scope

按 ADR-001 §6 的 2026-05-21 修订第二段，把 Postgres + TimescaleDB + pgvector
从 Phase 2 提前到 Phase 3 entry **启服务**（不迁移）。本次目的：

- 把 ADR-001 §6 表里 Phase 2 / Phase 3 entry 应该跑但还没跑的 PG 服务起好，
  schema 占位齐备。
- 给 `apps/bridge/store.py` 加 `PostgresSignalStore` 作为可选 backend，
  **SQLite 仍是默认**。
- 给 Grafana 加一个 read-only Postgres datasource，未来直接 SQL 查 trader
  数据，而不是只能用 LogQL 解 jsonl。

**关键边界**：本次**不**迁移 SignalStore 历史数据。bundle 仍是 promotion
source of truth。

## 2. 服务与配置

| 服务 | 镜像 | 端口 | 配置文件 |
|---|---|:-:|---|
| trader-postgres | `timescale/timescaledb-ha:pg16` | 5433 | `infra/postgres/init.sql` |

- host 端口 `127.0.0.1:5433`（5432 已被无关的 `nishiki-postgres` 容器占用）。
- 默认凭证（loopback dev only）：`POSTGRES_USER=trader / POSTGRES_PASSWORD=trader_local_pg / POSTGRES_DB=trader`，
  覆写通过 `.env`：`POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB`。
- 一个只读角色 `trader_ro / trader_ro_local`，仅供 Grafana / 看板用。
- healthcheck：`pg_isready -U trader -d trader`，10 s 间隔。

## 3. 占位表

`infra/postgres/init.sql` 在容器 fresh-init 时执行，建：

- **`signal_events`** — 字段镜像 `apps/bridge/store.py` 的 sqlite `signals`
  表（`signal_id / schema_version / symbol / venue / ts_event / horizon /
  side / score / confidence / source / model_version / ttl_seconds /
  raw_json / status / reason / created_at / consumed_at`），与 SQLite 唯一差
  别是 PK 改成复合 `(signal_id, ts_event)` 以满足 hypertable 的 unique 约束
  规则。Hypertable，chunk_time_interval = 1 day (ns)。索引：`source +
  model_version`、`status`。
- **`orders`** — order_id / venue_order_id / instrument_id / venue / side /
  quantity / price / status / ts_event / signal_id / metadata。PK
  `(order_id, ts_event)`。Hypertable。
- **`fills`** — fill_id / order_id / venue_order_id / instrument_id / side /
  quantity / price / ts_event / signal_id / metadata。PK
  `(fill_id, ts_event)`。Hypertable。
- **`positions`** — position_id / instrument_id / venue / side (LONG/SHORT/
  FLAT) / quantity / avg_px / realized_pnl / opened_ts / closed_ts /
  signal_ids[] / metadata。PK `(position_id, opened_ts)`。Hypertable。
- **`embeddings`** — embedding_id PK / namespace / source_ref /
  `embedding vector(1536)` / metadata / created_ts。pgvector。

`signal_events` 是真 backend；`orders / fills / positions` 是 Phase 2+ 迁
移占位（当前仍以 parquet sidecar 为 source of truth）；`embeddings` 是
Phase 4 agent / mcp_server / n8n 的提前铺设。

修改 schema 需要 `docker compose down -v postgres + up`（fresh-init 仅在第
一次执行 init.sql；之后改 schema 要单独迁移）。

## 4. `apps/bridge/store.py` 新增 backend

- 新类 `PostgresSignalStore` + `PostgresConnInfo` dataclass。
- 接口与 `SignalStore` 一一对应：`write` / `mark` / `get` / `list_by_status`
  / `replay`，返回类型从 `sqlite3.Row` 换成 `dict[str, Any]`。
- `DuplicateSignalError` / `UnknownSignalError` 继续复用；PG 端
  `UniqueViolation` 映射到 `DuplicateSignalError`。
- **默认仍是 `SignalStore` (SQLite)**。CLI / 工厂未做改动；想用 PG backend
  的调用方显式 `PostgresSignalStore()` 实例化。
- `psycopg[binary]>=3.2` 加进 `pyproject.toml` `dependencies`。

## 5. Grafana datasource provisioning

- `infra/grafana/provisioning/datasources/datasources.yml` 加一项
  `Postgres` (uid `postgres-trader`)，通过容器内 DNS `postgres:5432`，使用
  `trader_ro` 只读角色。
- `deleteDatasources` 列表同步加 `Postgres`，让重建 provisioning 时干净。
- `jsonData.timescaledb=true` 让 Grafana 的 PG 插件知道这是 Timescale 实例。

## 6. 验证

```text
docker compose ps                 → trader-postgres healthy
docker exec trader-postgres psql -U trader -d trader \
    -c "SELECT extname, extversion FROM pg_extension
        WHERE extname IN ('timescaledb','vector') ORDER BY extname"
  → timescaledb 2.27.0
    vector      0.8.2

docker exec trader-postgres psql -U trader -d trader -c "\dt"
  → embeddings / fills / orders / positions / signal_events (5 tables)

docker exec trader-postgres psql -U trader -d trader \
    -c "SELECT hypertable_name FROM timescaledb_information.hypertables"
  → fills / orders / positions / signal_events (4 hypertables)

docker exec trader-postgres psql -U trader -d trader \
    -c "SELECT rolname, rolcanlogin FROM pg_roles WHERE rolname='trader_ro'"
  → trader_ro | t
```

End-to-end Grafana → Postgres：

```text
curl -u admin:trader -X POST /api/ds/query   \
    -d '{... "rawSql": "SELECT current_database(), current_user,
              count(*) FROM information_schema.tables
              WHERE table_schema = '\''public'\''" ...}'
  → ['trader', 'trader_ro', 5]
```

测试：

```text
UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q                    → 478 passed
UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/bridge -q       → 93 passed
UV_CACHE_DIR=/tmp/uv-cache uv run ruff check apps tests docs infra → clean
```

新增 7 个 `tests/bridge/test_postgres_store.py` 用例覆盖：
- write / get round-trip
- 重复 `signal_id` 抛 `DuplicateSignalError`
- `mark` unknown signal 抛 `UnknownSignalError`
- `mark consumed` 设 `consumed_at`
- `replay` 按 source + since/until 过滤
- `list_by_status` 按 `ts_event` 正序
- `replay` 返回的 `SignalEvent` payload 与原 event `model_dump()` 完全相等

PG 不可达时整组测试通过 `pytest.skipif` 跳过（不阻塞 CI / 其他 checkout）。

## 7. 不做 / 待做

不做：
- **不迁移** SignalStore 历史数据。
- 不引入 Redis（ADR-010 草稿条件未满足）。
- 不让 PG 成为 promotion 评判依据。
- 不把 PG 凭证写进 git history（密码是 loopback dev only，且可通过
  `infra/.env` 覆盖）。

待做（不在本次范围）：
- 当 paper / testnet / live 真出 SQLite 瓶颈，开一个迁移 ADR，把
  `SignalStore` 默认 backend 从 SQLite 切到 Postgres。
- 给 `apps/bridge/cli.py` 加 `--backend postgres` 让 CLI 用 PG（当前 CLI 是
  SQLite 专属，不动）。
- 给 Grafana 写一个 `signals-overview` dashboard（在 PG 上做 SQL 时序聚合
  显示信号源 / 状态 / 拒绝率随时间）。
- 给 `embeddings` 加真实的 schema：等 Phase 4 agent 真正开 embed 时定 dim。

## 8. 不变 / 不破

- ADR-001 铁律 1–5 全保留。
- ADR-002 SignalEvent v1 / ADR-004 backtest sidecar / ADR-007 paper runtime
  / ADR-008 §6.6 testnet canary 全保留，没有任何字段 / schema / 信号路径
  改动。
- bridge 默认 backend = SQLite。所有现有 SQLite 调用未改、未替换。
- `apps/bridge/cli.py`、`apps/bridge/validators.py` 未动。
- `freqai_linear_v1 / linear-mom-train20240105` 仍在 `hold @ testnet_canary`
  下的 `SourcePolicy(dry_run=False, position_pct_multiplier=0.1,
  min_confidence_override=None)`。
- Grafana 现有 `canary-current` dashboard 未改。
