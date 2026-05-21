# loki

**Phase**: 3 entry (提前启用).

单机 Loki, 单一目的: 接 Promtail 推过来的 `data/testnet/<run_id>/logs/*.jsonl`
和 watchdog state, 提供 LogQL 查询.

## 文件

- `loki-config.yml` — 单节点 TSDB filesystem 后端配置.

## 数据保留

30 天 (`limits_config.retention_period`, `compactor.retention_enabled=true`).

## 不暴露公网

监听 `127.0.0.1:3100`, 仅本机可访问 (含 Grafana 容器内调用).

## 关联

- Promtail 配置: `infra/promtail/promtail.yml` (Task 4 实现).
- Grafana 数据源 provisioning: `infra/grafana/provisioning/datasources/datasources.yml`.
