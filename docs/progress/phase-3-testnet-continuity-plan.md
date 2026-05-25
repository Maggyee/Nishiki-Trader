# Phase 3 Testnet Continuity Plan

- **Status**: Active operating plan
- **Last updated**: 2026-05-25 after third canary `20260525-140958Z-7bd13f02`
- **Scope**: ADR-008 testnet continuity evidence for `freqai_linear_v1 / linear-mom-train20240105`
- **Decision state**: Planning and evidence tracking only. This file does not authorize live trading or mutate `SourcePolicy`.

## Current Position

The current clean-session evidence has twelve 6 h canaries at the 6 h/day
tracking threshold:

- 2026-05-19: `20260519-120037Z-f1b06fd3`
- 2026-05-20: `20260520-095350Z-6414ef0d`
- 2026-05-21: `20260521-102631Z-ea999625`
- 2026-05-22: `20260522-030142Z-36922497`
- 2026-05-22: `20260522-175232Z-83a9d87d`
- 2026-05-23: `20260523-014615Z-9ef29d55`
- 2026-05-23: `20260523-121618Z-ba5c4bfe`
- 2026-05-24: `20260524-005423Z-24c8c34d`
- 2026-05-24: `20260524-072049Z-a49496ed`
- 2026-05-25: `20260525-000508Z-af7de22d`
- 2026-05-25: `20260525-074853Z-592ff1f1`
- 2026-05-25: `20260525-140958Z-7bd13f02`

For continuity review, do not feed the tool only the clean runs. The input
must be the candidate continuity window: all completed `kind="testnet"`
bundle directories with `run_manifest.json` inside that window, including
blocked runs. With the current manifest-backed window from 2026-05-19 through
2026-05-25, the strict continuity report includes the 2026-05-20 aborted
bundle `20260520-035223Z-20061290` and shows
`current_qualified_streak_days=5/14`, `qualified_day_count=6/7`,
`ws_reconnects=1`, and `emergency_flatten_completed=1`. The 2026-05-22 day
contributes 12.00 clean hours and the 2026-05-23 day contributes 12.00 clean
hours; the 2026-05-24 day contributes 12.00 clean hours; the 2026-05-25 day
contributes 18.00 clean hours. The current blockers are:

```text
current_qualified_streak_days=5<required=14
emergency_flatten_completed=1
```

The 2026-05-20 no-manifest abort (`20260520-040143Z-90c3c62b`) and the
2026-05-21 no-manifest false start (`20260521-102449Z-114b7c91`) remain
manual ledger caveats because they cannot be parsed by the bundle reader.

This is operational readiness evidence for the testnet path. It is not alpha
evidence and not live authorization.

## Continuity Gate

Use the passive report reader as the source of truth before updating any
Phase 3 evidence ledger:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run python -m \
  apps.strategies_nautilus.runners.report_testnet_bundle \
  --continuity \
  --markdown \
  --min-clean-hours-per-day 6 \
  --required-consecutive-days 14 \
  data/testnet/<window-run-id-1> \
  data/testnet/<window-run-id-N>
```

For machine-readable review:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run python -m \
  apps.strategies_nautilus.runners.report_testnet_bundle \
  --continuity \
  --json \
  --min-clean-hours-per-day 6 \
  --required-consecutive-days 14 \
  data/testnet/<window-run-id-1> \
  data/testnet/<window-run-id-N>
```

A qualified day currently requires:

- A completed `kind="testnet"` bundle with `clean_for_retro=true`.
- At least `--min-clean-hours-per-day` clean elapsed runtime for that UTC
  calendar day.
- No blocked runs included for that day.
- No `logs/alerts.log` rows.
- No restart drift.
- No `kill_switch_fired` or `emergency_flatten_completed` alert.

The summary additionally enforces the ADR-008 continuity thresholds:

- `exchange_error_count < 1000` across the reviewed continuity window.
- `ws_reconnect_count < 50` across the reviewed continuity window.
- `restart_sequence <= 3`.
- `restart_drift_detected == 0`.
- `kill_switch_fired == 0`.
- `emergency_flatten_completed == 0`.

ADR-001/ADR-008 still require a live-risk decision before live money. The
daily PnL standard-deviation comparison against paper_simulated remains a
manual review item until a paper-vs-testnet continuity comparator exists.

## Operating Path

1. Continue the hardened 6 h/day control-machine canary routine from
   `docs/runbook-first-testnet-canary.md`.
2. After each completed run, generate the single-bundle report, write the
   retro, then regenerate the aggregate and continuity reports from bundle
   artifacts.
3. For the continuity command, include every completed testnet bundle with a
   manifest inside the candidate window. Keep no-manifest blocked or
   abandoned runs in the session ledger and review them manually; do not hide
   them from the retro.
4. When the current streak reaches 7 qualified days, decide whether to raise
   the tracking threshold to 12 h/day for the remaining window.
5. When the current streak reaches 14 qualified days, do not jump to live.
   Open a separate live-risk ADR/review that includes the continuity report,
   paper_simulated comparison, capital ladder sizing, and explicit go/no-go
   decision.

## Boundaries

- NautilusTrader remains the only execution engine.
- FreqAI remains a research signal producer only.
- LLM agents do not enter the order path.
- `SignalEvent v1 -> NautilusTrader Strategy -> RiskEngine` remains the only
  bridge into execution.
- `report_testnet_bundle --continuity` is passive: it reads completed bundles
  and never loads credentials, starts Nautilus, or talks to Binance.
