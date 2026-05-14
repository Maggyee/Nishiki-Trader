# ops

运维脚本。

**当前 Phase**：0（骨架）。Phase 1 开始填内容。

## 计划脚本

| 脚本 | 用途 | 最早 Phase |
|---|---|:-:|
| `emergency_flatten.py` | 应急一键平仓 + 停策略 | 3 |
| `daily_health.py` | 每日健康检查（数据延迟 / 服务存活 / 仓位漂移） | 1 |
| `backfill_bars.py` | 从 binance 补历史 K 线到 ParquetDataCatalog | 1 |
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
