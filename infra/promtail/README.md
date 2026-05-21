# promtail

**Phase**: 3 entry (提前启用).

Loki 的本机日志采集 agent. 单一目的: 把
`data/testnet/<run_id>/logs/*.jsonl` /
`data/paper/<run_id>/logs/*.jsonl` /
`infra/watchdog/history.jsonl` 推到 Loki, 给 Grafana Explore + 看板用.

## 文件

- `promtail.yml` — 完整 scrape 规则: testnet runtime / heartbeat /
  alerts, paper runtime, watchdog append-only history.

## 监听

- HTTP `:9080` (debug + readiness), 容器内绑 `127.0.0.1:9080`.
- 推送到容器内 DNS `loki:3100`.

## 状态

- Phase 3 entry 可用: jsonl 实际进入 Loki.
- `state.json` 是 overwrite 状态快照, 不适合 tail; Promtail 使用
  `history.jsonl`.
