# ops

运维与审查脚本。全部是被动工具：不下单，不写 `SignalEvent`（demo 种子除外），
不改 `SourcePolicy`，不读交易凭证。

- **当前 Phase**：5 entry（只读监控），兼顾 Phase 1/2 数据与回测审查。
- **边界**：研究协议、portfolio/testnet 联合采集、egress 工具已于 2026-10-17
  移到 tag `archive/pre-slim-2026-10-17`，见 `docs/history.md`。
- **下一步入口**：新增运维脚本前先确认 `docs/project-status.md` Next Steps 需要它。

| 模块 | 用途 |
|---|---|
| `backfill_bars.py` | 把 Binance 公开 kline（日/月归档）幂等导入 Nautilus `ParquetDataCatalog`，可写入冒烟用 demo 信号 |
| `catalog_audit.py` | 检查 catalog 的行数、边界、重复、缺口、指纹和跨资产对齐 |
| `alpha_review.py` | 对 backtest/paper bundle 重算 gross / base（10+2 bps）/ stress（10+5 bps）成本情景，输出 `alpha.review.v1` |
| `live_readiness.py` | Phase 6 只读就绪闸门。ADR-013 仍是 Draft，所以默认结果是阻塞 |
| `dashboard_snapshot.py` | 汇总状态、AgentAdvice、bundle、观测 textfile、Phase 6 报告，生成前端只读快照 |
| `sync_signals_to_postgres.py` | 把 SQLite 信号库一次性、幂等地镜像到 Postgres（供 Grafana 使用） |

## 常用命令

```bash
# 1m catalog fixture + demo signals（冒烟用，不代表 alpha）
uv run python -m apps.ops.backfill_bars --download --symbol BTCUSDT --interval 1m \
  --date 2024-01-01 --catalog-path data/catalog \
  --seed-demo-signals --signal-store-path data/bridge/signals.db

# 区间补数（月度归档拒绝不完整自然月）
uv run python -m apps.ops.backfill_bars --download --archive-period monthly \
  --start-date 2024-01-01 --end-date 2025-12-31 --symbol ETHUSDT --interval 1m \
  --catalog-path data/catalog

uv run python -m apps.ops.catalog_audit --catalog-path data/catalog \
  --bar-type BTCUSDT.BINANCE-1-MINUTE-LAST-EXTERNAL \
  --start-date 2024-01-01 --end-date 2025-12-31

uv run python -m apps.ops.alpha_review \
  --candidate walkforward=data/backtests/<run-id> \
  --blind-start 2024-08-01 --blind-end 2024-12-31 \
  --catalog-path data/catalog --bar-type BTCUSDT.BINANCE-1-MINUTE-LAST-EXTERNAL --markdown

# 前端快照；可附加 --paper-bundle / --testnet-bundle / --phase6-*-report
uv run python -m apps.ops.dashboard_snapshot > data/frontend/dashboard-snapshot.json

uv run python -m apps.ops.live_readiness --source <source> --model-version <version> \
  --starting-capital-usdt 100 --markdown

uv run python -m apps.ops.sync_signals_to_postgres
```

Binance Spot 归档从 2025-01-01 起把时间戳由毫秒改为微秒。importer 按数值量级
识别单位，混合单位一律拒绝。
