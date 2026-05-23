# Phase 3 Testnet Canary Evidence Summary

- **Status**: Active handoff summary
- **Last updated**: 2026-05-23 after canary
  `20260523-014615Z-9ef29d55`, aggregate verification, and continuity
  verification
- **Scope**: Phase 3 ADR-008 testnet canary evidence for `freqai_linear_v1 / linear-mom-train20240105`
- **Decision state**: Operational evidence only. This file does not mutate `SourcePolicy`.

## Current Position

`freqai_linear_v1 / linear-mom-train20240105` remains at
`hold @ testnet_canary` under the signed testnet policy from
`docs/retros/2026-05-19-freqai-linear-v1-promote-testnet-canary.md`:

- `dry_run=False`
- `position_pct_multiplier=0.1`
- `min_confidence_override=None`

Do not run `promotion_review.py hold @ testnet_canary` as a routine
ratification after each canary. The promotion-review tool is for actual
policy/stage decisions. Canary retros and this summary are the operational
record.

No live trading is authorized. The current evidence does not satisfy the
ADR-001 live-money ladder requirement of 14 consecutive testnet days without
manual intervention, and there is no live-risk ADR. The active continuity
plan is `docs/progress/phase-3-testnet-continuity-plan.md`.

## Evidence Bottom Line

The project now has six clean, sidecar-backed, strategy-registered 6 h
Binance Spot testnet canaries with real entry/exit order flow:

| run_id | date | heartbeats | alerts | sidecars | final state | realized PnL |
|---|---:|---:|---|---|---|---:|
| `20260519-120037Z-f1b06fd3` | 2026-05-19 | 720 | none | orders=2 / fills=2 / positions=1 / account=451 / lineage=3 | FLAT | +0.07496 USDT |
| `20260520-095350Z-6414ef0d` | 2026-05-20 | 720 | none | orders=2 / fills=2 / positions=1 / account=451 / lineage=490 | FLAT by sidecar | +0.02137 USDT |
| `20260521-102631Z-ea999625` | 2026-05-21 | 719 | none | orders=2 / fills=2 / positions=1 / account=451 / lineage=955 | FLAT | -0.18422 USDT |
| `20260522-030142Z-36922497` | 2026-05-22 | 719 | none | orders=2 / fills=2 / positions=1 / account=451 / lineage=477 | FLAT | -0.46798 USDT |
| `20260522-175232Z-83a9d87d` | 2026-05-22 | 719 | none | orders=2 / fills=2 / positions=1 / account=451 / lineage=477 | FLAT | -1.23226 USDT |
| `20260523-014615Z-9ef29d55` | 2026-05-23 | 719 | none | orders=2 / fills=2 / positions=1 / account=451 / lineage=477 | FLAT | -0.15345 USDT |

Aggregate for those six clean 6 h sidecar-backed sessions:

- 36.01 h of clean strategy-registered testnet runtime.
- 12 orders, 12 fills, 6 closed positions, all final FLAT by sidecar.
- 0 `logs/alerts.log` rows, 0 `ws_reconnect_count`, 0 `exchange_error_count`.
- External watchdog observed completion without emergency flatten.
- Net realized PnL across the six sessions: -1.94158 USDT.

Strict continuity review remains blocked by the 2026-05-20 manifest-backed
aborted run. With every manifest-backed bundle in the candidate window
included, the current continuity view is `qualified_day_count=4/5`,
`current_qualified_streak_days=3/14`; 2026-05-22 contributes 12.00 clean
hours and 2026-05-23 contributes 6.00 clean hours.

This is good operational evidence for the testnet path. It is not alpha
evidence: the fill count is tiny, Binance testnet fees are zero, and the
signals are wall-clock replays of already-reviewed historical rows.

## Session Ledger

| date | run_id | duration | result | evidence value |
|---|---|---:|---|---|
| 2026-05-18 | `20260518-150212Z-997bf080` | 6 h | Clean no-strategy stability soak. 720 heartbeats, no alerts, watchdog 714 healthy / 0 flatten. | ADR-008 section 6.6 prerequisite testnet stability evidence, not source policy evidence. |
| 2026-05-19 | `20260519-023115Z-e6aeb688` | 30 min | Clean strategy-registered smoke, 60 heartbeats, no alerts, 0 orders because no current SignalStore rows. | Proved the registered `BaselineNautilusStrategy` execution path without order flow. |
| 2026-05-19 | `20260519-033558Z-e653c3e5` | 6 h | Runner completed `max_duration`; real BUY/SELL round trip, PnL -0.02 USDT. Post-run watchdog bug produced false `heartbeat_lost` and repeated flatten calls after normal shutdown. | First real SignalEvent -> Nautilus -> Binance Spot testnet order-flow proof. Not counted as clean alert evidence. Watchdog behavior fixed afterward. |
| 2026-05-19 | `20260519-120037Z-f1b06fd3` | 6 h | Clean sidecar-backed canary with 2 orders / 2 fills / 1 position, no alerts, PnL +0.07496 USDT. | First parquet-backed promotion-grade operational bundle. |
| 2026-05-20 | `20260520-035223Z-20061290` | 216 s | Aborted after startup `ws_connected=false` implementation artifact; emergency flatten succeeded. | Invalidated clean canary. Fixed by suppressing pre-first-connect false readings. |
| 2026-05-20 | `20260520-040143Z-90c3c62b` | about 5 h 48 min | Aborted after repeated `signal_lag_exceeded_threshold` warnings at 60 s; emergency flatten succeeded. No manifest written. | Invalidated clean canary. Fixed by using a 120 s lag threshold for the 1m bar-driven canary. |
| 2026-05-20 | `20260520-095350Z-6414ef0d` | 6 h | Clean live-telemetry canary, no alerts, 2 orders / 2 fills / 1 position, sidecar final FLAT, PnL +0.02137 USDT. | Validated the startup WS and signal-lag fixes over a full window. |
| 2026-05-21 | `20260521-072730Z-2e4d2146` | 30 min | Real order flow and observability smoke. One benign warning-only `signal_lag_exceeded_threshold` because the short replay window ended before the run. PnL +0.28908 USDT. | Validated Prometheus / Loki / Grafana / node_exporter flow under live traffic; not counted as a fully clean no-alert canary. |
| 2026-05-21 | `20260521-102631Z-ea999625` | 6 h | Clean observability-backed canary, 719 heartbeats, no alerts, 2 orders / 2 fills / 1 position, final FLAT, PnL -0.18422 USDT. | Confirms trading + observation + alerting + watchdog over the full 6 h path. |
| 2026-05-22 | `20260522-030142Z-36922497` | 6 h | Clean control-machine canary, 719 heartbeats, no alerts, 2 orders / 2 fills / 1 position, final FLAT, PnL -0.46798 USDT. | Confirms the hardened foreground launch flow: no false start, no overlapping future replay rows, clean watchdog terminal state. |
| 2026-05-22 | `20260522-175232Z-83a9d87d` | 6 h | Clean evening control-machine canary, 719 heartbeats, no alerts, 2 orders / 2 fills / 1 position, final FLAT, PnL -1.23226 USDT. | Adds a second clean 6 h block on 2026-05-22; the day now has 12.00 clean hours under the continuity report. |
| 2026-05-23 | `20260523-014615Z-9ef29d55` | 6 h | Clean control-machine canary, 719 heartbeats, no alerts, 2 orders / 2 fills / 1 position, final FLAT, PnL -0.15345 USDT. | Advances the strict current continuity streak to 3/14 qualified days. |

There was also a one-heartbeat false start before
`20260521-102631Z-ea999625`: `data/testnet/20260521-102449Z-114b7c91/`.
It wrote no orders, fills, sidecars, or alerts. Cause: launching through a
one-shot shell with `nohup ... &` allowed the tool environment to clean up
the child process. `docs/runbook-first-testnet-canary.md` was hardened in
commit `0116b89` to require a long-lived foreground terminal/session and to
check for existing future wall-clock replay rows before writing another
stream.

## Known Caveats

- Testnet PnL is not strategy alpha. Fees are zero, sample size is tiny, and
  the signal stream is replayed historical `SignalEvent v1` data.
- Live telemetry `daily_pnl` is anchored from `starting_balance=10000`, while
  the Binance testnet faucet account has about 86775 USDT. The configured
  5% kill-switch remains tighter than the faucet account balance; this is
  acceptable for testnet but must be revisited before live money.
- `RiskEngine: Cannot check MARKET order risk: no prices for BTCUSDT.BINANCE`
  appears on entry/exit market orders. It is a known Binance Spot testnet
  quote-source limitation and has not mapped to an ADR-008 alert kind.
- `BinanceUserDataWebSocketClient: eventStreamTerminated` appears during
  scheduled teardown. It has matched clean-shutdown timing in every documented
  canary and is not treated as an alert.
- `exchange_error_count` remains 0 in current evidence. Treat any future
  non-zero value as investigation material, but note that fully surfacing this
  counter still depends on non-invasive upstream telemetry availability.

## Next Operating Step

Continue collecting testnet canary evidence with the hardened runbook:

1. Use a long-lived foreground terminal/session for the runner and watchdog.
2. Before writing new replay rows, check for existing future
   `metadata.wall_clock_replay` rows and avoid overlapping streams unless the
   overlap is intentional and recorded in the retro.
3. Treat the bundle (`run_manifest.json` plus sidecar parquet files) as the
   promotion source of truth; Grafana/Prometheus/Loki are runtime observation
   aids.
4. Before editing this evidence ledger, regenerate the clean aggregate table
   from clean bundle artifacts. For the continuity view, include every
   completed manifest-backed bundle in the candidate window, including
   blocked runs:

   ```bash
   UV_CACHE_DIR=/tmp/uv-cache uv run python -m \
     apps.strategies_nautilus.runners.report_testnet_bundle --markdown \
     data/testnet/20260519-120037Z-f1b06fd3 \
     data/testnet/20260520-095350Z-6414ef0d \
     data/testnet/20260521-102631Z-ea999625 \
     data/testnet/20260522-030142Z-36922497 \
     data/testnet/20260522-175232Z-83a9d87d \
     data/testnet/20260523-014615Z-9ef29d55
   ```

   ```bash
   UV_CACHE_DIR=/tmp/uv-cache uv run python -m \
     apps.strategies_nautilus.runners.report_testnet_bundle \
     --continuity \
     --markdown \
     --min-clean-hours-per-day 6 \
     --required-consecutive-days 14 \
     data/testnet/20260519-120037Z-f1b06fd3 \
     data/testnet/20260520-035223Z-20061290 \
     data/testnet/20260520-095350Z-6414ef0d \
     data/testnet/20260521-102631Z-ea999625 \
     data/testnet/20260522-030142Z-36922497 \
     data/testnet/20260522-175232Z-83a9d87d \
     data/testnet/20260523-014615Z-9ef29d55
   ```

5. Do not open a live-risk ADR or live promotion unless there is explicit user
   direction and enough continuous testnet evidence to satisfy the capital
   ladder gate.

Do not implement Redis Stream or automatic bridge -> Postgres mirroring unless
one of the trigger conditions in ADR-010 or ADR-011 actually fires.
