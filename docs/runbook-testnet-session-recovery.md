# ADR-017 固定测试网会话：未知订单与恢复处置

适用于 `spot-testnet-engineering-v1` 的一次工程会话。该账户包含原有资产；
不能套用通用 `emergency_flatten`、账户级撤单、全账户卖出或重启旧 testnet runner。
本手册不新增 BUY、SELL、撤单重试、重置会话或实盘权限。

## 1. 先读本地状态

在项目根目录执行：

```bash
.venv/bin/python -m apps.ops.portfolio_session_run --status
```

该入口不读取 Key、不联网、不获取执行租约、不创建文件，不需要干净代码才能检查。
固定私有目录是 `~/.local/state/trader/spot-testnet-engineering-v1`，没有路径或会话覆盖参数。
检查失败退出码为 1，读取成功为 0；退出码 0 仅表示读到了记录，不是恢复或下单许可。

- `evidence_basis=local_checkpoint_record`：最后一个可读检查点中的历史记录。
- `checkpoint_updated_ns` / `record_age_ns`：记录时间与年龄。
- `recorded_owned_btc`：记录中的本会话净持仓，不是当前交易所可卖余额。
- `current_venue_state_verified=false`：本地检查没有查询当前交易所状态。
- `orders`：原客户端订单 ID、买卖方向、本地订单状态，以及各类消耗记录。
- `submit_intent_consumed` / `cancel_intent_consumed`：提交/撤单机会已准备并消耗。
- `submit_dispatch_recorded` / `cancel_dispatch_recorded`：允许尝试发送的记录已经落盘；
  不代表 HTTP 请求抵达交易所，更不代表已成交或已撤单。
- `cancel_allowance_consumed=true`：无论是否看到发送记录，都不能再发一次撤单。
- `new_orders_authorized=false` / `cancel_retry_allowed=false`：报告不授予执行许可。

`evidence_basis=signed_reconciliation_at_observation` 只出现在正常运行/恢复的成功报告中。
它表示在 `observation_received_ns` 时完成了来源绑定的完整原生对账；以后读这个文件，
仍不能把它当作当前交易所状态或重新执行许可。

## 2. 按结果处置

| 结果 / 情况 | 后续操作 |
| --- | --- |
| `recorded_terminal_no_inventory` | 本地记录为终态且净持仓为零。核对既有成功对账证据；已完成的会话保留归档，不再次执行 BUY。 |
| `recorded_terminal_with_residual` | 保留本会话余量。不能凑单、四舍五入、卖出原有资产或再发清理 SELL。 |
| `recorded_active_requires_reconciliation` | 当前活动状态尚未确认。先走下述 GET 对账；本地显示 ACCEPTED/PARTIALLY_FILLED 不能直接授权撤单。 |
| `unresolved_submission_no_resubmit` | 准备/提交已消耗，但结果不明。只查询原订单，不改 ID、不补发 BUY/SELL。 |
| `unresolved_cancellation_no_retry` | 撤单已准备、已尝试或处于 PendingCancel。保留订单和资金冻结；没有撤单确认就不能宣布订单关闭，不能补发撤单。 |
| `activated_without_order_record` | 激活已存在。空订单记录不能恢复整轮执行机会；保留激活文件并复核中断点。 |
| `unknown_preserve_scope` | 文件缺失、损坏、权限不符、来源不符或读取时变化。持仓与订单返回 null，不解释为零；复核私有文件，不能删文件重新开始。 |
| `halt_reasons` 非空 | 保留每条停机记录。费用/经济异常不能当作网络异常清除；先复核原始成交、费用及账户差异。 |

只有原生已确认成交才改变本会话持仓。冻结不等于成交，未成交卖出不产生收入。
即使报告显示没有 SELL 意图，也不代表可以在恢复进程中创建 SELL。

## 3. GET 对账和严格受限的撤单

当 `collector_history_window_expired=false` 且私有文件完整时，可按需执行只读对账：

```bash
.venv/bin/python -m apps.ops.portfolio_session_run --recover
```

它使用已有 Key 和新的签名订阅，查询完整账户、账户级未完成订单、所有原订单和成交。
它不提交/撤销订单，不替换固定 `native.json`，只生成独立的私有证据和恢复报告。
失败不代表交易所没有订单，也不允许自动循环重试。

`--recover-cancel` 是带撤单能力的独立操作，不是 `--recover` 的自动下一步。它要求
干净且已同步的代码、新鲜完整签名对账、唯一原活动订单、原提交凭证，以及**从未准备或
尝试过的撤单机会**。历史停机只有既定传输原因可以共存；它不清除历史停机。
任何已消耗撤单、证据缺失、来源变化或经济异常都不能绕过。
终态分支仅返回 no-action。该入口永远不创建新的 BUY/SELL。

若交易所仍有活动订单，而撤单机会已经消耗或恢复被阻断，保留原 ID、原始响应、成交、
冻结与失败记录并进入专项事故复核。本范围没有追加脚本或网页重试的操作许可。

## 4. 超过历史窗口或状态不能读取

收集器只接收会话开始后 24 小时内的完整历史；`--status` 使用同一个时间常量。
窗口过期时 `next_step=review_archived_evidence_history_window_exceeded`。
此时停止反复调用恢复入口，不改变 `started_ns`、时间限制、激活文件或客户端订单 ID。

检查已有 `*-report.json`、`*-evidence.json`、`*-recovered.json`、`*-stream.jsonl`
与 `*-failure.json`。成功报告应有完整账户对账、原订单/成交数量、观察时间和相关哈希。
失败报告新增 `operator_status`，其来源始终是本地记录，不能提升为签名对账结论。
文件名、哈希或内容自述本身不能证明交易所身份、历史连续性或当前余额。
不公开 Key、签名 URL、完整账户余额或原始私有归档。

离线复核入口如下；每次在新的 Python 进程中运行，替换参数为**历史报告中已经记录的**
归档/原输入检查点哈希和所选 collection ID，不自动挑选最新文件：

```bash
.venv/bin/python -m apps.ops.portfolio_session_archive \
  --archive /path/to/retained-stream.jsonl \
  --archive-sha256 ORIGINAL_ARCHIVE_SHA256 \
  --checkpoint /path/to/original-native.json \
  --checkpoint-sha256 ORIGINAL_INPUT_CHECKPOINT_SHA256 \
  --collection-id ORIGINAL_COLLECTION_ID \
  --output /path/to/new-private-review.json
```

文件必须是当前用户所有、权限 0600 的普通文件；输入不接受符号链接，输出必须尚不存在。
入口不读 Key、不联网、不创建会话租约，只新建一份私有诊断报告，不写恢复检查点。
原输入检查点缺失时不能用后来的 recovered 文件替代，也不能重新计算现有文件的哈希来
冒充历史引用。归档截断、缺原始响应、缺完成封印、错误来源/订单/时间或原生资金不符，
都返回退出码 1；成功返回 0 只代表历史复核完成。

报告的 `evidence_basis=archived_session_reconciliation_at_observation` 表示归档历史复核。
`observation_received_ns` 保留原观察时间，`reviewed_ns` / `observation_age_ns` 表示复核时间
和历史年龄；`historical_view` / `historical_halt_reasons` 是当时原生状态及停机记录。
`current_venue_state_verified`、`source_authenticated`、`new_orders_authorized`、
`cancel_retry_allowed`、`runtime_ready` 均为 false。过期后重放成功不会延长恢复窗口。
实际所选文件、哈希与验收结果见
[9 月 13 日历史归档复核](progress/portfolio-testnet-session-archive-2026-09-13.md)。

磁盘失败时，失败报告也可能无法落盘。终端会给出 `--status` 命令和本手册路径；
状态入口返回 unknown 时保留现有文件，不能自动修复或覆盖最后一个成功检查点。

## 当前实际范围

2026-09-11 的真实测试 BUY 已成功撤销，无成交或本会话持仓，BUY 和撤单机会已消耗。
后续签名恢复确认过该终态。2026-09-12 的本地状态检查显示历史窗口已过期；这不是
新的交易所观察。9 月 13 日离线归档重放还原相同终态和全部 502 项资产，
未产生新交易所观察。当前没有本会话 BTC 可以用来验证真实清理 SELL。
真实成交/费用/活动订单恢复仍未验收；模拟通过不能替代这些证据或 14 天准入门槛。
