# Phase 0/1 To Phase 2 Entry Progress Archive

- **Status**: Historical archive
- **Archived from**: `docs/project-status.md`
- **Archive date**: 2026-05-15
- **Scope**: Detailed progress from project skeleton through the first Phase 2 Nautilus backtest runner.

This file preserves implementation detail that no longer belongs in the always-read status file. `docs/project-status.md` remains the source of truth for current focus, blockers, and next steps.

## Historical Completed Detail

- Cloned upstream `freqtrade` into `freqtrade/` and upstream `nautilus_trader` into `nautilus_trader/` as local read-only source checkouts.
- Added ADR-001 for technology stack, five hard rules, service limits, and explicit non-goals.
- Added ADR-002 for `SignalEvent v1`, the only allowed bridge from research signals into NautilusTrader.
- Added shared agent entrypoints: `AGENTS.md` and `CLAUDE.md`.
- Added `docs/agent-operating-contract.md` to define agent boundaries.
- Added `docs/agent-reading-list.md` as the expandable reading index for all agents.
- Added Phase 0 project skeleton under `apps/`, `infra/`, `docs/`, `notebooks/`, `data/`, and `tests/`.
- Added README files for project-owned directories created so far.
- Initialized the root git repository on `main`, configured `origin` as `git@github.com:Maggyee/Nishiki-Trader.git`, and pushed the initial framework.
- Added `docs/upstream-versions.md` to record pinned upstream checkout commits.
- Added ADR-003 for Phase 0/1 project skeleton, `apps/bridge` package layout, SQLite-only Phase 1 persistence, and test mirror conventions.
- Implemented `apps/bridge/` Phase 1 package: `signal_event.py`, `time_utils.py`, `validators.py`, `store.py`, and `cli.py`.
- Added `pydantic>=2.6` to project dependencies in `pyproject.toml`.
- Added `tests/bridge/` covering ADR-002 §7: valid round-trip, required-field rejections, expired-by-ttl, unauthorized source/model version, duplicate `signal_id`, deterministic replay, AgentAdvice isolation, ns timestamp handling, and WAL pragma.
- Implemented `apps/strategies_nautilus/signal_consumer.py`: minimal placeholder consumer that reads pending rows from `SignalStore`, applies ADR-002 §4.1 checks, and marks rows `consumed | rejected | expired` without importing trading, exchange, or HTTP modules.
- Added `tests/strategies_nautilus/test_signal_consumer.py`.
- Added ADR-004 for the Phase 2 backtest result bundle under `data/backtests/<run_id>/`.
- Implemented `apps/strategies_nautilus/result_schema.py`: Pydantic `BacktestManifest` validator for ADR-004 `run_manifest.json`.
- Added `tests/strategies_nautilus/test_result_schema.py`.
- Implemented `apps/strategies_nautilus/baseline_strategy.py`: pure-Python decision layer for SignalEvent gating, side-to-intent mapping, and the 5%-day-loss kill-switch.
- Added `tests/strategies_nautilus/test_baseline_strategy.py`.
- Pinned `nautilus-trader==1.226.0` in `pyproject.toml` and aligned the local upstream checkout to tag `v1.226.0` (`38b912a8b0`).
- Implemented `apps/strategies_nautilus/baseline_nautilus_strategy.py`: real Nautilus `Strategy` wrapper around `BaselineSignalStrategy`, with order submission through `self.submit_order(...)`, signal-id order tags, Nautilus portfolio equity updates for the kill-switch, and per-signal lineage.
- Implemented `apps/strategies_nautilus/runners/backtest_runner.py`: in-memory `BacktestEngine` runner, deterministic bundle writer, ADR-004 manifest validation, Parquet sidecars, deterministic fill IDs, and `signal_id` propagation into orders/fills/positions/lineage.
- Added `tests/strategies_nautilus/test_backtest_reproducibility.py`: bundle smoke test, lineage coverage, report signal-id round-trip, bit-for-bit `fills.parquet` reproducibility, and Nautilus wrapper kill-switch update coverage.

## Phase 0/1 Graduation Checklist

| # | Criterion | Status |
|---|---|---|
| 1 | ADR-003 §2.1 directories present; Phase 2+ kept as empty skeletons where appropriate | Verified |
| 2 | All five files in `apps/bridge/` implemented; ADR-002 §7 tests pass | Verified |
| 3 | `bridge write / validate / replay` CLI works against `data/bridge/signals.db` | Verified via `tests/bridge/test_cli.py` |
| 4 | Minimal `apps/strategies_nautilus/` consumer reads `SignalEvent` from SQLite; no real trading API | Verified via `SignalConsumer` tests |
| 5 | `docs/project-status.md` records Phase 1 graduation and Phase 2 entry | Verified |

## Verification Snapshot

- 2026-05-15 after Phase 0/1 graduation: `uv run pytest` -> 155 passed; `ruff check apps tests` -> clean.
- 2026-05-15 after first Phase 2 backtest runner: `uv run pytest` -> 150 passed on home-frp; `ruff check apps tests` -> clean.

## Remaining From This Archive Point

- Replace the runner's inline `bars` input with `ParquetDataCatalog` loading from `data/catalog/`.
- Add a CLI/config entrypoint for `backtest_runner.py`.
- Defer SQLite -> Postgres / Redis Stream readiness decisions until backtest volume exposes the bottleneck.
