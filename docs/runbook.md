# Runbook

> 救火手册。Phase 0 内容很少；每个 Phase 完成时回来补对应章节。

## 紧急停机 / 平仓

**触发条件**（手动判断或自动）：

- 单日亏损达 5%（ADR-001 §2 铁律 5；nautilus RiskEngine 应自动停）
- 连续亏损 3 笔以上
- 交易所返回异常 / API 限流 / 风控失效
- agent 异常输出
- 网络 / 进程 / 数据库异常

**步骤**（Phase 3+）：

1. 跑 `uv run python -m apps.ops.emergency_flatten --confirm I_REALLY_MEAN_IT`
2. 登录 Binance 网页 / app 二次确认仓位为 0
3. 停 nautilus：`docker compose -f infra/docker-compose.yml stop nautilus` 或 `pkill -f nautilus`
4. 在 `docs/retros/YYYY-MM.md` 记录事故 + 触发原因 + 复盘

## 服务重启

### nautilus（Phase 1+）

```bash
# 检查最后状态
ls -la data/nautilus_cache/

# 启动 backtest / dry-run
cd apps/strategies_nautilus && uv run python runners/backtest_runner.py
```

### paper session（Phase 2+）

Paper session 只允许模拟账户，不读取真实交易所 API key，不提交真实订单。输出目录：
`data/paper/<run_id>/`。

启动本地模拟 paper session：

```bash
uv run python -m apps.strategies_nautilus.runners.paper_runner \
  --catalog-path data/catalog \
  --signal-store-path data/bridge/signals.db \
  --instrument-id BTCUSDT.BINANCE \
  --bar-type 'BTCUSDT.BINANCE-1-MINUTE-LAST-EXTERNAL' \
  --signal-source freqai_linear_v1 \
  --signal-model-version linear-mom-train20240105 \
  --allowed-source freqai_linear_v1 \
  --allowed-model-version linear-mom-train20240105 \
  --trade-size 0.001 \
  --starting-balance 100000 \
  --policy-position-pct-multiplier 0.2 \
  --policy-dry-run
```

检查：

```bash
jq '.kind, .runtime, .totals, .strategies[0].params.policies' \
  data/paper/<run_id>/run_manifest.json
```

降档规则：

- `signal_lineage.parquet` 出现批量 `expired`、`unauthorized`、`signal_lag`：保持或切回 `dry_run=True`。
- `risk.log` 出现 `kill_switch`：停用该 `(source, model_version)`，人工复盘后才能恢复。
- 任何 session 的 `git_dirty=true`：不得作为升档依据。
- Paper 通过前禁止添加真实 exchange credentials；testnet 通过前禁止 live。

### freqtrade（Phase 2+）

```bash
freqtrade trade \
  --config apps/strategies_freqtrade/user_data/config.json \
  --userdir apps/strategies_freqtrade/user_data
```

### postgres / redis（Phase 2+）

```bash
docker compose -f infra/docker-compose.yml up -d postgres redis
```

## 数据问题

| 症状 | 处理 |
|---|---|
| 历史 K 线缺失 | 跑 `uv run python -m apps.ops.backfill_bars` |
| SQLite 损坏 | 从最近 `data/signals.sqlite.bak` 恢复 |
| Parquet 损坏 | 重新从 binance 拉历史 |
| signals 表重复 | 检查 `signal_id` 去重逻辑 |
| 价格漂移 | 检查 nautilus 与 freqtrade 用的是不是同一份数据源 |

## 日志位置

| 服务 | 路径 |
|---|---|
| nautilus | `logs/nautilus_*.log`（待 Phase 1 落地） |
| freqtrade | `apps/strategies_freqtrade/user_data/logs/` |
| agents | `logs/agent_*.log`（Phase 4） |
| ops 脚本 | `logs/ops_*.log` |

## 升级 / 降级路径

- ADR-001 / ADR-002 标记为 Accepted 的内容，**改动前先开新 ADR**
- upstream（`freqtrade/`、`nautilus_trader/`）升级走单独流程：
  1. 在新分支跑 `apps/` 测试全量
  2. backtest 重跑过去 30 天，PnL 偏差 < 5% 才允许合
  3. 不直接覆盖，保留旧版本可回滚 1 周

## 待补章节（按 Phase）

- Phase 1：daily_health.py 自检项清单、signals 表损坏恢复流程
- Phase 2：PG 故障 / Redis 故障的 SQLite 降级流程
- Phase 3：testnet 与真实账户切换流程
- Phase 4：agent 失控的快速吊销流程
- Phase 6：真实账户实盘第一日的逐步加仓和监控清单
