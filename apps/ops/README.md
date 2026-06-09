# ops

运维脚本。

**当前 Phase**：2（catalog fixture / backtest operations）+ Phase 4/5 read-only
dashboard snapshot support。

## 当前入口

准备一份本地 BTCUSDT Binance 1m catalog fixture，并写入只用于冒烟测试的
`SignalEvent v1` demo signals：

```bash
uv run python -m apps.ops.backfill_bars \
  --download \
  --symbol BTCUSDT \
  --interval 1m \
  --date 2024-01-01 \
  --catalog-path data/catalog \
  --seed-demo-signals \
  --signal-store-path data/bridge/signals.db
```

等价地，也可以先手动下载 Binance public data ZIP，再用 `--raw-path` 导入：

```bash
uv run python -m apps.ops.backfill_bars \
  --raw-path data/raw/binance/spot/daily/klines/BTCUSDT-1m-2024-01-01.zip \
  --catalog-path data/catalog \
  --seed-demo-signals
```

当前 fixture importer 只支持 `BTCUSDT.BINANCE` spot。它会生成以下 Nautilus
命名，供 backtest runner 使用：

- instrument id: `BTCUSDT.BINANCE`
- bar type: `BTCUSDT.BINANCE-1-MINUTE-LAST-EXTERNAL`

`--seed-demo-signals` 写入的 `manual_research/binance-fixture-v1` 信号只用于
确认 catalog-backed runner 可以端到端产出 ADR-004 bundle，不代表可交易 alpha。

生成 Phase 4 只读 dashboard snapshot（JSON 默认输出到 stdout）：

```bash
uv run python -m apps.ops.dashboard_snapshot \
  --project-status-path docs/project-status.md \
  --agent-advice-db data/agents/advice.db
```

默认 snapshot 还会带只读 `reference_links`：

- 本地 Grafana：`http://127.0.0.1:3000/d/signals-overview/signals-overview`
  和 `http://127.0.0.1:3000/d/canary-current/canary-current`
- 对应源文件：`infra/grafana/dashboards/*.json`
- 当前状态、ADR、证据 ledger、runbook 的本地源路径

可用空字符串关闭 Grafana URL，只保留本地源路径；也可以传入仓库浏览基准
URL，让文档路径变成浏览器可打开的只读链接：

```bash
uv run python -m apps.ops.dashboard_snapshot \
  --grafana-base-url "" \
  --repo-browser-base-url https://github.com/Maggyee/Nishiki-Trader/blob/main
```

也可以追加已完成的 passive bundle reports 作为压缩摘要输入：

```bash
uv run python -m apps.ops.dashboard_snapshot \
  --testnet-bundle data/testnet/<run_id> \
  --paper-bundle data/paper/<run_id> \
  --markdown
```

`dashboard_snapshot` 只读取 `docs/`、AgentAdvice SQLite、既有 paper/testnet bundle
report reader、以及静态链接配置；不写 `SignalEvent`、不改 `SourcePolicy`、不读取
交易所凭证。

## 计划脚本

| 脚本 | 用途 | 最早 Phase |
|---|---|:-:|
| `emergency_flatten.py` | 应急一键平仓 + 停策略 | 3 |
| `daily_health.py` | 每日健康检查（数据延迟 / 服务存活 / 仓位漂移） | 1 |
| `backfill_bars.py` | 从 Binance public klines 导入 K 线到 ParquetDataCatalog | 1 |
| `signal_replay.py` | 重放 SQLite 中的历史 signals 跑回测 | 1 |
| `migrate_sqlite_to_pg.py` | Phase 2 数据迁移 | 2 |
| `dashboard_snapshot.py` | Phase 4 只读 AgentAdvice / report snapshot | 4 |
| `testnet_handoff.py` | testnet ↔ live 切换前的检查清单 | 6 |

## 跑法

```bash
uv run python -m apps.ops.daily_health
uv run python -m apps.ops.emergency_flatten --confirm I_REALLY_MEAN_IT
```

## 边界

- 应急脚本必须有**二次确认**参数，避免误触发
- 任何写真实账户的脚本（Phase 6+）走 `EMERGENCY_*` 前缀，醒目
- Phase 2 ops 脚本只能写本地 `data/`，不能接真实账户或下单 API
