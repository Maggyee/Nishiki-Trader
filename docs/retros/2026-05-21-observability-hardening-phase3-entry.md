# Observability hardening — Phase 3 entry

- **Date**: 2026-05-21 (UTC)
- **Phase**: 3 entry
- **Owner**: nishiki
- **Status**: Implemented + smoke-verified
- **Type**: infra retro

## Scope

This hardens the Phase 3 entry observability stack before the next 6 h
testnet canary. The goal is not a new `SourcePolicy` decision; it is to make
the next canary's observation and alerting evidence more reliable.

## Changes

- `LiveTelemetryReader` now accepts an injected cumulative
  `exchange_error_counter`.
- `NautilusLogErrorCounter` tails the operator-owned Nautilus stdout/stderr
  log files and counts newly appended `ERROR` / `CRITICAL` lines, giving
  `exchange_error_count` a real non-invasive runtime source.
- `infra.watchdog.watchdog` still writes overwrite-style `state.json`, and
  now also appends every tick to `infra/watchdog/history.jsonl`.
- Promtail scrapes `infra/watchdog/history.jsonl` as `job=watchdog_history`.
- Prometheus loads `infra/prometheus/alert_rules.yml` with alerts for
  heartbeat stale, WS disconnected, exchange/runtime error burst, and stale
  heartbeat while a position is open.
- Textfile collector writes now chmod `.prom` files to `0644`; this is required
  because node_exporter runs as a non-root user.

## Smoke

Synthetic smoke used `run_id=smoke-hardening` for textfile metrics and
`run_id=smoke-watchdog` for watchdog history.

- Prometheus `/api/v1/rules` loaded all 4 new alert rules with `health=ok`.
- node_exporter exposed `trader_canary_info{run_id="smoke-hardening"}` and
  `node_textfile_scrape_error=0` after the `.prom` file mode fix.
- Loki `query_range` for `{job="watchdog_history", run_id="smoke-watchdog"}`
  returned both `healthy` and deliberately triggered `heartbeat_stale` ticks.

The synthetic `.prom` file was removed after verification so it cannot keep
firing canary alerts.

## Verification

```text
UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q
-> 471 passed, 7 skipped

UV_CACHE_DIR=/tmp/uv-cache uv run ruff check apps tests docs infra
-> all checks passed
```

The 7 skips are Postgres store tests gated on a reachable local
`trader-postgres`; they are outside this observability hardening path.

## Next

Run one short no-trade observability smoke if the launcher template changes
again, then run the next 6 h testnet canary to validate the full
trading + observation + alerting + replay evidence path.
