# Project Status

- **Status file**: Active
- **Last updated**: 2026-05-14
- **Current phase**: Phase 0/1
- **Current objective**: Establish a stable project skeleton, agent operating rules, git workflow, and the first implementation boundary around `SignalEvent v1`.
- **Source of truth**: This file, git history, and ADRs under `docs/decisions/`.

This file answers: "Where is the project now, and what should the next agent do?"

Agents must read this file at the start of each non-trivial task and update it at the end whenever the task changes project progress, current focus, blockers, or next steps.

---

## Progress Sync Protocol

At task start:

1. Read `docs/agent-reading-list.md`.
2. Read this file.
3. Run `git status --short --branch`.
4. If the working tree is clean, run `git fetch origin` and fast-forward the current branch with `git pull --ff-only`.
5. If the working tree is not clean, do not pull; inspect the local changes first and ask before overwriting or rebasing anything.
6. Run `git log --oneline --decorate -5`.
7. Inspect only the files relevant to the task.

At task finish:

1. Update this file if the task changes progress, next steps, blockers, or phase status.
2. Commit code and documentation changes unless the user explicitly says not to.
3. Report the commit hash, verification, and whether upstream or live trading paths were touched.

Do not use this file as a detailed changelog. Use it for current project state and next action.

---

## Completed

- Cloned upstream `freqtrade` into `freqtrade/` as a local read-only source checkout.
- Cloned upstream `nautilus_trader` into `nautilus_trader/` as a local read-only source checkout.
- Added ADR-001 for technology stack, five hard rules, service limits, and explicit non-goals.
- Added ADR-002 for `SignalEvent v1`, the only allowed bridge from research signals into NautilusTrader.
- Added shared agent entrypoints: `AGENTS.md` and `CLAUDE.md`.
- Added `docs/agent-operating-contract.md` to define agent boundaries.
- Added `docs/agent-reading-list.md` as the expandable reading index for all agents.
- Added Phase 0 project skeleton under `apps/`, `infra/`, `docs/`, `notebooks/`, `data/`, and `tests/`.
- Added README files for project-owned directories created so far.
- Initialized the root git repository on `main`.
- Configured `origin` as `git@github.com:Maggyee/Nishiki-Trader.git`.
- Pushed the initial project framework to GitHub.
- Added `docs/upstream-versions.md` to record pinned upstream checkout commits.
- Added ADR-003 for Phase 0/1 project skeleton, `apps/bridge` package layout, SQLite-only Phase 1 persistence, and test mirror conventions.

---

## Current Focus

Phase 0/1: turn the documented architecture into a minimal, testable research/backtest loop.

Immediate focus:

1. Implement `SignalEvent v1` Pydantic model in `apps/bridge/signal_event.py` (ADR-002 §3, ADR-003 §2.2).
2. Implement `apps/bridge/time_utils.py` for ms / μs → ns conversion (ADR-002 §7).
3. Implement `apps/bridge/validators.py` for missing / expired / unauthorized / duplicate rejection (ADR-002 §4.1).
4. Implement `apps/bridge/store.py` over SQLite at `data/bridge/signals.db` with WAL + `signals` table (ADR-002 §5, ADR-003 §2.3).
5. Implement `apps/bridge/cli.py` for `bridge write|validate|replay` (ADR-003 §2.2).

---

## Next Steps

1. Land `apps/bridge/signal_event.py` + `time_utils.py` + `validators.py` with pytest coverage of the 8 cases in ADR-002 §7.
2. Land `apps/bridge/store.py` with SQLite WAL + dedupe by `signal_id` + status transitions.
3. Land `apps/bridge/cli.py` (`argparse`, no click/typer) for write / validate / replay.
4. Add a minimal `apps/strategies_nautilus/` consumer that reads `SignalEvent` from SQLite without calling any trading API.
5. Confirm Phase 0/1 "graduation" criteria in ADR-003 §2.7 are all met, then update this file for Phase 2 entry.

---

## Blocked / Deferred

- No live trading.
- No real exchange API keys in the repository.
- No Redis until cross-process signal transport is required.
- No Postgres/TimescaleDB/pgvector until schemas stabilize.
- No frontend implementation until backtest and risk result schemas exist.
- No n8n workflows until Phase 3/4.
- No autonomous Agent trading. Agents may only research, review, summarize, and suggest.
- No edits to `freqtrade/` or `nautilus_trader/` unless explicitly requested.

---

## Recent Git Baseline

- `2f9ec32 chore: initialize trader project framework`

Agents should run `git log --oneline --decorate -5` for the latest commits instead of assuming this section is exhaustive.

---

## Definition Of Current Success

The project is on track when a new agent can:

- Read `AGENTS.md` or `CLAUDE.md`.
- Follow `docs/agent-reading-list.md`.
- Understand current progress from this file.
- Sync from `origin` safely before editing.
- Avoid upstream edits by default.
- Make a scoped Phase 0/1 change.
- Update this file if project state changed.
- Commit the change with a clear message.
