# Phase 5 Dashboard and Passive Phase 6 History

- **Status**: Historical progress archive
- **Last updated**: 2026-07-10
- **Scope**: Completed Phase 4/5 read-only dashboard work and passive Phase 6
  readiness/startup evidence hardening that was previously too detailed for
  `docs/project-status.md`.
- **Current source of truth**: `docs/project-status.md` for current status,
  blockers, focus, and latest verification.
- **Boundary**: Historical record only. This file does not authorize live
  trading, mutate `SourcePolicy`, write `SignalEvent`, load credentials, start
  Nautilus, or call exchange APIs.

## Why This Exists

`docs/project-status.md` must stay short enough for every agent to read at
task start. By July 2026 it had accumulated a long changelog of dashboard,
AgentAdvice, observability, and passive Phase 6 validation work. This archive
keeps those details available without making the status file the historical
ledger.

Use the existing Phase 3 archives for detailed testnet evidence:

- `docs/progress/phase-3-testnet-canary-evidence.md`
- `docs/progress/phase-3-testnet-continuity-plan.md`

Use `docs/retros/` for individual dated reviews and bundle evidence.

## Phase 5 Read-Only Dashboard

Phase 5 opened on 2026-06-04 with ADR-012 and a read-only Next.js operations
console under `apps/frontend`. The frontend reads `dashboard.snapshot.v1`
server-side from `data/frontend/dashboard-snapshot.json` or
`TRADER_DASHBOARD_SNAPSHOT`. It has no API routes, browser-side mutations,
runner triggers, order controls, exchange access, or credential path.

Implemented operator visibility includes:

- Operational posture and live gate status.
- Strict continuity and Phase 6 blocker summaries.
- Guardrail counts and order-path boundary flags.
- AgentAdvice rows from the local advice store.
- Runtime health and Prometheus textfile observability summaries.
- Passive paper/testnet bundle summaries.
- Signal, rejection, freshness, and source/model evidence summaries.
- Grafana source/model drill-down links.
- Snapshot freshness state with configurable warning/stale thresholds.
- Snapshot source/input audit and degraded-input visibility.
- English and Simplified Chinese UI chrome selected by URL query.

Representative verification from the Phase 5 opening and console hardening:

- 2026-06-04 Phase 5 entry: frontend audit clean, typecheck clean, production
  build clean, dashboard snapshot smoke emitted `dashboard.snapshot.v1`, local
  dev server returned HTTP 200, full pytest reported 551 passed, and ruff was
  clean.
- 2026-06-06 operations-console upgrade and language switch: frontend
  typecheck/build/audit clean, Simplified Chinese content smoke passed, pytest
  reported 551 passed, ruff was clean, and `git diff --check` was clean.
- 2026-06-09 reference links: `tests/ops/test_dashboard_snapshot.py` passed,
  ruff was clean for the changed snapshot surface, frontend typecheck/build
  passed, full pytest reported 541 passed / 12 skipped, and a later npm audit
  returned 0 vulnerabilities.
- 2026-06-11 observability summaries: dashboard snapshot consumed passive
  Prometheus textfiles, frontend rendered runtime health rows, full pytest
  reported 556 passed, ruff was clean, frontend build/typecheck passed, npm
  audit returned 0 vulnerabilities, and local dev smoke returned HTTP 200.
- 2026-06-11 signal/rejection summaries: dashboard snapshot emitted 3003
  passive signal rows from attached paper/testnet bundles with 3003 accepted,
  0 skipped, and 0 true rejections; full pytest reported 552 passed / 12
  skipped, and ruff was clean.
- 2026-06-14 source/model freshness: passive paper/testnet report readers
  exposed first/last `signal_lineage.ts_event` bounds; dashboard snapshot and
  frontend rendered latest signal freshness; targeted tests reported 39
  passed, full pytest reported 552 passed / 12 skipped, ruff and frontend
  checks were clean.
- 2026-06-29 source/model Grafana drill-downs: dashboard links gained
  `var-source` and `var-model_version`, `signals-overview` gained a
  `model_version` template variable, dashboard snapshot tests passed, ruff was
  clean, and frontend typecheck/build/audit passed.
- 2026-06-29 snapshot freshness: `dashboard.snapshot.v1` emitted
  `snapshot_freshness` and later accepted configurable
  `--snapshot-warning-after-seconds` / `--snapshot-stale-after-seconds`;
  targeted tests, ruff, frontend typecheck/build/audit, smoke JSON, and
  `git diff --check` passed.

## Phase 4 AgentAdvice Inputs

Phase 4 AgentAdvice work created safe read-only inputs for the dashboard:

- `apps.agents.advice.AgentAdvice` defines `schema_version="agent.advice.v1"`
  records for journals, reviews, analysis, and candidate parameter notes.
- `apps.agents.store.AgentAdviceStore` persists advice under
  `data/agents/advice.db` with SQLite/WAL.
- `apps.agents.cli` can write JSON/JSONL, create journal rows, replay JSONL,
  and record human review decisions.
- MCP-facing wrappers expose only `query_agent_advice`,
  `write_agent_advice`, and `write_journal`.
- The deterministic review agent reads local evidence and writes/dry-runs
  `advice_type="project_review"` without LLM calls, exchange access,
  `SignalEvent` writes, or `SourcePolicy` mutation.

Representative verification:

- AgentAdvice audit store: `tests/agents` reported 27 passed; full pytest
  reported 520 passed / 12 skipped; ruff was clean.
- MCP wrappers: `tests/mcp_server` reported 7 passed; full pytest reported
  539 passed; ruff was clean.
- Review agent + dashboard snapshot surface: `tests/agents` plus
  `tests/ops/test_dashboard_snapshot.py` reported 39 passed; full pytest
  reported 551 passed; ruff was clean.
- Safe role profiles: `tests/agents` reported 42 passed; full pytest reported
  564 passed; ruff and import greps confirmed no runtime import of the
  ignored TradingAgents upstream reference.

## Passive Phase 6 Readiness and Startup Gates

Phase 6 remains closed. The passive tooling added in June 2026 is audit and
refusal evidence only:

- Draft ADR-013 (`docs/decisions/013-phase6-live-risk-gate.md`) defines the
  live-risk gate but is not accepted.
- `apps.ops.live_readiness` emits `phase6.live_readiness.v1` JSON/Markdown
  from project status, ADR-013 status, optional passive continuity bundles,
  optional live-canary promotion review evidence, declared capital, and market
  scope.
- `apps.strategies_nautilus.runners.live_startup_guard` emits
  `phase6.live_startup_guard.v1` JSON/Markdown and returns exit code 2 when a
  future live runner must refuse startup.
- `docs/runbook-first-live-day.md` exists as a Draft checklist only.
- `dashboard.snapshot.v1` can display saved readiness/startup guard artifacts
  as read-only Phase 6 Gates evidence and defaults missing artifacts to
  blocked.

The passive gates intentionally do not load credential values, build or start
Nautilus, connect to Binance, place orders, mutate `SourcePolicy`, write
`SignalEvent`, or authorize live trading.

Representative verification:

- 2026-06-29 `live_readiness`: targeted tests passed; blocked markdown smoke
  reported `readiness_gate_met=false` / `live_trading_allowed=false`; full
  `tests/ops` reported 14 passed / 5 skipped; ruff and `git diff --check`
  were clean.
- 2026-06-29 `live_startup_guard`: targeted tests over startup guard and
  readiness reported 13 passed; blocked current-repo smoke returned exit 2
  with Draft/missing-evidence blockers; ruff and `git diff --check` were
  clean.
- 2026-06-29 Phase 6 dashboard summaries: dashboard snapshot tests passed,
  ruff was clean, frontend typecheck/build/audit passed, smoke JSON reported
  `phase6.state=blocked`, both reports `missing`, and
  `authorizes_live_trading=false` / `places_orders=false`.

## July 2026 Passive Input Hardening

The latest dashboard/passive Phase 6 hardening pass focused on malformed local
artifact inputs and strict JSON output:

- Dashboard snapshot JSON output uses strict standard JSON and rejects
  non-standard `NaN` / `Infinity` values.
- Explicit `generated_at_ns` and snapshot freshness thresholds are validated
  before snapshot construction.
- Saved Phase 6 report artifacts with non-standard JSON constants or non-object
  top-level payloads degrade into blocked report summaries instead of
  crashing.
- Invalid UTF-8 project status, operator documents, promotion reviews, and
  Prometheus textfiles preserve fingerprints and produce structured blockers or
  degraded rows.
- Corrupt AgentAdvice SQLite input marks the dashboard as attention-state and
  leaves review queue counts unknown.
- Optional paper/testnet bundle loader failures now become invalid bundle rows
  with `review_blockers` instead of aborting snapshot generation.
- Readiness/startup numeric inputs reject or normalize non-finite values for
  capital, leverage, multiplier, continuity days, and freshness windows.
- Readiness/startup identity, boolean control fields, git evidence, credential
  env-name evidence, artifact SHA-256 fields, and generated timestamps are
  sanitized before being echoed into reports.
- Dashboard cross-report checks validate source/model matches, readiness
  artifact bytes, startup-consumed readiness report SHA, promotion-review SHA,
  project-status SHA, live-risk ADR SHA, continuity manifest bytes, operator
  document accepted states, internal check statuses, boundary flags, runtime
  identity, market scope, SourcePolicy bounds, and credential-boundary leaks.
- The frontend renders degraded AgentAdvice, observability, and passive bundle
  input visibility without adding write or control surfaces.

Final verification for that hardening sequence:

- `TMPDIR=/tmp UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/ops/test_live_readiness.py tests/strategies_nautilus/test_live_startup_guard.py tests/ops/test_dashboard_snapshot.py -q` -> 144 passed.
- `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check apps tests docs infra` -> clean.
- `npm --prefix apps/frontend run typecheck` -> clean.
- `npm --prefix apps/frontend run build` -> clean Next.js production build.
- `npm --prefix apps/frontend audit --audit-level=moderate` -> 0 vulnerabilities.

## What This Archive Does Not Prove

This archive does not change the current gate state:

- ADR-013 is still Draft.
- Strict testnet continuity is still 0/14.
- No live-canary promotion review exists.
- `docs/runbook-first-live-day.md` is still Draft.
- No live runner is authorized or wired.
- Agents and frontend still cannot enter the order path.
