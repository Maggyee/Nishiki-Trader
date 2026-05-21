# promtail

**Phase**: 3 entry (提前启用).

Loki 的本机日志采集 agent. 单一目的: 把
`data/testnet/<run_id>/logs/*.jsonl` /
`data/paper/<run_id>/logs/*.jsonl` /
`infra/watchdog/state.json` 推到 Loki, 给 Grafana Explore + 看板用.

## 文件

- `promtail.yml` — Task 2 的最小占位配置, Task 4 替换为完整 scrape 规则.

## 监听

- HTTP `:9080` (debug + readiness), 容器内绑 `127.0.0.1:9080`.
- 推送到容器内 DNS `loki:3100`.

## 状态

- Task 2 完成: 容器可起.
- Task 4 完成: jsonl 实际进入 Loki.
