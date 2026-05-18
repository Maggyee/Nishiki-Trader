# Phase 3a wall-clock paper runtime - 24h soak

- **Date (UTC)**: 2026-05-18
- **Operator**: nishiki
- **ADR**: [ADR-008 §6.1](../decisions/008-phase3-risk-runbook.md) Phase 3a
- **Kind**: Runtime acceptance retro - not a `SourcePolicy` decision. No
  source / model_version was promoted, held, demoted, or disabled.

## 1. Scope

This retro records the ADR-008 §7.2 item 4 wall-clock paper soak. The
runner used Binance public WS 1m closed klines and the ADR-007 paper
simulator. It did not read credentials, connect to testnet, submit orders,
or open any exchange adapter path.

The authoritative run is the current-control-machine run below. The earlier
home-frp attempt is not used as evidence because that host could lose power.

## 2. Run identity

- bundle: `data/paper/20260517-094345Z-ad69bd68/`
- run_id: `20260517-094345Z-ad69bd68`
- manifest_sha256:
  `98984bd15a37600b695716d072eb0688207d0154397e80d88a43ea7663aaca44`
- git_commit: `d122ffda1011bdd5af9f9ae0db48b7bcd3d743cb`
- git_dirty: `false`
- started_at: `2026-05-17T09:43:45.246Z`
- finished_at: `2026-05-18T09:43:45.429Z`
- elapsed_seconds: `86400.183665`

## 3. Runtime counters

| metric | value |
|---|---:|
| kind | `paper` |
| runtime.mode | `paper` |
| runtime.data_mode | `wall_clock` |
| runtime.order_mode | `simulated` |
| bar_source | `binance_public_ws` |
| ws_endpoint | `wss://data-stream.binance.vision:9443` |
| ws_stream | `btcusdt@kline_1m` |
| max_duration_seconds | 86400 |
| shutdown_reason | `max_duration` |
| bar_count | 1440 |
| poll_count | 1440 |
| heartbeat_count | 24 |
| data_gap_count | 0 |
| ws_reconnect_count | 0 |
| duplicate_bars_dropped | 0 |
| credentials_loaded | `false` |
| restart_sequence | 0 |

## 4. Heartbeat cadence

The run wrote 24 rows to `logs/heartbeat.jsonl`, one per hour while the WS
stream stayed healthy.

- first heartbeat wall clock: `2026-05-17T09:44:00.041Z`
- first heartbeat poll_number: `1`
- last heartbeat wall clock: `2026-05-18T08:44:00.038Z`
- last heartbeat poll_number: `1381`
- heartbeat runtime data_gap_count: `0` throughout

## 5. Sidecars and policy

The soak used an empty `SignalStore` for runtime stability evidence, so it
is not a return-side or alpha test.

- signal_rows: 0
- accepted_signals: 0
- orders / fills / positions: 0 / 0 / 0
- account_balances rows: 1440
- PnL USDT: 0.0
- max_drawdown_pct USDT: 0.0
- policy: `freqai_linear_v1 / linear-mom-train20240105`,
  `dry_run=true`, `position_pct_multiplier=0.2`

`report_paper_bundle` correctly marks this bundle ineligible for a
`SourcePolicy` review because `runtime.data_mode="wall_clock"` and there
are no signals. That is expected; this retro is only the Phase 3a runtime
stability record.

## 6. ADR-008 §7.2 result

| §7.2 item | Status | Evidence |
|---|---|---|
| 1 - `--data-mode wall_clock` reads no `BINANCE_*` env vars | pass | Existing grep/unit coverage plus manifest `credentials_loaded=false` |
| 2 - WS reconnect behavior observable | pass | `ws_reconnect_count=0`; no reconnect was needed over this 24h window |
| 3 - duplicate bars deduped by `ts_event_ns` | pass | Runtime `duplicate_bars_dropped=0`; dedup path remains unit-covered |
| 4 - 24h continuous, one heartbeat per hour, no `data_gap` | pass | `elapsed_seconds=86400.183665`, `bar_count=1440`, `heartbeat_count=24`, `data_gap_count=0`, `shutdown_reason=max_duration` |

## 7. Decision

ADR-008 §6.1 Phase 3a wall-clock paper runtime is accepted as complete for
this code baseline. This does **not** promote any signal source to
`testnet_canary`; it only clears the wall-clock-paper precondition needed
before continuing ADR-008 §6.2 Phase 3b.

Next implementation step: continue Phase 3b by wiring the guarded
`testnet_runner.py` startup path to Binance testnet only behind the existing
credential, clean-git, retro-evidence, and policy-multiplier gates.
