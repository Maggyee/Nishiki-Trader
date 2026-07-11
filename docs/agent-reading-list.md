# Agent Reading List

- **Status**: Active
- **Owner**: nishiki
- **Purpose**: Single source of truth for what Codex, Claude, and future agents must read before working.

Agents must read this file first. Then read the documents listed below according to the task.

---

## Always Read

Read these before any non-trivial work:

1. `docs/agent-operating-contract.md`
2. `docs/project-status.md`
3. `docs/decisions/001-tech-stack.md`
4. `docs/decisions/002-signal-bridge-protocol.md`

---

## Read When Relevant

| Task area | Read |
|---|---|
| Project status, next step, or handoff | `docs/project-status.md`, `git status --short --branch`, `git fetch origin`, `git pull --ff-only`, `git log --oneline --decorate -5` |
| Architecture, boundaries, or phase planning | `docs/agent-operating-contract.md`, `docs/decisions/001-tech-stack.md` |
| Signal bridge, ML output, FreqAI integration | `docs/decisions/002-signal-bridge-protocol.md`, `docs/decisions/005-signal-source-taxonomy.md`, `docs/decisions/006-gray-rollout-and-source-policies.md`, `docs/decisions/007-paper-trading-runtime.md` |
| Agent research, AgentAdvice, MCP tool boundaries, or TradingAgents-inspired configuration | `docs/decisions/009-agent-advice-audit.md`, `apps/agents/README.md`, `apps/mcp_server/README.md`, `docs/upstream-versions.md`, `docs/progress/tradingagents-reference-map.md` |
| Frontend or dashboard work | `docs/decisions/012-phase5-readonly-dashboard.md`, `apps/frontend/README.md` |
| Signal transport / message bus / Redis | `docs/decisions/010-redis-stream-signal-transport.md` (Draft, **not implemented**; only read when one of §2 triggers fires) |
| Bridge → Postgres auto-mirror, dashboard freshness, dual-write design | `docs/decisions/011-bridge-postgres-mirror.md` (Draft, **not implemented**; only read when one of §2 triggers fires) |
| Upstream source updates or dependency drift | `docs/upstream-versions.md` |
| Project skeleton or directory layout | `docs/decisions/003-project-skeleton.md` |
| Backtest result format or reports | `docs/decisions/004-backtest-result-format.md` |
| Adding or comparing a signal source | `docs/progress/phase-2-signal-source-baselines.md` — current demo / rule fingerprints to diff against |
| Cost-sensitive alpha review or new research candidate | `docs/retros/2026-07-10-cost-sensitive-alpha-blind-review.md`, `docs/progress/phase-2-signal-source-baselines.md`, `apps/ops/alpha_review.py` |
| Trend-regime hypothesis and opened 2025 blind result | `docs/progress/phase-2-trend-regime-hypothesis.md`, `docs/retros/2026-07-10-trend-regime-2025-blind-review.md`, `apps/strategies_freqtrade/research/trend_regime_signals.py` |
| Market-regime diagnosis or next alpha hypothesis | `docs/retros/2026-07-10-market-regime-failure-attribution.md`, `notebooks/market_regime_failure_attribution.py` |
| Closed pullback-regime candidate and preserved 2026 holdouts | `docs/progress/phase-2-pullback-regime-hypothesis.md`, `docs/retros/2026-07-10-pullback-regime-development-rejection.md`, `apps/strategies_freqtrade/research/pullback_regime_signals.py`, `apps/ops/alpha_review.py` |
| Diverse-strategy tournament result | `docs/progress/phase-2-diverse-strategy-tournament.md`, `docs/retros/2026-07-10-diverse-strategy-tournament-development.md`, `apps/strategies_freqtrade/research/diverse_strategy_signals.py`, `apps/ops/strategy_tournament.py` |
| Multi-asset rotation study | `docs/progress/phase-2-multi-asset-rotation-study.md`, `docs/retros/2026-07-10-multi-asset-rotation-development-review.md`, `apps/strategies_freqtrade/research/multi_asset_rotation_signals.py`, `apps/ops/multi_asset_review.py`, `apps/ops/strategy_tournament.py` |
| Flow and funding-positioning study | `docs/progress/phase-2-flow-positioning-study.md`, `docs/retros/2026-07-10-flow-positioning-development-review.md`, `apps/strategies_freqtrade/research/flow_positioning_signals.py`, `apps/ops/backfill_funding.py`, `apps/ops/feature_audit.py`, `apps/ops/multi_asset_review.py` |
| Independent alt portfolio study | `docs/progress/phase-2-independent-alt-portfolio-study.md`, `docs/retros/2026-07-10-independent-alt-portfolio-development-review.md`, `apps/strategies_freqtrade/research/alt_portfolio_signals.py`, `apps/ops/daily_archive_audit.py`, `apps/ops/catalog_audit.py`, `apps/ops/multi_asset_review.py` |
| Cumulative alpha research stop rule | `docs/progress/phase-2-research-candidate-registry.json`, `docs/retros/2026-07-10-research-program-screening-review.md`, `apps/ops/research_program_review.py` |
| Research Protocol v2 independent mechanisms | `docs/progress/phase-2-research-protocol-v2.md`, `docs/progress/phase-2-research-protocol-v2.json`, `docs/progress/phase-2-research-v2-data-sources.json`, `apps/ops/research_protocol_v2.py`, `apps/ops/research_v2_snapshot.py`, `apps/strategies_freqtrade/research/independent_mechanism_signals.py` |
| Detailed historical progress | Relevant file under `docs/progress/` only when current status links it or history is needed |
| Paper trading, risk rules, testnet, or live trading | `docs/decisions/007-paper-trading-runtime.md`; `docs/decisions/008-phase3-risk-runbook.md` (Draft, gates Phase 3 / testnet) |
| Testnet continuity or next live-readiness stage | `docs/progress/phase-3-testnet-canary-evidence.md`, `docs/progress/phase-3-testnet-continuity-plan.md`, `docs/runbook-first-testnet-canary.md`, `docs/decisions/008-phase3-risk-runbook.md`, `docs/decisions/013-phase6-live-risk-gate.md`, `apps/ops/live_readiness.py`, `apps/strategies_nautilus/runners/live_startup_guard.py` |
| Phase 6, live-risk gate, or small-money live trading | `docs/decisions/013-phase6-live-risk-gate.md`, `docs/runbook-first-live-day.md`, `docs/decisions/001-tech-stack.md`, `docs/decisions/007-paper-trading-runtime.md`, `docs/decisions/008-phase3-risk-runbook.md`, `docs/progress/phase-3-testnet-continuity-plan.md`, `docs/progress/phase-3-testnet-canary-evidence.md`, `apps/ops/live_readiness.py`, `apps/strategies_nautilus/runners/live_startup_guard.py` |
| Operations, restart, emergency handling | `docs/runbook.md`; ADR-008 §6.6 first canary procedure: `docs/runbook-first-testnet-canary.md` + `docs/templates/testnet-canary-session-retro.md` |
| Project skeleton, directory ownership, dev environment | `README.md`, `apps/README.md`, `infra/README.md` |
| Recent project context | Latest file under `docs/retros/` |

---

## Update Rule

When a new ADR, runbook, status file, or phase document becomes required context for agents, update this file instead of expanding `AGENTS.md` or `CLAUDE.md`.

`AGENTS.md` and `CLAUDE.md` are stable entrypoints. This file is the expandable reading index.

## Status File Size Rule

`docs/project-status.md` must stay short enough to read at every task start. Do not use it as a changelog.

- Record only current state, active focus, blockers, next steps, latest verification, and short milestone summaries in `docs/project-status.md`.
- Move long completed-work lists, implementation narratives, and historical verification snapshots into `docs/progress/`.
- Keep durable architecture decisions in `docs/decisions/`.
- When a status update would add more history than current guidance, replace old detail with a summary and add or update a `docs/progress/` archive.
