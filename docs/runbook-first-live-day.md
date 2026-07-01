# First Live Day Runbook

- **Status**: Draft
- **Owner**: nishiki
- **Scope**: First Binance Spot live-canary day under ADR-013.
- **Decision state**: Draft only. This runbook does not authorize live trading,
  live credentials, or live orders.

Phase 6 remains closed until ADR-013 is Accepted, the 14-day testnet
continuity gate is proven, a live-canary promotion review is signed, this
runbook is Accepted, and the live startup guard passes.

## Preconditions

- ADR-013 status is Accepted after a human go/no-go review.
- `apps.ops.live_readiness` produced a saved JSON report with
  `readiness_gate_met=true`, `live_trading_allowed=false`, and
  `git.dirty=false`; its `project_status.sha256`, `live_risk_adr.sha256`, and
  `live_promotion_review.sha256` identify the project status, ADR, and live
  promotion review artifacts used at startup, and its `continuity_artifacts`
  list fingerprints every testnet bundle manifest used to prove continuity,
  including the manifest paths the startup guard must reread.
- `apps.strategies_nautilus.runners.live_startup_guard` passes against that
  saved readiness report at the same git commit and within the guard's default
  24 hour readiness-evidence freshness window; the startup guard report records
  the SHA-256 of the saved readiness report, live-risk ADR, and first-live-day
  runbook artifacts it consumed, and verifies every recorded continuity
  manifest path still hashes to the readiness report's recorded SHA-256.
- Starting capital is declared between 100 and 500 USDT.
- Market scope is explicitly Binance Spot only: `market_type=spot`,
  `margin_enabled=false`, and `max_leverage=1.0`.
- SourcePolicy is `dry_run=False` and `position_pct_multiplier <= 0.1`.
- The live promotion review artifact is the standard `promotion_review.py`
  JSON or Markdown form with exact source/model,
  `current_stage=testnet_canary`, `target_stage=live_canary`,
  `decision=promote`, `decision_allowed=yes`, non-empty `operator`, and no
  review or promotion gate blockers.
- The live credential env names are declared, but credential values are not
  written to disk.

## Preflight

1. Confirm `git status --short --branch` is clean and `git rev-parse HEAD`
   matches the commit recorded in the saved readiness evidence.
2. Confirm the saved readiness evidence has `generated_at_ns` and was generated
   within the last 24 hours unless the operator explicitly chose a wider
   `--max-readiness-report-age-seconds` window.
3. Confirm the startup guard report's `live_readiness_report.sha256`,
   `live_risk_adr.sha256`, and `first_live_day_runbook.sha256` identify the
   exact saved readiness report, ADR, and runbook artifacts supplied to
   startup.
4. Confirm the startup guard report's
   `live_readiness_report.expected_live_risk_adr_sha256` equals
   `live_risk_adr.sha256`.
5. Confirm the startup guard report has
   `live_readiness_report.continuity_artifact_problems=[]` and every saved
   readiness `continuity_artifacts[*].manifest_path` still exists with a local
   SHA-256 equal to its recorded `sha256`.
6. Confirm the live promotion review fields exactly match the intended
   `testnet_canary -> live_canary` transition; do not accept incidental stage
   mentions in rationale text as evidence.
7. Confirm the saved readiness report's `live_promotion_review.sha256` equals
   the SHA-256 of the live promotion review artifact supplied to the startup
   guard.
8. Confirm the live credential key-prefix audit plan: record only the API key
   prefix in runtime logs; never write the full API key or secret.
9. Confirm Binance Spot only: no margin, no futures, no leverage.
10. Confirm the operator has the exchange web UI open before startup.
11. Confirm a manual exchange fallback is available: if the runner or emergency
   tooling fails, manually cancel all open Spot orders and sell residual BTC to
   return the account to USDT/flat.

## Startup Guard

The future live runner must call the guard before loading credential values:

```bash
uv run python -m apps.strategies_nautilus.runners.live_startup_guard \
  --mode live \
  --kind live \
  --allow-live-credentials \
  --source freqai_linear_v1 \
  --model-version linear-mom-train20240105 \
  --policy-position-pct-multiplier 0.1 \
  --starting-capital-usdt 100 \
  --market-type spot \
  --max-leverage 1 \
  --max-readiness-report-age-seconds 86400 \
  --live-readiness-report-path docs/retros/<phase6-live-readiness>.json \
  --live-promotion-review-path docs/retros/<live-canary-promotion-review>.md \
  --first-live-day-runbook-path docs/runbook-first-live-day.md \
  --markdown
```

Any non-zero exit code refuses live startup.

## First-Hour Observation

- Watch the runner heartbeat at least every 5 minutes for the first hour.
- Verify `ws_connected=true`, open orders are expected, and open positions are
  consistent with the sidecar or live telemetry.
- Verify no `kill_switch_fired`, `exchange_error_burst`, `ws_disconnected`,
  `heartbeat_lost`, `restart_drift_detected`, or emergency flatten alerts.
- If any unexpected live order or position appears, stop the runner and use the
  manual exchange fallback.

## Emergency Flatten

Live-mode emergency flatten is not accepted yet. Until it is implemented and
tested, the required fallback is manual exchange fallback:

1. Stop the live runner so it cannot submit new orders.
2. Cancel all open Binance Spot orders for the live account.
3. Check residual BTC or other base-asset balances.
4. Market sell residual base assets back to USDT only if this is required to
   return to flat under the live-canary plan.
5. Save screenshots or exchange exports outside the repository.
6. Write a retro before any restart.

## Shutdown

- Stop after the first scheduled live-canary window or earlier on any alert.
- Confirm final open orders are zero.
- Confirm final live position state is flat or intentionally documented.
- Preserve logs and sidecars under `data/live/<run_id>/` once a live runner
  exists; `data/` remains gitignored.

## Post-Run Retro

The post-run retro must record:

- Source/model and SourcePolicy.
- Starting capital, ending capital, and realized PnL.
- Every order, fill, position transition, and signal lineage reference.
- Any manual intervention, restart, data gap, exchange error, or emergency
  flatten action.
- Whether live remains paused, continues at the same capital, or rolls back to
  testnet/paper.

This draft must be promoted to Accepted only after the operator reviews the
final live runner implementation and emergency fallback path.
