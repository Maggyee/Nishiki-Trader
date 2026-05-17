# ADR-004：NautilusTrader 回测结果标准格式

- **状态**：Accepted
- **日期**：2026-05-15
- **作者 / 维护者**：nishiki（个人开发者，唯一负责人）
- **范围**：Phase 2 起 NautilusTrader 回测结果在本仓库内的持久化格式、目录布局、可重放性约束
- **依赖**：
  - ADR-001 §3.4（执行层 = NautilusTrader）、§5（目录结构）、§6 铁律 4（先写得对，再写得快）
  - ADR-002 §5（信号必须可追踪）、§7（同批历史信号重复回放结果一致）
  - ADR-003 §2.3（`data/` 默认 gitignore）、§2.7（Phase 1 → Phase 2 graduation）
- **复审周期**：Phase 2 末复审一次；之后每次回测口径变动随 ADR 修订

---

## 1. 背景

Phase 1 已经把 `SignalEvent v1` → `apps/strategies_nautilus/signal_consumer.py` 的占位链路打通，但消费者只是把信号标记成 `consumed | rejected | expired`，**没有产出可比对的回测结果**。Phase 2 要把消费者升级成跑在 `nautilus_trader.backtest` 上的真实策略，结果必须能：

1. 多次重跑同一份输入，得到字节相同（或仅时间戳差异）的结果文件——ADR-002 §7 的"重复回放结果一致"要求落地到磁盘层。
2. 多次跑不同策略 / 不同参数 / 不同信号源，结果之间能按统一字段对比 PnL、Sharpe、最大回撤、订单数。
3. 任何一次回测都能被复盘到信号级别——给定一个 trade，能反查到产生它的 `signal_id`、`source`、`model_version`。
4. 不依赖 hvplot / pandas notebook / 第三方 UI 也能读——纯命令行 + jq + DuckDB 就能查。
5. 在迁移到 Postgres / Grafana（Phase 3）时不需要回头改格式。

NautilusTrader 自带的 `BacktestResult`（见 `nautilus_trader/nautilus_trader/backtest/results.py`）只是一个 dataclass，承载了运行元数据和聚合统计；订单 / 成交 / 持仓 / 账户余额是按需通过 `Trader.generate_*_report()` 拿到的 DataFrame。本 ADR **不替代** Nautilus 的内部对象，而是**在本仓库的 `data/` 下规定一份持久化外壳**：把 `BacktestResult` 的字段、四张明细报表，以及本项目特有的"信号血缘"统一落到一份目录里。

---

## 2. 决策

### 2.1 目录布局

每一次完整回测都落到一个**自包含目录**：

```text
data/backtests/<run_id>/
├── run_manifest.json
├── orders.parquet
├── fills.parquet
├── positions.parquet
├── account_balances.parquet
├── signal_lineage.parquet
└── logs/
    ├── strategy.log
    └── risk.log
```

约束：

- `<run_id>` 形如 `YYYYMMDD-HHMMSSZ-<8charhex>`，例如 `20260615-021530Z-9a2c4f81`。`run_id` 必须等同于 `run_manifest.json.run_id`，便于纯文件名识别。
- 整个 `data/` 默认 gitignore（ADR-003 §2.3），需要分享的结果用 `tar -czf` 打包，**不入仓**。
- 单次回测目录一旦写完即视为只读，禁止追加 / 改写——重新跑请新建 `<run_id>`。
- `logs/` 在 Phase 2 是可选的；如果没有就省略目录。Phase 3 起强制写入并在 Grafana 中索引。

### 2.2 `run_manifest.json`

唯一的入口文件，UTF-8 编码、`\n` 行尾、字段顺序按下面给出（便于 diff）。

```json
{
  "schema_version": "backtest.v1",
  "run_id": "20260615-021530Z-9a2c4f81",
  "kind": "backtest",
  "trader_id": "TRADER-001",
  "machine_id": "home-frp",
  "git_commit": "1a174c7",
  "git_dirty": false,
  "nautilus_version": "1.220.0",
  "python_version": "3.12.13",
  "started_at": "2026-06-15T02:15:30.000Z",
  "finished_at": "2026-06-15T02:16:42.318Z",
  "elapsed_seconds": 72.318,
  "backtest_start": "2026-01-01T00:00:00.000Z",
  "backtest_end":   "2026-06-01T00:00:00.000Z",
  "venues": ["BINANCE"],
  "instruments": ["BTCUSDT", "ETHUSDT"],
  "strategies": [
    {
      "name": "baseline_signal_strategy",
      "params": {"max_position_pct": 0.05, "min_confidence": 0.55}
    }
  ],
  "risk_rules": [
    {"name": "daily_drawdown_stop", "params": {"max_pct": 0.05}}
  ],
  "signal_source": {
    "store_path": "data/bridge/signals.db",
    "store_sha256": "8c0b...e6f1",
    "filter": {"source": "freqai_v1", "model_version": "2026-05-14"},
    "row_count": 4321,
    "min_ts_event_ns": 1735689600000000000,
    "max_ts_event_ns": 1748736000000000000
  },
  "data_catalog": {
    "path": "data/catalog/",
    "instruments": [
      {"id": "BTCUSDT.BINANCE", "bars": "1m", "rows": 217440}
    ]
  },
  "totals": {
    "iterations": 217440,
    "events": 184902,
    "orders": 1037,
    "positions": 215,
    "fills": 1842
  },
  "stats_pnls": {
    "USDT": {
      "pnl_total": 3142.18,
      "pnl_per_trade_avg": 1.71,
      "win_rate": 0.546,
      "sharpe": 1.82,
      "sortino": 2.41,
      "max_drawdown_pct": -0.082,
      "max_drawdown_abs": -812.55
    }
  },
  "stats_returns": {
    "annualized_return": 0.241,
    "annualized_vol": 0.132,
    "max_drawdown": -0.082
  }
}
```

字段约束：

| 字段 | 必填 | 约束 |
|---|---:|---|
| `schema_version` | 是 | 固定为 `backtest.v1`，未来加字段不破坏（appended）；不兼容改动必须升 `backtest.v2` |
| `run_id` | 是 | 与目录名一致 |
| `kind` | 是 | `backtest`、`paper`、`live`（Phase 2 只能是 `backtest`） |
| `git_commit` / `git_dirty` | 是 | 起跑时 `git rev-parse HEAD` 与 `git diff --quiet` 的结果；**`git_dirty=true` 的回测不允许出现在策略比对里** |
| `started_at` / `finished_at` | 是 | ISO 8601 UTC，毫秒精度，`Z` 结尾 |
| `backtest_start` / `backtest_end` | 是 | 模拟时段（不是墙钟） |
| `signal_source.store_sha256` | 是 | 起跑前 `data/bridge/signals.db` 的 SHA-256；重跑相同字节即视为重放同一份信号 |
| `signal_source.filter` | 是 | 实际喂给策略的过滤条件，对应 `SignalStore.replay(**filter)` |
| `data_catalog.path` | 是 | 行情来源（NautilusTrader `ParquetDataCatalog`） |
| `stats_pnls` | 是 | 按结算货币聚合；至少要有总 PnL、胜率、Sharpe、最大回撤 |

`stats_pnls` 与 `stats_returns` 直接对应 NautilusTrader `BacktestResult.stats_pnls` / `stats_returns`；如果未来 Nautilus 扩了字段，仓本侧透传不改名。

### 2.3 Parquet 明细

四份必填 Parquet，外加一份本项目特有的信号血缘。**所有时间字段统一用 `int64` 纳秒（UTC）**，与 ADR-002 §7 一致。所有金额字段统一用 `decimal128(38, 12)` 或者 `float64`（择一，全项目同一种）；本 ADR 选 **`float64`**——Phase 2 不引入 Arrow Decimal 处理依赖。

| 文件 | 来源 | 关键列 | 索引 |
|---|---|---|---|
| `orders.parquet` | `Trader.generate_order_fills_report()` 的母集 | `order_id, client_order_id, venue, instrument_id, side, quantity, price, type, status, ts_init, ts_last, signal_id` | `order_id` 主键 |
| `fills.parquet` | `Trader.generate_fills_report()` | `fill_id, order_id, venue, instrument_id, side, quantity, price, commission, currency, ts_event, signal_id` | `fill_id` 主键，按 `ts_event` 升序 |
| `positions.parquet` | `Trader.generate_positions_report()` | `position_id, venue, instrument_id, side, quantity, peak_qty, avg_px_open, avg_px_close, realized_pnl, unrealized_pnl, opened_ts, closed_ts, signal_ids` | `position_id` 主键 |
| `account_balances.parquet` | `Trader.generate_account_report(account_id)` 的每个 venue/account 拼接 | `ts_event, venue, account_id, currency, total, free, locked` | (`venue`, `account_id`, `currency`, `ts_event`) |
| `signal_lineage.parquet` | 本项目生成（消费者层注入） | `signal_id, source, model_version, ts_event, decision, reason, order_ids, fill_ids, position_id` | `signal_id` 主键 |

约束：

- `signal_id` 必须在 `orders` / `fills` / `positions` 中**冗余写入一份**（即使 Nautilus 不原生支持，由 `apps/strategies_nautilus/baseline_strategy.py` 在生成订单时通过 `client_order_id` 或 tag 透传，再由结果落盘代码反查）。这是 ADR-002 §5 的硬要求——"如果触发交易，保存 signal_id 到订单/交易日志"。
- `signal_lineage.parquet` 是单次回测的**所有** `SignalEvent` 的去向，包括 `rejected / expired / accept_no_fill`；与 `apps/strategies_nautilus/signal_consumer.py` 当前产出的 `ConsumerOutcome` 等价，只是格式从 SQLite 行变 Parquet 行。
- Parquet 写入用 `pyarrow`，压缩 `zstd`，`row_group_size=64_000`。读取必须可由 `duckdb` 直接 `SELECT * FROM 'fills.parquet'` 跑通。

### 2.4 可重放性

定义一次回测**可重放**为：相同 `git_commit` + 相同 `signal_source.store_sha256` + 相同 `data_catalog.path` 内容 + 相同 `strategies[].params` + 相同 `risk_rules[].params` + 相同 NautilusTrader 版本，**两次回测的 `stats_pnls / stats_returns / fills.parquet` 必须 bit-for-bit 等价**（除了 `run_id`、`started_at`、`finished_at`、`elapsed_seconds`）。

实现要求：

1. 随机源全部使用显式 seed，seed 写入 `run_manifest.json.strategies[].params.seed`。
2. 不依赖墙钟做决策；只用 `clock.timestamp_ns()`（NautilusTrader 的回测时钟）。
3. 浮点求和顺序固定（按 `ts_event` 升序）。
4. CI（Phase 2 末）必须有一份"重放测试"：对同一份输入跑两次，diff Parquet 内容 + `stats_pnls` 必须为空集。

### 2.5 与现有持久化的接口

| 来源 | 角色 |
|---|---|
| `data/bridge/signals.db` | 信号输入；本 ADR 不变更 schema，但要求每次回测前 sha256 整个文件 |
| `data/catalog/` | NautilusTrader `ParquetDataCatalog` 维护的 K 线/逐笔；本 ADR 不规定其内部布局（由 Nautilus 决定） |
| `data/backtests/<run_id>/` | **本 ADR 唯一新增持久化目录** |

`apps/strategies_nautilus/runners/backtest_runner.py` 是本格式的**唯一写入者**：

```text
backtest_runner.py
  ├─ load SignalStore  (apps/bridge/store.SignalStore)
  ├─ load ParquetDataCatalog
  ├─ build BacktestNode + Strategy + RiskEngine
  ├─ run()  → list[BacktestResult]
  └─ write data/backtests/<run_id>/  (this ADR)
```

读取侧暂不写代码——Phase 2 用 `duckdb` / `polars` 在 notebook 临时查询即可。任何固化下来的查询 / 报表代码进 Phase 3 ADR-008（命名待定）。

### 2.6 Schema 演进

- `backtest.v1` 内允许**追加**新字段（兼容），不允许重命名 / 删除现有字段；增加字段需要在本 ADR 追加表行。
- 不兼容变更升 `backtest.v2`，并在本 ADR 写迁移指引。
- Parquet 列只能追加；删除 / 重命名等同升大版本。

---

## 3. 明确不做

- 不在 Phase 2 引入 hvplot / plotly / dash / streamlit——结果**只是文件**，画图属于 Phase 3 前端。
- 不在 Phase 2 把回测结果写进 SQLite / Postgres——文件就够，迁库等 Phase 3 ADR-008。
- 不为多回测对比写"对比器"代码（脚本化的 leaderboard、参数扫描汇总）；Phase 2 用 `duckdb` 临时查。
- 不为单次回测拆分多个 manifest（例如多策略各一份）——一次 `BacktestNode.run()` 即使产出多个 `BacktestResult`，也统一聚合在一个 `run_manifest.json.strategies[]`。
- 不在 manifest 里嵌入完整日志——`logs/strategy.log` / `logs/risk.log` 单独留文件，避免 manifest 文件过大。
- 不依赖 NautilusTrader 内部未公开字段；只读 `Trader.generate_*_report()` 公共方法。

---

## 4. 验证标准

本 ADR 落地后必须满足（在 Phase 2 末逐项打勾）：

1. `apps/strategies_nautilus/runners/backtest_runner.py` 写出的目录与 §2.1 完全一致。
2. `run_manifest.json` 通过一份 schema 校验（`apps/bridge/` 之外的位置，初步用 Pydantic 写在 `apps/strategies_nautilus/result_schema.py`）。
3. `tests/strategies_nautilus/test_backtest_result_format.py` 包含：
   - 写一份合法 manifest，再用 schema 反向加载，字段全保留；
   - 重放性测试：同样输入跑两次，diff fills/positions/manifest 中非时间字段为空；
   - `signal_id` 在 `orders / fills / positions` 中可追溯回 `signal_lineage` 与 `data/bridge/signals.db`；
   - `git_dirty=true` 的 manifest 在比对工具里被强制过滤（占位测试，等比对工具进 Phase 3）。
4. `data/backtests/` 已被 `.gitignore` 覆盖（落在 ADR-003 §2.3 `data/*` 通配下，无需新增）。

---

## 5. 后续 ADR

- **ADR-005**：研究层信号源分类与命名（已落地）。
- **ADR-006**：信号源灰度策略与 dry-run（已落地）。
- **ADR-007**：paper trading runtime 与 SourcePolicy 升档（已落地）。
- **Future**：Redis Stream 桥接通道（确认 SQLite 桥不够用之后）。
- **Future**：回测结果对比 / 索引 / Web 展示（与 Phase 3 前端启动同步定）。

---

**Decided. Phase 2 起所有 NautilusTrader 回测结果按本 ADR 的目录、manifest、Parquet 明细格式落盘。任何偏离都需先提 ADR 修订或升 `backtest.v2`。**
