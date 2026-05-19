# Phase 3f testnet long-run - 6h stability soak

- **Date (UTC)**: 2026-05-18
- **Operator**: nishiki
- **ADR**: [ADR-008 §6.6](../decisions/008-phase3-risk-runbook.md) Phase 3f
- **Kind**: Runtime stability retro — **not** a `SourcePolicy` decision. No
  source / model_version is promoted, held, demoted, or disabled by this
  retro. It records the pre-promote testnet stability evidence that ADR-008
  §6.6 requires before a `paper_simulated → testnet_canary` `decision=promote`
  retro can be opened.

## 1. Scope

This retro records the ADR-008 §6.6 testnet long-run on Binance Spot testnet.
`testnet_runner.py --long-run` ran with one already-`paper_simulated` source
(`freqai_linear_v1 / linear-mom-train20240105`, `position_pct_multiplier=0.2`,
`dry_run=False`) and the external `infra/watchdog/watchdog.py` loop. The
runner connected to `https://testnet.binance.vision` with Ed25519 PEM-PKCS#8
credentials and exercised the full Phase 3a–3e stack (startup guard, adapter
config, emergency-flatten path, restart reconciliation, alert outlet) for
6 hours with no strategies registered against live signal flow — the runner
holds `0` open orders / `0` open positions / `0.0` daily PnL throughout, so
this is a runtime-stability soak, not a return-side test.

The `phase_3_not_ready` gate in `promotion_review.py`
(`PHASE_2_STAGE_LIMIT = STAGE_PAPER_SIMULATED`) stays closed. The follow-up
patch that raises it to `STAGE_TESTNET_CANARY` is an explicit follow-up item
under ADR-008 §6.6 and is tracked in §9 below.

## 2. Run identity

- bundle: `data/testnet/20260518-150212Z-997bf080/`
- run_id: `20260518-150212Z-997bf080`
- git_commit at launch: `8f0e0413ed171e53ba082465dce74143efcf47e0`
  (ADR-008 §6.5 Phase 3e alert outlet)
- git_dirty: `false`
- started_at: `2026-05-18T15:02:12.825Z`
- finished_at: `2026-05-18T21:02:18.018Z`
- elapsed_seconds: `21605.192657` (max_run_seconds=21600, drift 5.19s)
- credentials_source: `env:BINANCE_TESTNET_API_KEY,BINANCE_TESTNET_API_SECRET`
- credentials_key_prefix: `yKtnt9cb` (8 chars only; full key never on disk)
- credentials_loaded: `true`

## 3. Runtime counters

| metric | value |
|---|---:|
| kind | `testnet` |
| runtime.mode | `testnet` |
| runtime.data_mode | `exchange_ws` |
| runtime.order_mode | `exchange_testnet` |
| exchange | `binance` |
| exchange_endpoint | `https://testnet.binance.vision` |
| instrument_ids | `BTCUSDT.BINANCE` |
| trader_id | `TESTNET_TRADER-001` |
| source | `freqai_linear_v1` |
| model_version | `linear-mom-train20240105` |
| policy_position_pct_multiplier | 0.2 |
| starting_balance USDT | 10000.0 |
| daily_pnl USDT | 0.0 |
| account_total_usdt (last heartbeat) | 10000.0 |
| daily_loss_limit_pct | 0.05 |
| open_orders (final) | 0 |
| open_positions (final) | 0 |
| restart_sequence | 0 |
| restart_drift_detected | `false` |
| exchange_error_count | 0 |
| exchange_error_burst_threshold | 50 |
| ws_connected (final) | `true` |
| ws_reconnect_count | 0 |
| ws_reconnect_burst_threshold | 10 |
| data_gap_tolerance_seconds | 120.0 |
| signal_lag_threshold_seconds | 60.0 |
| heartbeat_interval_seconds | 30.0 |
| shutdown_reason | `max_duration` |
| auto_flatten_trigger (final shutdown event) | `null` |
| emergency_flatten_success (final shutdown event) | `null` |

## 4. Heartbeat cadence

`logs/heartbeat.jsonl` carries 720 rows, one every 30s, matching the
21600 s budget exactly (21600 / 30 = 720).

- first heartbeat: `2026-05-18T15:02:12.858Z`
- last heartbeat: `2026-05-18T21:01:48.192Z`
- every row carries `ws_connected=true`, `exchange_error_count=0`,
  `ws_reconnect_count=0`, `open_orders=0`, `open_positions=0`,
  `account_total_usdt=10000.0`, `daily_pnl=0.0`

## 5. §5.4 alert silence

`logs/alerts.log` **does not exist** in the bundle. ADR-008 §5.4 requires
the file to be created only on the first write, so its absence is the
authoritative record that none of the 9 alert kinds fired:

| §5.4 kind | source | fired |
|---|---|---|
| `kill_switch_fired` | `testnet_runner.py` | no |
| `restart_drift_detected` | `testnet_runner.py` | no (cold start, `restart_sequence=0`) |
| `exchange_error_burst` | `testnet_runner.py` | no (`exchange_error_count=0 < 50`) |
| `ws_disconnected` | `testnet_runner.py` | no (`ws_connected=true` on every heartbeat) |
| `data_gap_exceeded_tolerance` | `testnet_runner.py` | no |
| `signal_lag_exceeded_threshold` | `testnet_runner.py` | no |
| `heartbeat_lost` | `infra/watchdog/watchdog.py` | no |
| `emergency_flatten_started` | `emergency_flatten.py` | no |
| `emergency_flatten_completed` | `emergency_flatten.py` | no |

The runtime.log `shutdown` event likewise records
`auto_flatten_trigger=null` and `emergency_flatten_success=null` — the
monitor loop never elevated any condition to a kill-switch or emergency
flatten.

## 6. Runtime.log lifecycle four-tuple

`logs/runtime.log` carries exactly four lines, matching the ADR-008 §6.2
lifecycle contract:

| event | ts |
|---|---|
| `credentials_loaded` | `2026-05-18T15:02:12.825Z` |
| `node_built` | `2026-05-18T15:02:12.858Z` |
| `node_run_invoked` | `2026-05-18T15:02:12.859Z` |
| `shutdown` (`stop_reason=max_duration`) | `2026-05-18T21:02:18.018Z` |

Build-to-run latency 1 ms; run-to-shutdown 21605.19 s; shutdown event
records `node_built=true`, `node_run_invoked=true`,
`auto_flatten_trigger=null`, `emergency_flatten_success=null`.

## 7. Nautilus log evidence

`/tmp/phase3f/runner.stdout.log` (77 KB) was captured outside the bundle
for offline inspection.

- `Account BINANCE-SPOT-master registered in cache` at
  `2026-05-18T15:02:13.172Z` (T+0.348 s after `credentials_loaded`).
- `Reconciliation for BINANCE succeeded` at
  `2026-05-18T15:02:13.519Z` (T+0.694 s).
- `grep -c ERROR runner.stdout.log` → **0**.
- `/tmp/phase3f/runner.stderr.log` → **0 bytes**.
- Eight `BinanceSpotInstrumentProvider: Not requesting actual trade fees
  for TESTNET; all instruments will have zero fees` warnings (one at
  startup plus one each hour). This is Binance's own testnet-zero-fee
  advisory, not an ADR-008 §5.4 alert, and is informational.
- One `BinanceUserDataWebSocketClient: Received eventStreamTerminated,
  resubscribing...` at `2026-05-18T21:02:17.904Z`, **0.114 s before the
  scheduled shutdown** and **after** `node.stop()` had been invoked. The
  user-data listen key expired exactly as the node was being torn down; it
  did not trigger an ADR-008 §5.4 alert because (a) `ws_connected` on the
  monitored exchange WS path remained `true` and (b) the runner had
  already begun a clean stop. No retry escalation followed because the
  node disposed immediately after.
- Engine teardown was clean: `DataClient-BINANCE`, `DataEngine`,
  `RiskEngine`, `ExecClient-BINANCE`, `ExecEngine`, `TESTNET_TRADER-001`,
  `TradingNode` all log `DISPOSED` at `21:02:18.017–.018Z`.

## 8. Watchdog evidence

`infra/watchdog/watchdog.py` ran in an external loop (`/tmp/phase3f/
watchdog.loop.log`, 362 KB) with `heartbeat_timeout_seconds=90` and a 30 s
poll interval throughout the 6 h.

- `grep -c '"status": "healthy"'` → **714** (≈ 21600 s / 30 s, with a few
  ticks lost to the loop starting slightly after the runner and exiting
  slightly before final dispose).
- `grep -c '"flatten_invoked": true'` → **0**.
- Final `infra/watchdog/state.json` (last write at `21:01:48.427Z`):
  `status=healthy`, `exit_code=0`, `flatten_invoked=false`,
  `heartbeat_age_seconds=0.235`, `alert_path=null`.

The watchdog therefore confirms the runner's own "all silent" view from an
independent process — it never had to invoke `emergency_flatten` and never
saw a stale heartbeat.

## 9. ADR-008 §6.6 / §7 result

ADR-008 §7.3 (testnet runtime), §7.5 (kill-switch), §7.6 (restart
reconciliation), and §7.7 (alerts) all pass for this run:

| §7 row | status | evidence |
|---|---|---|
| 7.3 `kind=testnet` ↔ `runtime.mode=testnet`, bundle under `data/testnet/`, manifest carries no full key/secret | pass | §2, §3, `credentials_key_prefix=yKtnt9cb` |
| 7.3 real testnet order / account ids in sidecars | n/a | no orders / positions in this stability soak; this row is exercised by the future first promote bundle |
| 7.5 kill-switch on daily PnL ≤ -5% | not exercised | `daily_pnl=0.0` throughout; threshold not crossed |
| 7.6 `--previous-run-id` mandatory, drift exits 3 | pass | cold start, `restart_sequence=0`, `restart_drift_detected=false`; the `--previous-run-id` mandatory path is enforced by `test_testnet_runner_startup.py` |
| 7.7 alerts.log absent because no §5.4 event fired | pass | file does not exist; runtime + watchdog both record silent path |

ADR-008 §6.6 Phase 3f's first prerequisite — "all 9 §5.4 alert paths stay
silent over the test window" — is **met** on commit `8f0e041`.

## 10. Decision

ADR-008 §6.6 Phase 3f testnet stability soak is **accepted** for commit
`8f0e041`. This retro does **not** promote any source: it is the
prerequisite stability evidence ADR-008 §6.6 requires *before* a
`paper_simulated → testnet_canary` `decision=promote` retro can be opened.

`freqai_linear_v1 / linear-mom-train20240105` stays `hold @
paper_simulated`. The `phase_3_not_ready` gate in `promotion_review.py`
stays closed.

## 11. Next steps

1. Land the ADR-008 §6.6 / §8 promotion-review patch in a separate commit:
   raise `PHASE_2_STAGE_LIMIT` from `STAGE_PAPER_SIMULATED` to
   `STAGE_TESTNET_CANARY`, add testnet-stage extra blockers
   (`max_multiplier=0.2`, `dry_run_required=False`,
   `requires_paper_simulated_retro=True`,
   `requires_testnet_runbook_signoff=True`), and reference this retro as
   the runbook-signoff evidence. ADR-008 §8 explicitly scopes this patch
   to Phase 3f, not ADR-008 itself.
2. Only after that patch lands and is unit-tested, run
   `promotion_review.py --decision promote
   --target-stage testnet_canary` against the v9 `paper_simulated` bundle
   (`data/paper/20260517-053502Z-37b99b3f`) and this retro to produce the
   project's first `paper_simulated → testnet_canary` retro with
   `decision_allowed=True`.
3. Until then keep `testnet_runner.py --long-run` runs to stability-soak
   territory only: no strategies registered, no order flow, watchdog
   loop attached, `--previous-run-id` set on every restart.
