# Upstream Versions

- **Status**: Active
- **Owner**: nishiki
- **Purpose**: Record the upstream source checkouts used for local reference and integration testing.

The root repository does not commit upstream source trees. `freqtrade/`, `nautilus_trader/`, and `TradingAgents/` are local read-only checkouts, ignored by root git, and updated through a controlled review process.

## freqtrade

- Repository: `https://github.com/freqtrade/freqtrade`
- Local path: `freqtrade/`
- Branch at setup: `develop`
- Commit at setup: `764b32a0cf91cfe04ec53344a4d98e37206c77a3`
- Project role: research, FreqAI experiments, and signal generation reference

## nautilus_trader

- Repository: `https://github.com/nautechsystems/nautilus_trader`
- Local path: `nautilus_trader/` (read-only source reference, **not** installed from)
- Tag / commit: `v1.226.0` → `38b912a8b0fe14e4046773973ff46a3b798b1e3e` (detached HEAD)
- Previous checkout (history): `2a8953d4a87f75df8cecad07a50c4452f534528b` on `develop` (pre-Phase-2 reference snapshot)
- Project role: execution engine, backtesting, risk, portfolio, and exchange adapters
- Runtime install: PyPI wheel `nautilus-trader==1.226.0` pinned in `pyproject.toml`. The local checkout is for browsing source only; runtime imports resolve to the venv wheel.
- Pin policy: exact-version pin (`==`) is required by ADR-004 §2.4 — backtest reproducibility depends on identical `nautilus_version`. Bumping the pin must move the checkout to the matching tag and re-record both here in the same commit.

## TradingAgents

- Repository: `https://github.com/TauricResearch/TradingAgents`
- Local path: `TradingAgents/` (read-only source reference, **not** installed from)
- Branch at setup: `main`
- Commit at setup: `04f434e86db88e7707bf16db8ed7183f9764fe26`
- Version at setup: `0.2.5` from `pyproject.toml`
- License: Apache-2.0
- Project role: reference for future LLM-agent role decomposition, debate/review flow design, LLM provider configuration, CLI ergonomics, and research workflow ideas.
- Boundary: reference only. Do not install TradingAgents as a runtime dependency, do not copy its trader / portfolio-manager execution semantics into this project, and do not let any TradingAgents-inspired output write `SignalEvent`, mutate `SourcePolicy`, call exchange APIs, or enter the live order path. Any adapted agent output must stay within `AgentAdvice v1` unless a later ADR explicitly opens a reviewed `llm_*` signal experiment.

## Update Policy

Do not run `git pull` in upstream checkouts as an unreviewed routine task.

Use this flow:

1. Read upstream release notes or relevant changelog.
2. Fetch the upstream repository.
3. Check out the intended tag, branch, or commit.
4. Run the project regression checks that touch signals, backtests, and Nautilus strategy integration.
5. Update this file with the new commit and reason.
6. Commit the version record update in the root repository.

Production or testnet code should not track unpinned upstream moving targets.
