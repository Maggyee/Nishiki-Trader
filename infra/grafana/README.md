# grafana

**Phase**: 3 entry (提前启用, 见 docs/decisions/001-tech-stack.md §6 补丁).

观测栈的展示层. 默认登录 `admin / admin` (开发用, 后续可以通过 .env 覆盖
`GRAFANA_ADMIN_USER` / `GRAFANA_ADMIN_PASSWORD`).

## 端口

- `127.0.0.1:3000` (仅本机, 见 infra/docker-compose.yml).

## 子目录

- `provisioning/datasources/` — Prometheus + Loki 数据源自动注册.
- `provisioning/dashboards/` — dashboards.yml 把 dashboards/ 下所有 JSON
  自动加到 `trader` folder.
- `dashboards/` — 看板 JSON 源文件 (Task 5 写入 canary-current.json +
  watchdog-current.json).

`dashboards/signals-overview.json` 是只读 Postgres `signal_events` 观察面板，
支持 `source` 和 `model_version` 模板变量。前端 dashboard snapshot 的
source/model evidence link 会把这两个变量带入 Grafana URL，用于只读
drill-down；它不写 `SignalEvent`，也不触发 runner。
