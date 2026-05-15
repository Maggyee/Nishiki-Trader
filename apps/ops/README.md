# ops

运维脚本。

**当前 Phase**：2（catalog fixture / backtest operations）。

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

## 计划脚本

| 脚本 | 用途 | 最早 Phase |
|---|---|:-:|
| `emergency_flatten.py` | 应急一键平仓 + 停策略 | 3 |
| `daily_health.py` | 每日健康检查（数据延迟 / 服务存活 / 仓位漂移） | 1 |
| `backfill_bars.py` | 从 Binance public klines 导入 K 线到 ParquetDataCatalog | 1 |
| `signal_replay.py` | 重放 SQLite 中的历史 signals 跑回测 | 1 |
| `migrate_sqlite_to_pg.py` | Phase 2 数据迁移 | 2 |
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
