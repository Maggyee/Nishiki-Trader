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

---

## Current Focus

Phase 0/1: turn the documented architecture into a minimal, testable research/backtest loop.

Immediate focus:

1. Add ADR-003 for project skeleton and Phase 0 directory ownership.
2. Implement `SignalEvent v1` model and validation in `apps/bridge`.
3. Add local Phase 1 signal storage using SQLite or JSONL.
4. Add tests for valid, expired, duplicate, and unauthorized signals.
5. Add a minimal CLI for writing, validating, and replaying signals.

---

## Next Steps

1. Create `docs/decisions/003-project-skeleton.md`.
2. Define `apps/bridge` package layout for `SignalEvent v1`.
3. Implement signal schema, validator, and serialization helpers.
4. Add pytest coverage mirroring ADR-002 testing standards.
5. Decide whether Phase 1 storage starts with SQLite, JSONL, or both.

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
