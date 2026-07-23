# ADR-012: Phase 5 Read-Only Dashboard Entry

- **Status**: Accepted
- **Date**: 2026-06-04
- **Owner**: nishiki
- **Scope**: Phase 5 entry frontend surface.
- **Depends on**: ADR-001, ADR-002, ADR-004, ADR-007, ADR-008, ADR-009.

## 1. Context

Phase 5 is defined as frontend and monitoring. The monitoring stack was moved
earlier to Phase 3 entry by ADR-001's 2026-05-21 amendment because testnet
canary heartbeat and alert data already existed. The remaining Phase 5 gap is a
project-owned frontend.

Phase 4 now has a stable read-only input contract for that frontend:
`dashboard.snapshot.v1`, emitted by `apps.ops.dashboard_snapshot`. The snapshot
summarizes project status, AgentAdvice rows, optional passive paper/testnet
bundle reports, and optional saved Phase 6 gate artifacts. It does not write
signals, policies, credentials, or orders.

## 2. Decision

Open Phase 5 entry with a Next.js dashboard shell under `apps/frontend`.

The first frontend consumes only `dashboard.snapshot.v1` from a local file:

```text
data/frontend/dashboard-snapshot.json
```

Operators generate the file with:

```bash
uv run python -m apps.ops.dashboard_snapshot > data/frontend/dashboard-snapshot.json
```

The frontend may render status, operational posture, operator checklist,
boundaries, AgentAdvice history, passive bundle summaries, passive textfile
observability summaries, optional Phase 6 live-readiness/startup-guard artifact
summaries, and source-of-truth neutral reference links, including source/model
Grafana drill-down links. The snapshot may include a freshness policy so the
frontend can show whether the loaded local snapshot is fresh, aging, or stale
without refreshing it automatically. If the file is absent, it renders a
fallback read-only state so build and local smoke checks remain deterministic.
`dashboard.snapshot.v1.generated_at_ns` is emitted only as a non-negative
integer nanosecond timestamp; malformed programmatic timestamps are rejected
before snapshot generation so JSON output remains strict standard JSON.
If `docs/project-status.md` exists but is not valid UTF-8, snapshot generation
records `project_status.decode_error`, leaves parsed status sections empty, and
treats the live gate as unknown/attention instead of crashing or treating
malformed operator-document bytes as proof that live trading is blocked.
If the AgentAdvice SQLite database, optional paper/testnet bundle reports, or
passive Prometheus textfiles are corrupt, the snapshot records degraded
read-only input state and reports operator attention; the frontend
first-viewport metrics include those degraded input counts instead of hiding
the issue or entering any mutation path.

Language selection is read-only URL state. The dashboard may render English or
Simplified Chinese UI chrome through `?lang=en` / `?lang=zh-CN`; this does not
write cookies, call API routes, or mutate operator state.

## 3. Boundary

Allowed:

- read `dashboard.snapshot.v1`;
- render AgentAdvice, status, bundle-summary, and monitoring-oriented panels;
- render passive Prometheus textfile summaries produced by existing runners;
- render passive summaries of saved `phase6.live_readiness.v1` and
  `phase6.live_startup_guard.v1` JSON artifacts, including promotion-review
  fingerprint evidence already present in those artifacts;
- render links to docs, evidence files, runbooks, and Grafana dashboards without
  treating the frontend as the source of truth;
- show snapshot age using the freshness thresholds declared by
  `dashboard.snapshot.v1`.
- show whether live/order-path boundary flags are closed.

Forbidden:

- order placement buttons or exchange API calls;
- writing `SignalEvent`, `SourcePolicy`, or AgentAdvice from the browser;
- triggering `promotion_review`, emergency flatten, or any runner from the
  frontend;
- generating Phase 6 readiness reports or startup-guard reports from the
  frontend or dashboard snapshot;
- treating frontend output as promotion, live-readiness, or live authorization
  evidence.

The source of truth remains unchanged:

- bundle `run_manifest.json` + sidecar parquet for ADR-004/ADR-007/ADR-008
  evidence;
- saved `phase6.live_readiness.v1` and `phase6.live_startup_guard.v1` JSON
  artifacts for Phase 6 blocker review;
- `docs/project-status.md` for current phase/focus;
- ADRs for durable decisions.

## 4. Implementation

Phase 5 entry implementation:

- `apps/frontend/package.json` locks a Next.js + Tailwind app.
- `apps/frontend/app/dashboardData.ts` loads the local snapshot server-side,
  including `ops_status`, parsed project-status sections, `observability`,
  `reference_links`, `operator_checklist`, optional `phase6` summaries, and an
  optional passive `research.v5.collector_status.v1` or v2 artifact. Version 2
  adds an explicit active/archived lifecycle; a valid archive is a healthy
  terminal operations state, not a retryable collector fault.
- `apps/frontend/app/page.tsx` renders the read-only operations dashboard:
  posture band, guardrail metrics, Phase 6 gate-artifact status, runtime
  health, Protocol v5 collector run/date and four-stream status, passive
  storage/conflict and deployment-identity evidence, evidence matrix, bundle
  ledger, AgentAdvice queue, operator checklist, snapshot source audit,
  watchlist, verification, reference links, boundary ledger, Phase 6
  promotion-review fingerprint evidence summaries, and an English / Simplified
  Chinese URL language switch.
- `apps/frontend/app/globals.css` defines the compact dashboard surface.

The first implementation deliberately has no API routes and no client-side
mutation paths.

## 5. Verification Standard

The implementation must prove:

1. `npm audit --audit-level=moderate` reports no vulnerabilities.
2. `npm run typecheck` passes from a clean `.next` state.
3. `npm run build` passes.
4. A local dev server returns the dashboard over HTTP.
5. Backend Python tests and ruff remain clean.

**Decided.** Phase 5 starts with a read-only dashboard shell. The trading path
remains `SignalEvent v1 -> NautilusTrader Strategy -> RiskEngine`; the frontend
does not enter that path.

## 6. Protocol v5 archive amendment (2026-07-23)

The dashboard keeps backward-compatible v1 reads and accepts
`research.v5.collector_status.v2`. An `archived` artifact must prove that the
timer is inactive/disabled with no next trigger, the service is inactive, the
deployment identity is clean and matching, and immutable storage has no
conflicts or comparison markers. The last incomplete batch remains visible as
history but is not an operational blocker. A valid archive displays its time,
reason and `retain_archived_evidence` action without contributing to the
collector issue count. Any false archive claim fails closed as a breach.
