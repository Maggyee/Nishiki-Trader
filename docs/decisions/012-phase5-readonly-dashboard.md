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
summarizes project status, AgentAdvice rows, and optional passive paper/testnet
bundle reports. It does not write signals, policies, credentials, or orders.

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
boundaries, AgentAdvice history, and passive bundle summaries. If the file is
absent, it renders a fallback read-only state so build and local smoke checks
remain deterministic.

Language selection is read-only URL state. The dashboard may render English or
Simplified Chinese UI chrome through `?lang=en` / `?lang=zh-CN`; this does not
write cookies, call API routes, or mutate operator state.

## 3. Boundary

Allowed:

- read `dashboard.snapshot.v1`;
- render AgentAdvice, status, bundle-summary, and monitoring-oriented panels;
- show whether live/order-path boundary flags are closed.

Forbidden:

- order placement buttons or exchange API calls;
- writing `SignalEvent`, `SourcePolicy`, or AgentAdvice from the browser;
- triggering `promotion_review`, emergency flatten, or any runner from the
  frontend;
- treating frontend output as promotion or live-readiness evidence.

The source of truth remains unchanged:

- bundle `run_manifest.json` + sidecar parquet for ADR-004/ADR-007/ADR-008
  evidence;
- `docs/project-status.md` for current phase/focus;
- ADRs for durable decisions.

## 4. Implementation

Phase 5 entry implementation:

- `apps/frontend/package.json` locks a Next.js + Tailwind app.
- `apps/frontend/app/dashboardData.ts` loads the local snapshot server-side,
  including `ops_status`, parsed project-status sections, and
  `operator_checklist`.
- `apps/frontend/app/page.tsx` renders the read-only operations dashboard:
  posture band, guardrail metrics, evidence matrix, bundle ledger, AgentAdvice
  queue, operator checklist, watchlist, verification, boundary ledger, and an
  English / Simplified Chinese URL language switch.
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
