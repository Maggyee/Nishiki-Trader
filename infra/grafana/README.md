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
