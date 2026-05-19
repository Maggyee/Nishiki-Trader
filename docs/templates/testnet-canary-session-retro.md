# Phase 3f testnet canary session — `<YYYY-MM-DD>`

- **Date (UTC)**: `<YYYY-MM-DDTHH:MM:SSZ>`
- **Operator**: nishiki
- **ADR**: [ADR-008 §6.6](../decisions/008-phase3-risk-runbook.md) Phase 3f
- **Kind**: Operational session retro — not a `SourcePolicy` decision.
  A separate `promotion_review` retro must be opened afterwards to
  record whether this session supports a hold / demote / disable on
  `freqai_linear_v1 / linear-mom-train20240105` at `testnet_canary`.

> Template lives at `docs/templates/testnet-canary-session-retro.md`.
> Copy, rename to `docs/retros/<UTC date>-phase-3f-testnet-canary-session.md`,
> and fill in every `<placeholder>`. Delete this blockquote when done.

## 1. Scope

First real testnet canary session under ADR-008 §6.6: `testnet_runner.py
--long-run --enable-strategy-execution` registered one streaming
`BaselineNautilusStrategy` backed by
`SignalStorePollingSource(freqai_linear_v1 / linear-mom-train20240105)`
against Binance Spot testnet. Authorized policy:
`SourcePolicy(dry_run=False, position_pct_multiplier=<MULT>,
min_confidence_override=None)` from
`docs/retros/2026-05-19-freqai-linear-v1-promote-testnet-canary.md`.

## 2. Run identity

- bundle: `data/testnet/<RUN_ID>/`
- run_id: `<RUN_ID>`
- git_commit at launch: `<SHA>`
- git_dirty: `<true|false>`
- started_at: `<ISO_TS>`
- finished_at: `<ISO_TS>`
- elapsed_seconds: `<float>` (max_run_seconds = `<int>`)
- credentials_source: `env:BINANCE_TESTNET_API_KEY,BINANCE_TESTNET_API_SECRET`
- credentials_key_prefix: `<8 chars only — never the full key>`

## 3. Runtime counters

| metric | value |
|---|---:|
| kind | `testnet` |
| runtime.mode | `testnet` |
| runtime.data_mode | `exchange_ws` |
| runtime.order_mode | `exchange_testnet` |
| enable_strategy_execution | `true` |
| strategies_registered | `<int>` |
| actors_registered | `<int>` |
| source | `freqai_linear_v1` |
| model_version | `linear-mom-train20240105` |
| policy_position_pct_multiplier | `<float>` |
| starting_balance USDT | `<float>` |
| daily_pnl USDT (final) | `<float>` |
| open_orders (final) | `<int>` |
| open_positions (final) | `<int>` |
| restart_sequence | `<int>` |
| restart_drift_detected | `<true|false>` |
| exchange_error_count | `<int>` |
| ws_reconnect_count | `<int>` |
| shutdown_reason | `<max_duration|emergency_flatten|...>` |
| auto_flatten_trigger | `<null|...>` |
| emergency_flatten_success | `<null|true|false>` |

## 4. Heartbeat cadence

- first heartbeat: `<ISO_TS>`
- last heartbeat: `<ISO_TS>`
- count: `<int>` rows in `logs/heartbeat.jsonl`
- ws_connected throughout: `<true|false>`

If any transition happened, note the wall-clock time and what the
runtime recorded.

## 5. §5.4 alert outcome

`logs/alerts.log` `<exists with N lines|does not exist>`. If it does
not exist, that is the authoritative record that none of the 9 alerts
fired.

| §5.4 kind | source | fired this session |
|---|---|---|
| `kill_switch_fired` | `testnet_runner.py` | `<no|yes (N)>` |
| `restart_drift_detected` | `testnet_runner.py` | `<no|yes (N)>` |
| `exchange_error_burst` | `testnet_runner.py` | `<no|yes (N)>` |
| `ws_disconnected` | `testnet_runner.py` | `<no|yes (N)>` |
| `data_gap_exceeded_tolerance` | `testnet_runner.py` | `<no|yes (N)>` |
| `signal_lag_exceeded_threshold` | `testnet_runner.py` | `<no|yes (N)>` |
| `heartbeat_lost` | `infra/watchdog/watchdog.py` | `<no|yes (N)>` |
| `emergency_flatten_started` | `emergency_flatten.py` | `<no|yes (N)>` |
| `emergency_flatten_completed` | `emergency_flatten.py` | `<no|yes (N)>` |

If any fired, copy the relevant `logs/alerts.log` row below and explain.

## 6. Runtime.log lifecycle

| event | ts |
|---|---|
| `credentials_loaded` | `<ISO_TS>` |
| `node_built` | `<ISO_TS>` |
| `node_run_invoked` | `<ISO_TS>` |
| `strategies_registered` (strategies = `<int>`, actors = `<int>`) | `<ISO_TS>` |
| `shutdown` (stop_reason=`<value>`) | `<ISO_TS>` |

Build-to-run latency: `<float>` s. Run-to-shutdown: `<float>` s.

## 7. Nautilus log evidence

- `grep -c ERROR /tmp/phase3f-canary/runner.stdout.log` → `<int>`.
- `grep -c WARN` → `<int>` (note any WARN beyond the
  `BinanceSpotInstrumentProvider: zero fees` informational and the
  user-data `eventStreamTerminated` reconnect).
- `Account BINANCE-SPOT-master registered in cache` at `<T+s>`.
- `Reconciliation for BINANCE succeeded` at `<T+s>`.
- stderr file: `<N bytes>` (`<empty|copy contents below>`).
- Engine teardown lines: `<all DISPOSED at <ISO_TS>|other>`.

## 8. Watchdog evidence

- `grep -c '"status": "healthy"' /tmp/phase3f-canary/watchdog.loop.log`
  → `<int>` (expect ≈ elapsed_seconds / 30).
- `grep -c '"flatten_invoked": true'` → `<int>` (expect 0 on clean
  session).
- Final `infra/watchdog/state.json`: `status=<healthy|...>`,
  `exit_code=<int>`, `flatten_invoked=<bool>`,
  `heartbeat_age_seconds=<float>`, `alert_path=<null|...>`.

## 9. Real order flow

This session can produce real testnet order / fill / position events.
If live testnet sidecars are not present yet, say "not written" for the
parquet rows and record the Nautilus stdout order/fill/position evidence
plus exchange order/trade IDs instead.

- `orders.parquet` row count: `<int>` (vs `<int>` in v9 simulated)
- `fills.parquet` row count: `<int>`
- `positions.parquet` row count: `<int>`
- `account_balances.parquet` row count: `<int>`
- First order client_order_id / first fill exchange order_id: `<...>`
- First fill ts_event: `<ISO_TS>`; last fill ts_event: `<ISO_TS>`
- Net PnL on closed positions USDT: `<float>`
- Max drawdown observed during session USDT: `<float>`
- `signal_id` round-trip: every fill row carries `signal_id` `<true|false>`

If 0 orders fired during the session, explain why (no `freqai_linear_v1`
signals were produced during the window; producer was idle; etc.).

## 10. Signal flow

- `SignalStorePollingSource(cursor_ns).start` = `<int>`
- `SignalStorePollingSource(cursor_ns).end` = `<int>`
- rows popped during the session: `<int>`
- rows rejected by Authorization or SourcePolicy: `<int>`
- rows accepted into the strategy: `<int>`

## 11. Decision

This retro **does not** mutate `SourcePolicy`. It records what
happened. The follow-up `promotion_review` retro will use this
session retro as `--testnet-runbook-signoff-path` to gate the next
decision (hold/demote/disable on `freqai_linear_v1` at `testnet_canary`).

Recommended next decision (informal, must still go through
`promotion_review`):

- `<hold @ testnet_canary>` — clean session, keep observing.
- `<demote → paper_simulated>` — anomalies surfaced; back off until
  fixed.
- `<disable>` — kill_switch fired or other ADR-001 §2 violation; halt
  the source.
