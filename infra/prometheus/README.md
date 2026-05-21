# prometheus

**Phase**: 3 entry (提前启用, 见 docs/decisions/001-tech-stack.md §6 补丁).

Prometheus 配置. 单一目的: 抓 `node_exporter` 的 textfile collector,
让 `apps/strategies_nautilus/runners/testnet_runner.py` 写的
`data/testnet/<run_id>/metrics/*.prom` 进入时序库.

## 文件

- `prometheus.yml` — scrape 配置, 抓 self + node_exporter.

## 数据保留

`--storage.tsdb.retention.time=30d` (见 `infra/docker-compose.yml`).

## 不暴露公网

监听 `127.0.0.1:9090`, 仅本机可访问.

## 关联

- textfile collector 目录在 `infra/docker-compose.yml` 的 `node_exporter`
  服务里挂载: 容器内 `/textfile/testnet/<run_id>/metrics/*.prom`.
- runner 侧的 .prom 文件格式见 `apps/strategies_nautilus/runners/`
  里的 textfile 导出逻辑 (Task 3 实现).
