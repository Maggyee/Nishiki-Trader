# Architecture Decision Records

ADRs are permanent records. Do not rewrite an accepted ADR. Supersede it with a
new one.

| ADR | Topic | Status |
|---|---|---|
| [001](001-tech-stack.md) | Tech stack, five iron rules, capital ladder, service timeline | Accepted |
| [002](002-signal-bridge-protocol.md) | `SignalEvent v1` bridge protocol | Accepted |
| [003](003-project-skeleton.md) | Phase 0/1 skeleton, SQLite-only Phase 1 | Accepted |
| [004](004-backtest-result-format.md) | Backtest result bundle format | Accepted |
| [005](005-signal-source-taxonomy.md) | Signal source taxonomy and naming | Accepted |
| [006](006-gray-rollout-and-source-policies.md) | `SourcePolicy` gray rollout and dry-run | Accepted |
| [007](007-paper-trading-runtime.md) | Paper runtime and policy promotion | Accepted |
| [008](008-phase3-risk-runbook.md) | Phase 3 risk, testnet runtime, runbook | Draft (normative) |
| [009](009-agent-advice-audit.md) | AgentAdvice audit store, LLM isolation | Accepted |
| [010](010-redis-stream-signal-transport.md) | Redis Stream signal transport | Draft, not implemented |
| [011](011-bridge-postgres-mirror.md) | Bridge → Postgres mirror | Draft, not implemented |
| [012](012-phase5-readonly-dashboard.md) | Phase 5 read-only dashboard | Accepted |
| [013](013-phase6-live-risk-gate.md) | Phase 6 live-risk gate | Draft |
| [014](014-research-program-v2.md) | Research program v2, Gates v2 | Accepted |
| [015](015-portfolio-risk-policy.md) | Unified portfolio risk policy | Accepted (planning) |
| [016](016-testnet-observation-admission.md) | Testnet observation admission | Accepted (read-only); implementation archived |
| [017](017-testnet-engineering-session.md) | Testnet engineering session | Accepted; one-shot scope consumed 2026-09-11 |
| [018](018-intraday-research.md) | Intraday research protocols (minute data, hour-scale holds) | Accepted |
| [019](019-beta-allocation.md) | Beta allocation track (market exposure with risk control) | Accepted |

## Paths that moved on 2026-10-17

Older ADRs cite paths that no longer exist on `main`:

| Cited path | Now |
|---|---|
| `docs/agent-operating-contract.md`, `docs/agent-reading-list.md` | [`AGENTS.md`](../../AGENTS.md) |
| `docs/research-program-warnings.md` | [`docs/research/warnings.md`](../research/warnings.md) |
| `docs/research-mechanism-backlog.md` | [`docs/research/backlog.md`](../research/backlog.md) |
| `docs/progress/research-mechanism-family-registry.json` | [`docs/research/family-registry.json`](../research/family-registry.json) |
| other `docs/progress/*`, non-`freqai-linear-v1` `docs/retros/*`, `apps/ops/research_*`, `apps/*/portfolio_*`, `infra/egress-guard/` | tag `archive/pre-slim-2026-10-17` |
