# prometheus

**Phase**: 3 entry (提前启用, 见 docs/decisions/001-tech-stack.md §6 补丁).

Prometheus 配置. 单一目的: 抓 `node_exporter` 的 textfile collector,
让 `apps/strategies_nautilus/runners/testnet_runner.py` 写的
`data/testnet/<run_id>/metrics/*.prom` 进入时序库.

## 文件

- `prometheus.yml` — scrape 配置, 抓 self + node_exporter.
- `alert_rules.yml` — Phase 3 canary 基础告警: heartbeat stale, WS
  disconnected, exchange/runtime error burst, stale heartbeat with open
  position.

## 数据保留

`--storage.tsdb.retention.time=30d` (见 `infra/docker-compose.yml`).

## 不暴露公网

监听 `127.0.0.1:9090`, 仅本机可访问.

## 关联

- textfile collector 目录在 `infra/docker-compose.yml` 的 `node_exporter`
  服务里挂载: 容器内 `/textfile`.
- runner 侧默认写 `data/observability/textfile/testnet-<run_id>.prom`;
  文件格式见 `apps/strategies_nautilus/runners/textfile_metrics.py`.
