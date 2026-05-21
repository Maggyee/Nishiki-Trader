-- Phase 3 entry: Postgres + TimescaleDB + pgvector 提前启服务初始化脚本.
--
-- ADR-001 §6 2026-05-21 修订第二段: 服务先启, SignalStore 默认仍 SQLite,
-- 等真正出瓶颈再迁数据. 本文件只建 schema 占位, 不导入历史数据.
--
-- 表结构与 ADR-002 SignalEvent v1 / ADR-004 backtest sidecar / ADR-005
-- 信号源分类对齐, 字段约束保持最小, 等迁移时再加 NOT NULL / FK / index.
--
-- 注意: docker-entrypoint-initdb.d/ 下的 .sql 仅在 fresh data 目录初始化
-- 时执行一次. 修改 schema 后需要 ``docker compose down -v`` 删 volume 重建,
-- 或者写迁移 SQL 单独执行.

\connect trader

-- ---------------------------------------------------------------------------
-- 扩展
-- ---------------------------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS timescaledb;
CREATE EXTENSION IF NOT EXISTS vector;

-- ---------------------------------------------------------------------------
-- 角色: trader_ro (Grafana / 看板用, 只读, 不能写不能 DDL)
-- ---------------------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'trader_ro') THEN
        CREATE ROLE trader_ro WITH LOGIN PASSWORD 'trader_ro_local';
    END IF;
END$$;

GRANT CONNECT ON DATABASE trader TO trader_ro;
GRANT USAGE ON SCHEMA public TO trader_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT ON TABLES TO trader_ro;

-- ---------------------------------------------------------------------------
-- 占位表 — 字段对齐 ADR-002 SignalEvent v1 / ADR-004 sidecar.
-- ---------------------------------------------------------------------------

-- signal_events: SignalEvent v1 持久化, 字段镜像 apps/bridge/store.py 的
-- sqlite signals 表 (符号字段命名保持一致: symbol/venue/ts_event/horizon/...),
-- 让 apps.bridge.store.PostgresSignalStore 可以直接 INSERT / SELECT.
-- 与 sqlite schema 区别仅在: PK 是复合 (signal_id, ts_event), 因为 hypertable
-- 要求所有 unique 约束包含 partition column. application 层 (PostgresSignalStore)
-- 保证 signal_id 在同一 ts_event 下唯一; SignalEvent v1 的 signal_id 设计本身
-- 已经包含 source / model / ts, 所以重复检测仍然语义等价.
CREATE TABLE IF NOT EXISTS signal_events (
    signal_id      TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    symbol         TEXT NOT NULL,
    venue          TEXT NOT NULL,
    ts_event       BIGINT NOT NULL,                   -- ns since epoch
    horizon        TEXT NOT NULL,
    side           TEXT NOT NULL,                    -- buy/sell/flat
    score          DOUBLE PRECISION NOT NULL,
    confidence     DOUBLE PRECISION NOT NULL,
    source         TEXT NOT NULL,
    model_version  TEXT NOT NULL,
    ttl_seconds    BIGINT NOT NULL,
    raw_json       TEXT NOT NULL,
    status         TEXT NOT NULL DEFAULT 'pending',
    reason         TEXT,
    created_at     BIGINT NOT NULL,
    consumed_at    BIGINT,
    PRIMARY KEY (signal_id, ts_event)
);
CREATE INDEX IF NOT EXISTS idx_signal_events_source_model
    ON signal_events(source, model_version);
CREATE INDEX IF NOT EXISTS idx_signal_events_status
    ON signal_events(status);
-- chunk_time_interval is 1 day expressed in nanoseconds (matches ts_event BIGINT).
SELECT create_hypertable(
    'signal_events', 'ts_event',
    chunk_time_interval => 86400000000000::BIGINT,
    if_not_exists => TRUE
);

-- orders / fills / positions: ADR-004 sidecar 三件套 (后续 backtest_runner
-- / live sidecar writer 共用 schema).
CREATE TABLE IF NOT EXISTS orders (
    order_id         TEXT NOT NULL,
    venue_order_id   TEXT,
    instrument_id    TEXT NOT NULL,
    venue            TEXT NOT NULL,
    side             TEXT NOT NULL,
    quantity         NUMERIC,
    price            NUMERIC,
    status           TEXT,
    ts_event         BIGINT NOT NULL,
    signal_id        TEXT,
    metadata         JSONB,
    PRIMARY KEY (order_id, ts_event)
);
SELECT create_hypertable(
    'orders', 'ts_event',
    chunk_time_interval => 86400000000000::BIGINT,
    if_not_exists => TRUE
);

CREATE TABLE IF NOT EXISTS fills (
    fill_id          TEXT NOT NULL,
    order_id         TEXT NOT NULL,
    venue_order_id   TEXT,
    instrument_id    TEXT NOT NULL,
    side             TEXT NOT NULL,
    quantity         NUMERIC,
    price            NUMERIC,
    ts_event         BIGINT NOT NULL,
    signal_id        TEXT,
    metadata         JSONB,
    PRIMARY KEY (fill_id, ts_event)
);
SELECT create_hypertable(
    'fills', 'ts_event',
    chunk_time_interval => 86400000000000::BIGINT,
    if_not_exists => TRUE
);

CREATE TABLE IF NOT EXISTS positions (
    position_id      TEXT NOT NULL,
    instrument_id    TEXT NOT NULL,
    venue            TEXT NOT NULL,
    side             TEXT NOT NULL,                    -- LONG/SHORT/FLAT
    quantity         NUMERIC,
    avg_px           NUMERIC,
    realized_pnl     NUMERIC,
    opened_ts        BIGINT NOT NULL,
    closed_ts        BIGINT,
    signal_ids       TEXT[],
    metadata         JSONB,
    PRIMARY KEY (position_id, opened_ts)
);
SELECT create_hypertable(
    'positions', 'opened_ts',
    chunk_time_interval => 86400000000000::BIGINT,
    if_not_exists => TRUE
);

-- embeddings: pgvector 占位, 给 Phase 4 agent / mcp_server 用.
-- 维度先按 1536 (OpenAI ada / 兼容多数 LLM embedding), 真正用前再 ALTER.
CREATE TABLE IF NOT EXISTS embeddings (
    embedding_id     TEXT PRIMARY KEY,
    namespace        TEXT NOT NULL,                    -- e.g. "signal", "retro", "doc"
    source_ref       TEXT NOT NULL,                    -- e.g. signal_id, doc path
    embedding        vector(1536),
    metadata         JSONB,
    created_ts       BIGINT NOT NULL
);

-- 把现有表的 SELECT 也给 trader_ro (init 时 DEFAULT PRIVILEGES 只对后续生效).
GRANT SELECT ON ALL TABLES IN SCHEMA public TO trader_ro;
