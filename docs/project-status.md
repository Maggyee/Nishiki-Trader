# Project Status

- **Status file**: Active
- **Last updated**: 2026-05-15
- **Current phase**: Phase 1 → Phase 2 transition (graduation complete per ADR-003 §2.7)
- **Current objective**: Phase 0/1 has graduated. Next focus is Phase 2 entry: stabilize the bridge with a real NautilusTrader-driven consumer in backtest mode and lock down the backtest result format (ADR-004 draft).
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
- Implemented `apps/bridge/` Phase 1 package: `signal_event.py` (Pydantic v1 schema, `extra="forbid"`, frozen), `time_utils.py` (ms/μs/ns conversion + ns-range guard), `validators.py` (schema / authorization / freshness checks), `store.py` (SQLite WAL store at `data/bridge/signals.db`, dedupe by `signal_id`, status transitions, deterministic replay), `cli.py` (`bridge write|validate|replay` via `argparse`).
- Added `pydantic>=2.6` to project dependencies in `pyproject.toml`.
- Added `tests/bridge/` covering ADR-002 §7: valid round-trip, all required-field rejections, expired-by-ttl, unauthorized source / model_version, duplicate `signal_id`, deterministic replay, AgentAdvice cannot enter `signals` table, ts_event ns boundaries (ms/μs/ns), WAL pragma. 51 tests pass; `ruff` clean on bridge code.
- Implemented `apps/strategies_nautilus/signal_consumer.py`: minimal `SignalConsumer` placeholder that reads `pending` rows from `SignalStore`, runs ADR-002 §4.1 strategy-side checks (schema / venue / authorization / freshness / `min_confidence`), and marks rows `consumed | rejected | expired`. No `nautilus_trader` / `freqtrade` / HTTP imports — Phase 1 requires only a placeholder.
- Added `tests/strategies_nautilus/test_signal_consumer.py` (17 cases): accept path, venue mismatch, unauthorized source / model, expired, low-confidence boundary, store-status transitions, idempotency on re-run, and static asserts that the consumer file does not reference any trading or HTTP module.

### Phase 0/1 graduation checklist (ADR-003 §2.7)

| # | Criterion | Status |
|---|---|---|
| 1 | §2.1 directories present; Phase 2+ kept as empty skeletons (README + `__init__.py` only) | ✅ verified |
| 2 | All five files in `apps/bridge/` (§2.2) implemented; ADR-002 §7 tests pass | ✅ 51 / 51 |
| 3 | `bridge write / validate / replay` CLI works against `data/bridge/signals.db` (SQLite WAL) | ✅ via `tests/bridge/test_cli.py` |
| 4 | Minimal `apps/strategies_nautilus/` consumer reads `SignalEvent` from SQLite; no real trading API | ✅ `SignalConsumer` + 17 tests |
| 5 | `docs/project-status.md` records Phase 1 graduation + Phase 2 entry | ✅ this update |

Aggregate test result on 2026-05-15: `uv run pytest` → 68 passed in 0.14s; `ruff check apps tests` → clean.

---

## Current Focus

Phase 2 entry — switch the consumer from "decision logging placeholder" to a real NautilusTrader backtest path while preserving the SignalEvent → Strategy → RiskEngine boundary from ADR-002.

Immediate focus:

1. Draft **ADR-004** (NautilusTrader backtest result format) before adding real `nautilus_trader` imports.
2. Add `apps/strategies_nautilus/baseline_strategy.py` + `runners/backtest_runner.py` (per `strategies_nautilus/README.md` Phase 1 plan) on top of the existing placeholder consumer.
3. Build a small reproducible backtest harness that consumes `data/bridge/signals.db`, calls into NautilusTrader Strategy / RiskEngine, and writes a backtest result file matching ADR-004.

---

## Next Steps

1. Write ADR-004 — NautilusTrader backtest result format (fields, file layout, persistence path under `data/`).
2. Implement `baseline_strategy.py` (translates `SignalEvent.side` into Nautilus order intents through the real RiskEngine; no real exchange API).
3. Implement `runners/backtest_runner.py` (load Parquet K-lines from `data/catalog/`, feed signals from `SignalStore.replay`, emit ADR-004 result).
4. Add `tests/strategies_nautilus/` coverage for the real Strategy + 5%-day-loss risk rule (ADR-002 §4.2).
5. Decide Phase 2 SQLite → Postgres / Redis Stream readiness (defer to ADR-006 / ADR-007 once backtest volume exposes the bottleneck).

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
