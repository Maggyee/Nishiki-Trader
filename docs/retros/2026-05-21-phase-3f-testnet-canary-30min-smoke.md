# Phase 3f testnet canary session — 2026-05-21 (30 min observability smoke)

- **Date (UTC)**: 2026-05-21T07:27:30Z – 2026-05-21T07:57:35Z
- **Operator**: nishiki
- **ADR**: [ADR-008 §6.6](../decisions/008-phase3-risk-runbook.md) Phase 3f
- **Kind**: Operational session retro — not a `SourcePolicy` decision.
  This run also doubles as the **end-to-end validation of the
  2026-05-21 observability + Postgres stack** brought forward to Phase 3
  entry; see §12.

## 1. Scope

Real testnet canary session under ADR-008 §6.6 with `max_run_seconds=1800`
(30 min), chosen specifically to make `data/observability/textfile/`
output flow through node_exporter → Prometheus → Grafana and to make
`logs/heartbeat.jsonl` flow through Promtail → Loki → Grafana under
**live** traffic, instead of relying on stale smoke-test series. The
canonical 6 h launcher is unchanged at
`infra/launchers/first-testnet-canary.py`; a sibling
`infra/launchers/first-testnet-canary-30min-smoke.py` (gitignored) carries
the only delta — `--max-run-seconds 1800`.

`testnet_runner.py --long-run --enable-strategy-execution
--write-live-sidecars` registered one streaming
`BaselineNautilusStrategy` backed by
`SignalStorePollingSource(freqai_linear_v1 / linear-mom-train20240105)`
against Binance Spot testnet. Authorized policy:
`SourcePolicy(dry_run=False, position_pct_multiplier=0.1,
min_confidence_override=None)` from
`docs/retros/2026-05-19-freqai-linear-v1-promote-testnet-canary.md`.

## 2. Run identity

- bundle: `data/testnet/20260521-072730Z-2e4d2146/`
- run_id: `20260521-072730Z-2e4d2146`
- git_commit at launch: `98fc9766f3e7fba021d2783686276443cd4364c8`
- git_dirty: `false`
- started_at: `2026-05-21T07:27:30.395Z`
- finished_at: `2026-05-21T07:57:35.744Z`
- elapsed_seconds: `1805.349395` (max_run_seconds = `1800`)
- credentials_source: `env:BINANCE_TESTNET_API_KEY,BINANCE_TESTNET_API_SECRET`
- credentials_key_prefix: `yKtnt9cb`

## 3. Runtime counters

| metric | value |
|---|---:|
| kind | `testnet` |
| runtime.mode | `testnet` |
| runtime.data_mode | `exchange_ws` |
| runtime.order_mode | `exchange_testnet` |
| enable_strategy_execution | `true` |
| write_live_sidecars | `true` |
| strategies_registered | `1` |
| actors_registered | `0` |
| source | `freqai_linear_v1` |
| model_version | `linear-mom-train20240105` |
| policy_position_pct_multiplier | `0.1` |
| starting_balance USDT | `10000.0` |
| daily_pnl USDT (final) | `76775.76058` |
| open_orders (final) | `0` |
| open_positions (final) | `0` |
| open_state_source | `live_sidecars` |
| restart_sequence | `0` |
| restart_drift_detected | `false` |
| exchange_error_count | `0` |
| ws_reconnect_count | `0` |
| shutdown_reason | `max_duration` |
| auto_flatten_trigger | `null` |
| emergency_flatten_success | `null` |

The `daily_pnl` value reflects a known pre-existing telemetry behaviour:
the Binance testnet account already carries a faucet balance of
~86775 USDT, but the runner's UTC-day anchor initializes from
`starting_balance=10000`. The 5 % kill-switch reference is therefore
`starting_balance × daily_loss_limit_pct = 500 USDT`, not 5 % of the
faucet balance. This is harmless on the up-side, but if a session ever
loses against the configured `starting_balance` the kill-switch will
fire at a tighter threshold than the testnet wallet actually carries.
Same behaviour observed in the 2026-05-20 6 h live-telemetry canary
(`daily_pnl_final ≈ +76775`). Not changing in this retro; tracked as
follow-up only.

## 4. Heartbeat cadence

- first heartbeat: `2026-05-21T07:27:30.469Z`
- last heartbeat: `2026-05-21T07:57:03.018Z`
- count: `60` rows in `logs/heartbeat.jsonl` (30 s cadence, 1800 s window)
- ws_connected throughout: `true` (histogram `{True: 60}`)
- open_positions histogram across the 60 samples: `{0: 36, 1: 24}` —
  0 before the 07:30 entry, 1 from entry to before the 07:57 exit
  sample; the final heartbeat (07:57:03) sampled before the scheduled
  close, so the live sidecars are the ground truth for the final FLAT
  state and the manifest's `open_state_source=live_sidecars` reflects
  that.

## 5. §5.4 alert outcome

`logs/alerts.log` exists with 1 line.

| §5.4 kind | source | fired this session |
|---|---|---|
| `kill_switch_fired` | `testnet_runner.py` | no |
| `restart_drift_detected` | `testnet_runner.py` | no |
| `exchange_error_burst` | `testnet_runner.py` | no |
| `ws_disconnected` | `testnet_runner.py` | no |
| `data_gap_exceeded_tolerance` | `testnet_runner.py` | no |
| `signal_lag_exceeded_threshold` | `testnet_runner.py` | **yes (1)** |
| `heartbeat_lost` | `infra/watchdog/watchdog.py` | no |
| `emergency_flatten_started` | `emergency_flatten.py` | no |
| `emergency_flatten_completed` | `emergency_flatten.py` | no |

The one fired alert:

```json
{"context": {"lag_seconds": 120.5757, "last_signal_ns": 1779350014326175448,
 "threshold_seconds": 120.0}, "kind": "testnet",
 "msg": "signal_lag_exceeded_threshold", "run_id": "20260521-072730Z-2e4d2146",
 "severity": "warning", "ts": "2026-05-21T07:55:34.901Z"}
```

**Expected and benign.** The wall-clock signal replay (§10) staged 25
signals starting 180 s after launcher start at 60 s cadence; the last
one's `ts_event` is `2026-05-21T07:53:34.326Z`. Two minutes after the
last signal (`07:55:34`), the 120 s lag threshold breached and the
advisory alert fired. The alert is warning-only, never triggers
auto-flatten, never changes exit code. For the canonical 6 h canary
the replay window must already exceed the run duration (the existing
runbook §1.5 example writes 480 signals at 45 s cadence = 6 h coverage,
so this only surfaces because the 30 min smoke used the smaller dry-run
preset).

## 6. Runtime.log lifecycle

| event | ts |
|---|---|
| `credentials_loaded` | `2026-05-21T07:27:30.395Z` |
| `node_built` | `2026-05-21T07:27:30.468Z` |
| `strategies_registered` (strategies = 1, actors = 0) | `2026-05-21T07:27:30.469Z` |
| `node_run_invoked` | `2026-05-21T07:27:30.469Z` |
| `sidecar_write` (success=true) | `2026-05-21T07:57:35.742Z` |
| `shutdown` (stop_reason=`max_duration`) | `2026-05-21T07:57:35.744Z` |

Build-to-run latency: 0.074 s. Run-to-shutdown:
1805.275 s. Sidecar write was 2 ms before shutdown — the new
`open_state_source=live_sidecars` path on the manifest correctly
back-fills the final FLAT state from the parquet rows.

## 7. Nautilus log evidence

- `grep -c ERROR /tmp/phase3f-canary/runner.stdout.log` → `0`.
- `grep -c WARN` → `4`. All four are previously-classified informationals:
  - `BinanceSpotInstrumentProvider: zero fees for TESTNET` at startup
    (T+0.085 s) — identical to every prior Phase 3 session.
  - `RiskEngine: Cannot check MARKET order risk: no prices for
    BTCUSDT.BINANCE` at `07:30:00.761Z` (entry submit) and
    `07:57:30.473Z` (scheduled close submit). The Nautilus RiskEngine
    needs a recent quote to size the value-at-risk pre-trade check;
    Binance Spot's WS does not push quotes, only kline+depth, so the
    check is skipped. Order still goes through. Same warning was on the
    previous canaries; surfacing it here so the retro is exhaustive.
  - `BinanceUserDataWebSocketClient: Received eventStreamTerminated,
    resubscribing...` at `07:57:35.510Z` (5 s before shutdown). Same
    teardown-race informational seen on every prior Phase 3 session.
- `Account BINANCE-SPOT-master registered in cache` at T+0.486 s.
- `Reconciliation for BINANCE succeeded` at T+0.841 s.
- stderr file: `0 bytes` (empty).
- Engine teardown: all engines DISPOSED cleanly between 07:57:35.510Z
  and 07:57:35.744Z.

## 8. Watchdog evidence

- `grep -c '"status": "healthy"' /tmp/phase3f-canary/watchdog.loop.log` →
  `60` (matches elapsed_seconds / 30 = 60.18).
- `grep -c '"flatten_invoked": true'` → `0`.
- Final `infra/watchdog/state.json`: `status=run_completed`,
  `exit_code=0`, `flatten_invoked=false`, `heartbeat_age_seconds=50.95`,
  `alert_path=null`.
- Watchdog history (`infra/watchdog/history.jsonl`) confirms the
  `8e5fada` terminal-manifest behaviour: as soon as the runner wrote a
  completed manifest, the watchdog's next tick flipped to
  `run_completed` and stopped emitting `heartbeat_lost` (compare with
  the 2026-05-19 6 h order-flow canary which is the regression that
  fix originally landed for).

## 9. Real order flow

- `orders.parquet` row count: `2` (vs `545` in v9 simulated; vs `2` in
  the 2026-05-20 6 h live-telemetry canary)
- `fills.parquet` row count: `2`
- `positions.parquet` row count: `1`
- `account_balances.parquet` row count: `451`
- `signal_lineage.parquet` row count: `25`
- First entry: `BUY MARKET 0.001 BTCUSDT.BINANCE @ 77611.97 USDT`,
  client_order_id `O-20260521-073000-001-000-1`,
  venue_order_id `5778771`, trade_id `1881069`,
  ts_event `2026-05-21T07:30:00.894Z`.
- Scheduled close: `SELL MARKET 0.001 BTCUSDT.BINANCE @ 77901.05 USDT`,
  client_order_id `O-20260521-075730-001-000-2`,
  venue_order_id `5784503`, trade_id `1881684`,
  ts_event `2026-05-21T07:57:30.524Z`.
- Position closed FLAT, realized_pnl `+0.28908 USDT`, 0 commissions
  (testnet zero-fee policy).
- `signal_id` round-trip: 1 / 2 fills carry `signal_id` — only the BUY
  fill, because the scheduled close is initiated by the runner's
  shutdown sequence not by a signal, so it carries no `signal_id`. The
  signal_lineage parquet keeps the original BUY signal_id pointed at
  `orders.parquet[0]`/`fills.parquet[0]`.

## 10. Signal flow

- Wall-clock replay configuration:
  `--start-delay-seconds 180 --interval-seconds 60 --max-signals 25
  --min-confidence 0.55 --side buy --ttl-seconds 900`. Output:
  `generated_count=25`, `skipped_duplicates=0`, `written_count=25`,
  first ts_event `2026-05-21T07:29:34.326Z`, last ts_event
  `2026-05-21T07:53:34.326Z`.
- `SignalStorePollingSource` cursor start: `1779348322` (set at runner
  launch from `latest_ts_event_ns` of pre-replay rows).
- `SignalStorePollingSource` cursor end: end of run still inside
  `cursor_ns ≤ 1779350014326175448` (last replay row).
- 25 rows popped during the session (all replay rows surfaced into
  `BaselineNautilusStrategy.on_bar` and recorded in
  `signal_lineage.parquet`).
- 24 rows were popped but did not produce additional orders because
  `BaselineNautilusStrategy` does not stack longs while already long —
  the first signal opened the position and the strategy holds until
  the runner schedules the close at shutdown. This matches the v9
  paper_simulated bundle behaviour where 545 signals produced 545
  orders only because that strategy variant takes 1:1 exits per
  signal; the testnet baseline keeps a single open position by design.

## 11. Decision

This retro **does not** mutate `SourcePolicy`. It records what
happened. The follow-up `promotion_review` retro will use this session
retro as `--testnet-runbook-signoff-path` to gate the next decision.

Recommended next decision (informal, must still go through
`promotion_review` when actually opening a stage change):

- `hold @ testnet_canary` — clean session, no kill-switch, no
  exchange/data/WS errors, the one advisory alert is explained and
  the runbook §1.5 already covers the fix (size the replay window to
  outlast the run).

## 12. Observability validation

This session is the first **live** validation of the 2026-05-21
observability + Postgres stack. Until now both were verified only against
stale smoke-test series or static SQL queries.

| chain | status |
|---|---|
| `PrometheusTextfileWriter` → `data/observability/textfile/testnet-<run_id>.prom` | wrote one .prom file containing 13 `trader_canary_*` series with `{kind="testnet", run_id="20260521-072730Z-2e4d2146"}`; deleted on clean shutdown (writer.cleanup() called in `finally`). Directory was empty after run. |
| `.prom` → node_exporter | `curl :9100/metrics \| grep '^trader_canary_'` returned all 13 series during the session. |
| node_exporter → Prometheus | `query=trader_canary_heartbeat_timestamp_seconds` returned a vector with `instance=node_exporter:9100`, `job=node_exporter`, plus the new `kind` + `run_id` labels. |
| `logs/heartbeat.jsonl` → Promtail → Loki | Loki `{job="testnet_heartbeat", run_id="20260521-072730Z-2e4d2146"}` returned the active heartbeat stream within ~15 s of writes. |
| `logs/alerts.log` → Promtail → Loki | The `signal_lag_exceeded_threshold` advisory was visible in Loki under `job="testnet_alerts"` for the new run_id. |
| Loki run_id label values (7 d window) | All 22 historical run_ids preserved including the new one. |
| Grafana `canary-current` dashboard provisioning | uid `canary-current`, folder `trader`, 14 panels (6 stat + 4 timeseries + 2 logs + 2 row headers); panel datasource uids resolve to `prometheus` / `loki` correctly after the 2026-05-21 fix. |
| Grafana template var `run_id` (LogQL `{job=~"testnet_.+\|paper_.+"}`) | Returned the live run_id alongside the 21 historical ones in the default `Last 7 days` window. |
| Postgres (`trader-postgres`) | Stayed healthy throughout (`docker compose ps`); the canary did not exercise PG paths (bridge still on SQLite default) — only validated that the new container does not interfere with the live order flow. |
| External `infra/watchdog/watchdog.py` | 60 healthy ticks + 1 `run_completed` final tick; 0 `flatten_invoked`. `infra/watchdog/history.jsonl` append-only file picked up by `watchdog_history` Promtail job. |

The observability stack is therefore validated under live traffic as
of 2026-05-21. No code changes triggered by this run.

## 13. Follow-ups (not done in this retro)

These surfaced during the run; none are blocking:

- Wall-clock signal replay window must outlast the run window. For the
  next 6 h canary, generate ≥ 6 h worth of replay rows up front (the
  existing runbook §1.5 example of 480 signals @ 45 s already does
  this). For shorter smoke runs use the 25-row preset only with eyes
  open about the tail-end `signal_lag_exceeded_threshold` advisory.
- `daily_pnl` is anchored from `starting_balance=10000` despite the
  testnet faucet showing ~86775 USDT, so the 5 % kill-switch threshold
  is 500 USDT, not 5 % of the actual testnet wallet. Pre-existing
  behaviour, also observed in the 2026-05-20 6 h canary. Open a
  follow-up retro / ADR when the anchor policy needs revisiting.
- `RiskEngine: Cannot check MARKET order risk: no prices for
  BTCUSDT.BINANCE` — Nautilus skips the pre-trade VaR check because
  Binance Spot WS does not push quotes. Track upstream for a
  Spot-quote-from-depth synthesis, but not on critical path for
  testnet.
