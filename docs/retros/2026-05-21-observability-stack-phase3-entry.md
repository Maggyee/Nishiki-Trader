# Observability Stack 提前接入 — Phase 3 entry

- **Date**: 2026-05-21 (UTC)
- **Phase**: 3 entry
- **Owner**: nishiki
- **Status**: Implemented + verified
- **Type**: infra retro
- **Related**:
  - `docs/decisions/001-tech-stack.md` §6 + 2026-05-21 修订
  - `infra/docker-compose.yml`
  - `apps/strategies_nautilus/runners/textfile_metrics.py`
  - `apps/strategies_nautilus/runners/testnet_runner.py`

---

## 1. Scope

按 ADR-001 §6 的 2026-05-21 修订，把 grafana + prometheus + loki（及支撑组件
promtail / node_exporter）从 Phase 5 提前到 Phase 3 entry。本次目的：让正在
进行中的 ADR-008 §6.6 testnet canary 不再依赖 `grep heartbeat.jsonl + jq` 做
运行时观察。

观测栈**只读** `data/testnet/<run_id>/logs/` /
`data/paper/<run_id>/logs/` /
`data/observability/textfile/<kind>-<run_id>.prom`。不接 SignalStore，不读
exchange 凭证，不改写信号/订单路径。

## 2. 服务清单与端口

所有 host 端口都绑 `127.0.0.1`，不暴露公网。

| 服务 | 镜像 | 端口 | 配置文件 |
|---|---|:-:|---|
| Prometheus | `prom/prometheus:v2.55.1` | 9090 | `infra/prometheus/prometheus.yml` |
| node_exporter | `prom/node-exporter:v1.8.2` | 9100 | (textfile collector, `data/observability/textfile`) |
| Loki | `grafana/loki:3.2.1` | 3100 | `infra/loki/loki-config.yml` |
| Promtail | `grafana/promtail:3.2.1` | 9080 | `infra/promtail/promtail.yml` |
| Grafana | `grafana/grafana:11.3.1` | 3000 | `infra/grafana/provisioning/` |

数据保留：
- Prometheus TSDB：30 天 (`--storage.tsdb.retention.time=30d`)
- Loki：30 天 (`limits_config.retention_period: 30d` + `compactor.retention_enabled: true`)

## 3. 指标暴露路径

`testnet_runner.py --long-run` 在 monitor loop 里每个 sample 之后写一份
Prometheus textfile collector `.prom` 文件到
`data/observability/textfile/testnet-<run_id>.prom`（默认）；node_exporter 挂
该目录后 expose 在 `:9100/metrics`，Prometheus 抓 `node_exporter`
target 即可看到。

`testnet_runner.py` 关闭时 (`finally` 块) `cleanup()` 删除该 `.prom`，让
node_exporter 不再 expose stale 指标。Prometheus TSDB 已经持久化历史 series，
30 天保留窗口内可继续查询。

导出指标（前缀 `trader_canary_`）：

- gauges: `ws_connected`, `daily_pnl_usdt`, `account_total_usdt`,
  `open_orders`, `open_positions`, `last_bar_timestamp_seconds`,
  `last_signal_timestamp_seconds`, `heartbeat_timestamp_seconds`,
  `starting_balance_usdt`, `daily_loss_limit_pct`, `info`
- counters: `ws_reconnect_total`, `exchange_error_total`,
  `alert_total{alert=…}`

每个指标都带 `{kind, run_id}` label。

## 4. 日志路径

Promtail 在容器内挂 `../data/testnet:/data/testnet:ro` 和
`../data/paper:/data/paper:ro`，scrape 三个 testnet jsonl + 一个 paper jsonl：

| job | 文件 | label 提取 |
|---|---|---|
| `testnet_runtime` | `data/testnet/*/logs/runtime.log` | `run_id` |
| `testnet_heartbeat` | `data/testnet/*/logs/heartbeat.jsonl` | `run_id` |
| `testnet_alerts` | `data/testnet/*/logs/alerts.log` | `run_id, severity, msg` |
| `paper_runtime` | `data/paper/*/logs/runtime.log` | `run_id` |

时间戳从 jsonl 的 `ts` 字段取（ISO ms UTC），不用文件 mtime。

`infra/watchdog/state.json` **没有进 Loki**：它是 overwrite 模式（每次 tick
覆写整个 JSON 对象），Promtail 不能 tail。Watchdog 的 `heartbeat_lost` alert
已经 append 到 `data/testnet/<run_id>/logs/alerts.log`，因此被
`testnet_alerts` job 覆盖。

## 5. Grafana dashboard

provisioning 把 `infra/grafana/dashboards/*.json` 自动加载到 folder `trader`。
本次落地一个：

- `canary-current.json` (uid: `canary-current`)
  - Row 1 (Runtime, 6 stat + 4 time-series panel): ws_connected, account
    total, daily PnL, open orders/positions, ws reconnects + 时序图 + alert
    counts + heartbeat freshness（`time() - heartbeat_timestamp_seconds`，
    黄阈值 60s / 红阈值 120s）。
  - Row 2 (Logs & Alerts, 2 logs panel): `alerts.log` 和 `heartbeat.jsonl` 倒
    序展示。
  - Template variable `run_id` 从 `label_values(trader_canary_info, run_id)`
    填充，支持多选 / All。

## 6. 验证

```text
docker compose ps  # 5 containers all Up + ready (prometheus / loki /
                   # grafana / promtail / node_exporter)
curl :9090/-/ready             → "Prometheus Server is Ready."
curl :3100/ready               → "ready"
curl :3000/api/health          → {"database":"ok", "version":"11.3.1"}
curl :9080/ready               → "Ready"
curl :9100/metrics             → exposes go_* + textfile metrics

prometheus targets:            node_exporter health=up, prometheus health=up
grafana datasources:           Prometheus + Loki provisioned, both editable=false
grafana dashboards:            canary-current loaded into folder "trader",
                               14 panels (2 rows + 12 data panels)
```

End-to-end smoke：手写 `data/observability/textfile/testnet-smoke.prom`
内容 `trader_canary_info{kind="testnet",run_id="smoke-test"} 1`，**15s
scrape 间隔后**用 PromQL `trader_canary_info` 查询返回该 series，labels
`{kind="testnet", run_id="smoke-test", instance="node_exporter:9100",
job="node_exporter"}`。文件删除后 Prometheus 历史 series 仍可查。

Loki 端到端：Promtail 启动后立即把历史 testnet/paper bundle 的 jsonl 全部
吸入 Loki，`label_values(run_id)` 返回 20 个历史 run_id（覆盖 2026-05-17 到
2026-05-21 的所有 canary + paper bundle）。`testnet_heartbeat` job 第一条
查询返回 `run_id=20260520-040143Z-90c3c62b` 的 heartbeat（含 ws_connected,
last_bar_ns, account_total_usdt, daily_pnl 等字段）。

测试 & lint：

```text
UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q                     → 466 passed
UV_CACHE_DIR=/tmp/uv-cache uv run ruff check apps tests docs infra → all checks passed
```

新增的 18 个 textfile metric 单测覆盖：
- `render_textfile_metrics` 的 HELP/TYPE 配对、run identity labels、可选字段
  omit、alert_total 多 label、ws_connected 0/1、label escape、starting balance
  + daily_loss_limit_pct 暴露
- `write_textfile_atomic` 不 append / 不留 tmp / 自动 mkdir
- `PrometheusTextfileWriter` path 命名、record_alert 累积、cleanup 幂等
- `LongRunningTestnetSettings.observability_textfile_dir` 默认 None / 可设置
- `run_long_running_testnet` 注入 writer → write_sample 至少 1 次 + cleanup
  恰好 1 次 + 文件被删 + content 含 identity labels
- `run_long_running_testnet` `observability_textfile_dir=None` → 全程不写
  `.prom`
- `run_long_running_testnet` ws_connected=False 样本 → 记录
  `ws_disconnected` alert 计数到 textfile

## 7. 不做 / 待做

不做：
- 把 watchdog `state.json` 推到 Loki（设计上是覆写式不适合 tail）。
- 让观测栈成为 promotion 评判依据（bundle 仍是 source of truth）。
- 公网暴露 / OAuth / multi-org（个人 VPS，绑 loopback 即可）。

待做（不在本次范围）：
- 给 watchdog 加一个 append-only jsonl 历史日志，让 Promtail 也能抓
  watchdog 自己的 tick 记录。
- 给 `LiveTelemetryReader` 补 `exchange_error_count` 真实数据源（目前仍硬
  编码 0 — `data_gap_exceeded_tolerance` + `ws_disconnected` 可看用户可见
  失败模式）。
- 写第二个 dashboard 专门展示 paper bundle 长期表现。
- 增加 Prometheus alert rules（heartbeat freshness > 120s, ws_disconnected
  持续 60s 等）→ 走 Alertmanager 或 Grafana alerting。Phase 3 entry 暂时只用
  人工看面板。

## 8. 不变 / 不破

- ADR-001 铁律 1–5 全部保留：Agent 不下单、纯人工授权、回测/paper/testnet
  三层评判仍以 bundle 为准。
- ADR-008 §6.6 testnet canary 路径**完全不变**：
  - bundle 数据 (`heartbeat.jsonl`, `alerts.log`, `run_manifest.json`, 5 个
    parquet sidecar) 一字未改。
  - 信号/订单/sidecar 写入路径未改。
  - 凭证审计 (`credentials_key_prefix` 8 字符) 未改。
  - `--write-live-sidecars` / `--enable-strategy-execution` 入口未改。
  - exit code 0/1/2/3/4/5 语义未改。
- `freqai_linear_v1 / linear-mom-train20240105` 仍在 `hold @ testnet_canary`
  下的 `SourcePolicy(dry_run=False, position_pct_multiplier=0.1,
  min_confidence_override=None)`。
