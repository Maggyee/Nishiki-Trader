# ADR-008：Phase 3 风控、testnet runtime 与运行手册

- **状态**：Draft（接受为规范；运行时实现按 §6 路线分阶段完成，每阶段完成前 `phase_3_not_ready` gate 不放开）
- **日期**：2026-05-17
- **作者 / 维护者**：nishiki（个人开发者，唯一负责人）
- **范围**：从 `paper_simulated`（本地模拟撮合）跨到 `testnet_canary`（Binance testnet 真实下单、模拟资金）所需的运行拓扑、凭证管理、紧急停机、重启恢复、报警和升档前置条件
- **依赖**：
  - ADR-001（技术栈、五条铁律、资金阶梯、5% 单日亏损停机）
  - ADR-002（`SignalEvent v1` 是唯一允许的研究信号桥）
  - ADR-004（`run_manifest.json` bundle 格式与 `kind`）
  - ADR-006（`SourcePolicy`、multiplier、dry-run）
  - ADR-007（paper 运行时与 §2.5 升档表）
- **复审周期**：每完成 §6 中一个 Phase 3 子阶段后复审；首次 testnet_canary promote retro 前必须复审一次

---

## 1. 背景

Phase 2 在 2026-05-17 已经把第一个 source 推到 `paper_simulated`：
`freqai_linear_v1 / linear-mom-train20240105` 在 60 天 BTCUSDT 1m 历史数据
上跑出 `dry_run=False, position_pct_multiplier=0.2` 的本地模拟撮合
bundle，545 fills、273 positions、kill-switch 未触发、ADR-002 §4.1 traceability
全过。下一档 `testnet_canary` 现在被 `apps.strategies_nautilus.runners.promotion_review`
的 `phase_3_not_ready` gate 硬阻断（`STAGE_ORDER.index(target) > PHASE_2_STAGE_LIMIT`）。

阻断的原因是 ADR-007 §2.5 testnet_canary 行的前置条件——"paper simulated ≥ 7 天稳定；
人工复盘通过；Phase 3 testnet runbook 就绪"——的最后一项缺失：项目还没有定义
真正连交易所、读真凭证、面对网络/API 故障时如何安全运行的规则。`paper_simulated`
仍然是本地撮合，不暴露任何外部失败模式；`testnet_canary` 第一次让真实交易所
进入路径，必须先把整套故障假设、凭证边界、紧急停机、重启恢复和报警写下来。

本 ADR 是这套规则的规范层。它**不**实现任何运行时代码，**不**新增任何凭证、
**不**移除 `phase_3_not_ready` gate。它定义"什么必须存在、什么必须被测试、
什么必须在 commit 前出现"，让后续每个 Phase 3 子阶段都能拿这份 spec 作为
对照清单。

---

## 2. 范围与不做

### 2.1 范围

- `kind="testnet"` 的运行语义、bundle 落盘扩展、manifest 字段。
- 真实 Binance testnet API key/secret 的本地存储、加载、运行时校验。
- 紧急停机（emergency flatten）的 CLI 工作流、触发条件、审计落盘。
- 进程崩溃 / 手动重启后状态恢复的契约：cursor、订单、仓位三层都要可对账。
- 异常报警的本地最小集（`logs/alerts.log`）和触发口径。
- ADR-007 §2.5 升档表中 `paper_simulated → testnet_canary` 行的具体校验清单。

### 2.2 不做

- **不**启 live 实盘。`live_canary` / `live_normal` 行的资金阶梯、保险金、
  仓位上限由 ADR-001 §6 已经规定，本 ADR 不重复，但 §5.6 会列出从
  `testnet_canary` 升 `live_canary` 的最低附加证据。
- **不**接 Telegram、邮件、飞书或其他外部通知通道。Phase 3 报警先停在
  本地日志 + 进程退出码；外部通道留给 Phase 4 监控 ADR。
- **不**把 LLM agent 引入实盘订单路径——这是 ADR-001 五条铁律之一，本 ADR
  不放松。LLM 的 paper-shadow 升档由 ADR-009（之前 ADR-007 §4 中的 ADR-008）
  定义。
- **不**引入 Redis Stream 或 Postgres——SQLite `SignalStore` 仍是 Phase 3
  默认 transport，瓶颈出现后再走 ADR-010。
- **不**改 `SignalEvent v1` schema。ADR-002 §3 字段集合在本 ADR 里完全冻结。
- **不**为 testnet 之外的交易所写 adapter。Binance testnet 是 Phase 3 的
  唯一目标交易所；多交易所支持留给后续 ADR。

---

## 3. `kind="testnet"` 运行语义

### 3.1 与 backtest / paper / live 的边界

```text
backtest:    历史 catalog        -> Nautilus backtest engine        | 资金 0
paper:       catalog polling     -> 本地模拟撮合 (kind="paper")     | 资金 0
testnet:     交易所 testnet WS   -> Binance testnet adapter         | 资金 0（testnet 假币）
live:        交易所现货 WS       -> Binance live adapter            | ADR-001 §6 资金阶梯
```

- `paper` 永远不读真实凭证、不连真实交易所。Phase 2 的 `catalog_polling /
  simulated` 仍是 paper 主用法；Phase 3 增加 `wall_clock / simulated` 子模式
  作为 testnet 前的最后一关。
- `testnet` 用真实 Binance testnet 凭证，订单、撤单、市价、限价、ws/rest
  连接全部走真实路径，但资金账户是 testnet（充水龙头领来的假 USDT/BTC）。
- `live` 必须满足 ADR-001 §6 资金阶梯 + 本 ADR §5.6 testnet 满 14 天稳定，
  本 ADR 不实现。

### 3.2 testnet bundle 格式

复用 ADR-004 manifest，`schema_version="backtest.v1"`，`kind="testnet"`，
落盘在 `data/testnet/<run_id>/`，sidecar 与 paper 完全一致：
`run_manifest.json`、`orders.parquet`、`fills.parquet`、`positions.parquet`、
`account_balances.parquet`、`signal_lineage.parquet`、`logs/`。

`runtime` 字段在 paper 的基础上追加：

```json
{
  "runtime": {
    "mode": "testnet",
    "data_mode": "exchange_ws",
    "order_mode": "exchange_testnet",
    "exchange": "binance",
    "exchange_endpoint": "testnet.binance.vision",
    "credentials_source": "env:BINANCE_TESTNET_*",
    "credentials_key_prefix": "abcd1234",
    "heartbeat_interval_seconds": 30,
    "ws_reconnect_count": 0,
    "exchange_error_count": 0,
    "exchange_rate_limit_hits": 0,
    "operator": "nishiki"
  }
}
```

约束：

- `runtime.mode="testnet"` 必须与 `kind="testnet"` 同时出现，否则 runner 启动失败。
- `runtime.credentials_source` 永远是字段名而不是值，`credentials_key_prefix`
  只记 API key 的前 4–8 位用于审计核对，**严禁**把完整 key 或 secret
  写入 manifest、sidecar、parquet 或日志。
- `account_balances.parquet` 用真实 testnet 账户余额，而不是模拟余额。
- 仓位、订单 ID 是交易所返回的真实 ID，不是本地生成。
- bundle 目录与 `data/paper/` 同级但分开，方便 gitignore 一并屏蔽。

### 3.3 wall-clock paper：testnet 的最后一关

ADR-007 §2.1 已经允许 Phase 2 把 `kind="paper"` 用作 `catalog_polling /
simulated`。Phase 3 引入 `kind="paper"` 的第二个子模式 `wall_clock /
simulated`：按墙钟从 Binance public WS 消费 1m bar，本地模拟撮合，
**不读凭证、不下真实订单**。这是用来验证：

- 长驻进程能稳定消费几小时到几天的实时 WS。
- 重启 / WS 断线 / 数据延迟 / 重复 bar 等问题在不动凭证的前提下被发现。
- ADR-007 §2.4 的 cursor / heartbeat / restart_sequence 字段在墙钟下行为
  正确。

`wall_clock / simulated` 必须先稳定连续运行 ≥ 24 小时（无人工干预、
无重启异常）才允许进入 testnet。这一关是本 ADR 的"零凭证"入口。

---

## 4. 凭证管理

### 4.1 存储位置

- 真实 testnet API key / secret **绝对不**进仓库。
- 默认从环境变量加载：`BINANCE_TESTNET_API_KEY`、`BINANCE_TESTNET_API_SECRET`。
- 本地 dev 推荐 `~/.config/trader/binance_testnet.env`，权限 `chmod 600`，
  通过 shell 启动脚本 `set -a; source ...; set +a` 注入。
- 仓库里只允许 `infra/.env.example`，列出**字段名**，值留空或写
  `<set-locally>`。
- `.gitignore` 必须显式排除 `*.env`、`.envrc`、`infra/secrets/`、
  `data/testnet/<*>/logs/`（防止日志意外含凭证）。

### 4.2 启动校验

testnet runner 启动时按以下顺序校验，任何一步失败立即 `sys.exit(2)`，
不写 bundle、不连交易所：

1. `--mode testnet` 与 `--kind testnet` 必须同时显式给出（防误用）。
2. `BINANCE_TESTNET_API_KEY` 与 `BINANCE_TESTNET_API_SECRET` 必须存在
   且非空。
3. key 与 secret 长度必须 ≥ 32 字符（基本格式校验，不是真实性校验）。
4. 必须显式 `--allow-real-credentials`。这是双签：操作员明确知道自己
   要进 testnet。
5. `git_dirty=true` 时拒绝启动 testnet——任何 testnet bundle 必须可
   被 `git checkout <commit>` 完整重放。
6. 必须显式 `--source` + `--model-version`，且 `(source, model_version)`
   在 `docs/retros/` 中存在最近一次 `decision_allowed=true` 的
   `paper_simulated` hold 或 `promote testnet_canary` retro。
7. `SourcePolicy.position_pct_multiplier` 必须 ≤ 0.2（testnet_canary 上限）。

### 4.3 运行时审计

- 启动后**立刻**在 `logs/runtime.log` 写一条 `credentials_loaded`
  记录：包含 `credentials_source` 字段名、`credentials_key_prefix`（前 4–8 位）、
  时间戳。**不**写 secret、不写 key 完整值。
- 任何向交易所的 HTTP 请求失败、429、5xx、签名错误、timestamp 漂移
  都计入 `runtime.exchange_error_count`，且单独写入
  `logs/exchange_errors.jsonl`。
- 每 1 小时输出一次心跳到 `logs/heartbeat.jsonl`：
  `{ts, ws_connected, last_bar_ns, account_total_usdt, open_orders, open_positions}`。
- 心跳间隔超过 `heartbeat_interval_seconds * 3` 视为失联，进入 §6 的报警路径。

### 4.4 凭证泄露应对

- 怀疑泄露 → 操作员去 Binance testnet 控制台立即吊销 key。
- 同时本地 `unset BINANCE_TESTNET_API_KEY BINANCE_TESTNET_API_SECRET`，
  关闭 runner（`pkill -f testnet_runner` 或操作员自己触发 emergency flatten）。
- 复审：在 `docs/retros/` 写一份 `decision=disable` retro 把该 source 降回
  `paper_shadow`，再用新 key 重新启动 testnet runner。

---

## 5. Emergency flatten、kill-switch、重启与报警

### 5.1 Emergency flatten

CLI（待 §6 实现）：`apps.strategies_nautilus.runners.emergency_flatten`。

输入：

- 目标 `kind`（`paper` / `testnet` / `live`）。
- 目标 `run_id`（即将停的进程的 bundle 目录）。
- 操作员名 + 文字理由。
- 可选 `--cancel-only`（只撤单不平仓，用于 testnet 维护窗口）。

行为顺序（不可换）：

1. 向运行中的 runner 进程发 `SIGTERM`；runner 必须捕获并停止接受新 signal。
2. 向交易所 cancel 全部该 `(account, instrument)` 上的 open orders。
3. 等待 cancel 确认。
4. 对每个 open position 提交 reduce-only market 订单到 `quantity=position.quantity`。
5. 等待 fill 确认或超时（默认 60 秒）。
6. 把停机过程落盘：`data/<kind>/<run_id>/emergency_flatten.json`，
   字段：`triggered_at`、`triggered_by`、`reason`、`cancelled_orders`、
   `closed_positions`、`residual_orders`、`residual_positions`、`final_account`、
   `success`（全部撤单 + 全部平仓为 true）。
7. SIGKILL runner 进程；写最终 `runtime.shutdown_reason="emergency_flatten"`
   到 manifest。

### 5.2 触发口径

emergency flatten 必须在以下任一条件下被自动或人工触发：

| 触发 | 类型 | 谁触发 |
|---|---|---|
| 当日累计 PnL < `-0.05 * starting_balance` | 自动（kill-switch） | runner |
| `runtime.exchange_error_count` 超过阈值（默认 50/小时） | 自动 | runner |
| `runtime.ws_reconnect_count` 超过阈值（默认 10/小时） | 自动 | runner |
| 心跳失联超过 `heartbeat_interval_seconds * 3` | 自动（外部 watchdog） | 待 §6 决定 watchdog 实现位置 |
| 操作员观察到 PnL 异常、bug、外部市场异常 | 人工 | 操作员 CLI |
| 凭证泄露 / 账户异常 | 人工 | 操作员 CLI |

`kill-switch` 不取代 emergency flatten——5% 单日亏损只是其中一个触发点。
两者实现共用同一条停机路径（§5.1 的 7 步）。

### 5.3 重启恢复

testnet 进程崩溃或被人工 `kill -SIGTERM` 后再次启动：

1. 必须显式 `--previous-run-id <id>`。runner 读取上一个 bundle 的
   `run_manifest.json`，提取 `processed_until_ns`、`positions.parquet`、
   `orders.parquet`。
2. 调用交易所 REST：
   - `GET /api/v3/openOrders` 拿当前 open orders。
   - `GET /api/v3/account` 拿仓位。
3. 三方对账：
   - 上次 bundle 的 open orders vs 交易所返回的 open orders → 差异计入
     `runtime.restart_order_drift`。
   - 上次 bundle 的 open positions vs 交易所返回 → `runtime.restart_position_drift`。
   - 任意一方有差异 → runner **拒绝**继续运行，写 `restart_drift_detected`
     到 `logs/alerts.log`，退出码 3，让操作员人工核对。
4. 三方一致 → 启动新 run_id：
   - `runtime.previous_run_id` = 上一个 run_id。
   - `runtime.previous_manifest_sha256` = 上一个 manifest 的 sha256。
   - `runtime.restart_sequence` = 上一个的 restart_sequence + 1。
   - `runtime.restart_reason` = `--restart-reason` 必须显式提供。
5. 信号 cursor 从 `processed_until_ns + 1` 开始，新 bar 与前一段无重叠。

ADR-007 §2.4 已经规定了 paper 的重启字段；本 ADR 把 testnet 重启额外
要求"交易所对账一致"作为继续运行的硬条件。

### 5.4 报警最小集

`logs/alerts.log` 是 Phase 3 报警唯一目的地，行格式 JSON Lines：

```json
{"ts": "...", "severity": "warning|error|critical", "kind": "...", "run_id": "...", "msg": "...", "context": {...}}
```

必报的事件：

- `kill_switch_fired`（critical）
- `restart_drift_detected`（critical）
- `data_gap_exceeded_tolerance`（error）
- `signal_lag_exceeded_threshold`（warning）
- `exchange_error_burst`（error）
- `ws_disconnected`（warning）
- `heartbeat_lost`（critical）
- `emergency_flatten_started`（critical）
- `emergency_flatten_completed`（critical）

进程退出码约定：

| 码 | 含义 |
|---:|---|
| 0 | 正常停机 |
| 1 | 一般运行错误（已记录） |
| 2 | 启动校验失败（凭证、git_dirty、stage cap、policy 不一致） |
| 3 | 重启对账失败 |
| 4 | kill-switch 触发后 emergency flatten 已成功 |
| 5 | kill-switch 触发但 emergency flatten 部分失败 |

退出码 5 是最严重的状态——操作员必须人工进交易所核对、撤单、平仓。

### 5.5 watchdog（外部进程）

testnet runner 自身可能崩溃到无法触发 emergency flatten。Phase 3 必须
有一个独立的 watchdog 进程（实现待 §6.4 决定，可能是 systemd timer +
Python 脚本或独立 Rust binary）：

- 每 30 秒读 `data/testnet/<active_run_id>/logs/heartbeat.jsonl` 末尾。
- 心跳超过阈值 → 调用 `emergency_flatten` CLI 强制平仓。
- watchdog 自身的状态写 `infra/watchdog/state.json`。

watchdog 不读真实凭证（emergency_flatten 自己读），只持有 runner 的 PID
和 bundle 路径。

### 5.6 testnet → live 升档前置

ADR-007 §2.5 已给出 testnet_canary → live_canary 的升档条件
"testnet 连续 14 天不需手动干预；ADR-001 资金阶梯从 100-500 USDT 开始"。
本 ADR 把"不需手动干预"具体化：

| 项 | 阈值 |
|---|---|
| `runtime.exchange_error_count` 总和 | < 1000 |
| `runtime.ws_reconnect_count` 总和 | < 50 |
| `runtime.restart_sequence` | ≤ 3（计划性重启允许） |
| `runtime.restart_drift_detected` | 0 |
| `kill_switch_fired` 报警 | 0 |
| `emergency_flatten_completed` 报警 | 0 |
| 14 天滚动窗内每日 PnL 标准差 | 与 paper_simulated 同 source 的相对误差 < 100% |

最后一项是为了拒绝"PnL 大幅偏离 paper_simulated"的情况——live 之前要求
testnet 的统计行为与 paper_simulated 同一数量级，避免模型在真撮合下崩溃。

---

## 6. 实现路线图

ADR 是规范，运行时仍未实现。`promotion_review` 的 `phase_3_not_ready`
gate 在以下子阶段全部完成且测试通过前都不放开。

### 6.1 Phase 3a：wall-clock paper

- 在 `apps/strategies_nautilus/runners/paper_runner.py` 新增
  `--data-mode wall_clock` 参数。
- 实现 Binance public WS 1m bar 消费器，落入同一个 catalog polling
  cursor 路径。
- 不读凭证，不连 testnet。
- 验收：连续运行 ≥ 24 小时无人工干预，bundle 与 catalog_polling 同尺度
  fingerprint，重启续跑通过 §5.3 的对账（此时三方对账只对本地 catalog，
  不对交易所）。

### 6.2 Phase 3b：testnet adapter

- 新增 `apps/strategies_nautilus/runners/testnet_runner.py`。
- 引入 NautilusTrader 的 Binance 适配器，仅启用 testnet endpoint。
- 实现 §4 的全部启动校验（双签 flag、key 长度、git_dirty、stage cap、retro 链）。
- 验收：tests 覆盖"无 `--allow-real-credentials` 必须拒绝"、"key 长度
  不足必须拒绝"、"git_dirty 必须拒绝"、"未通过 paper_simulated retro
  的 source 必须拒绝"。

### 6.3 Phase 3c：emergency flatten + kill-switch 集成

- 新增 `apps/strategies_nautilus/runners/emergency_flatten.py`。
- 把 §5.1 的 7 步实现并测试（用 Binance testnet 模拟 fill 完成）。
- 在 testnet_runner 中接入 §5.2 的自动触发条件。
- 验收：tests 覆盖 `cancel_only` 路径、`reduce_only` 平仓路径、超时残单
  报告、`emergency_flatten.json` 落盘字段完整。

### 6.4 Phase 3d：重启对账

- 在 testnet_runner 启动路径中实现 §5.3 的 REST 对账。
- watchdog 进程：先用最简单的 systemd timer + Python 脚本，
  实现位置 `infra/watchdog/`。
- 验收：杀进程后重启，三方对账有差异时退出码 = 3 且 alerts.log 含
  `restart_drift_detected`。

### 6.5 Phase 3e：报警写入

- 把 §5.4 的 9 个事件加进 runner 的 alert 出口。
- 退出码按 §5.4 表实现。
- 验收：tests 覆盖每个事件路径都正确写入 `logs/alerts.log`。

### 6.6 Phase 3f：第一次 testnet_canary promote

- 操作员在 docs/retros/ 写 `decision=promote` retro，
  current_stage=paper_simulated → target_stage=testnet_canary。
- `promotion_review` 当前会以 `phase_3_not_ready` 阻断；要解开 gate，
  需要一个最小补丁把 `PHASE_2_STAGE_LIMIT` 改成 `STAGE_TESTNET_CANARY`，
  并新增 testnet 阶段的额外校验。
- 这个补丁本身是 Phase 3f 的工作，**不**在本 ADR 中实现。

---

## 7. 验证清单

下面这份清单是后续每个子阶段的合格标准。任何阶段在 commit 前必须能够
回答"是否满足这一栏"，否则不能进入下一个子阶段。

### 7.1 凭证

- [ ] 仓库内不含真实 API key / secret（grep 全树确认）。
- [ ] `infra/.env.example` 字段名齐全，值留空。
- [ ] `.gitignore` 排除 `*.env`、`.envrc`、`infra/secrets/`。
- [ ] runner 启动时 key 长度 < 32 必须拒绝。
- [ ] runner 在缺 `--allow-real-credentials` 时必须拒绝。
- [ ] manifest 里只写 `credentials_source` + `credentials_key_prefix`，不写完整 key。
- [ ] tests 覆盖以上每条路径。

### 7.2 wall-clock paper

- [ ] `--data-mode wall_clock` 不读任何 `BINANCE_*` 环境变量。
- [ ] WS 断线后能在 N 秒内重连（N 待 §6.1 实测）。
- [ ] 重复 bar（WS 抖动）必须按 ts_event_ns 去重。
- [ ] 连续运行 24 小时 bundle 完整：每个小时一段心跳，无 data_gap。

### 7.3 testnet runtime

- [ ] `kind="testnet"` 与 `runtime.mode="testnet"` 同时出现。
- [ ] testnet bundle 落到 `data/testnet/`，与 paper / backtest 分离。
- [ ] 真实 testnet 订单 ID 出现在 orders.parquet。
- [ ] 真实 testnet 账户余额出现在 account_balances.parquet。
- [ ] manifest 不含完整 key / secret（grep 字符串）。

### 7.4 emergency flatten

- [ ] 流程顺序按 §5.1 七步：先撤单后平仓。
- [ ] `emergency_flatten.json` 字段完整：触发时间、操作员、reason、
      cancelled_orders、closed_positions、residual_*、final_account、success。
- [ ] tests 覆盖 cancel_only、reduce_only、超时残单。
- [ ] runner 的 manifest `runtime.shutdown_reason="emergency_flatten"` 落盘。

### 7.5 kill-switch

- [ ] 当日 PnL ≤ -5% × starting_balance → 自动触发 emergency flatten。
- [ ] kill-switch 触发后写 `kill_switch_fired` alert。
- [ ] 退出码 4（成功）或 5（部分失败）。
- [ ] 同 source 自动降回 `paper_shadow`（写 `disable` retro）。

### 7.6 重启对账

- [ ] `--previous-run-id` 是必填项。
- [ ] 三方对账（local bundle / open orders / account）有差异 → 退出码 3。
- [ ] 一致时 `restart_sequence += 1`、`previous_manifest_sha256` 写入新
      manifest。
- [ ] 新 cursor 从 `processed_until_ns + 1` 开始，无重复消费。

### 7.7 报警

- [ ] `logs/alerts.log` 是 JSON Lines，每行可被 `jq` 解析。
- [ ] §5.4 列的 9 个事件全部有触发路径，每个都被 tests 覆盖。
- [ ] 退出码按 §5.4 表落实，没有出现"应当是 3 却返回 1"的情况。

---

## 8. 与 promotion_review 的关系

本 ADR 不要求 `apps/strategies_nautilus/runners/promotion_review.py` 立即
变化。`PHASE_2_STAGE_LIMIT = STAGE_PAPER_SIMULATED` 仍是当前正确的硬阶梯。

只有在 §6.1–§6.5 全部完成（含 tests）之后，§6.6 才会用一个独立小补丁
把 `PHASE_2_STAGE_LIMIT` 改成 `STAGE_TESTNET_CANARY` 并加 testnet 阶段
的策略边界（`max_multiplier=0.2`、`dry_run_required=False`、
`requires_paper_simulated_retro=True`、`requires_testnet_runbook_signoff=True`）。

补丁不动 `PolicyFields` schema，也不动现有 `paper_simulated → ...`
gate；它纯粹放开一个上限并增加新一段 `_decision_specific_blockers`。

---

## 9. 与已有 ADR 的链接

- ADR-001 §6 资金阶梯：`testnet_canary` 仍是 0；`live_canary` 起点
  100–500 USDT，由本 ADR §5.6 的稳定性指标作为附加门槛。
- ADR-002 §3 字段集合：testnet 不变。
- ADR-002 §4.1 traceability：testnet bundle 也必须保证每条 fill / order
  / position 带 `signal_id`。
- ADR-004 manifest：`kind="testnet"` 是预留值，运行字段在 §3.2 加
  testnet 专属内容。
- ADR-006 SourcePolicy：testnet_canary 阶段的 multiplier 上限仍是
  0.2，与 ADR-007 §2.5 一致。
- ADR-007 §2.5 升档表 `paper_simulated → testnet_canary` 行：本 ADR
  §5.6 + §7 把"runbook 就绪"这一行的具体含义钉死。
- ADR-007 §4 后续 ADR：原 ADR-008（LLM）顺延为 ADR-009；原 ADR-009
  （Redis Stream）顺延为 ADR-010。本 ADR 占用 ADR-008。

---

## 10. 决策

**Accepted as draft.** 本 ADR 把 Phase 3 风控、testnet runtime、凭证、
emergency flatten、重启、报警的规范钉下来。运行时实现按 §6 路线分子
阶段进行；每个子阶段完成前 `phase_3_not_ready` gate 不放开，第一次
`testnet_canary` promote retro 必须复审本 ADR 并附带 §7 全部勾选项的
证据。

不动 ADR-001 五条铁律，不动 ADR-002 schema，不动 `SourcePolicy` 字段，
不引入新长驻服务，不在仓库引入任何凭证。
