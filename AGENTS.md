# AGENTS.md

Single entry point for every coding agent (Codex, Claude, others). Read this
file and `docs/project-status.md`, then only the files your task touches.
Research tasks also read `docs/research/README.md` and `docs/research/warnings.md`.

## Mission and roles

Personal crypto quant system (Binance, medium/low frequency). Roles are fixed
by ADR-001:

- **NautilusTrader** — the only execution, order, position, portfolio and risk engine.
- **freqtrade / FreqAI / research code** — produce signals only.
- **LLM agents** — research, review, reports and `AgentAdvice`. Never in the order path.

The only permitted trading-intent path:

```text
research code -> SignalEvent v1 (ADR-002) -> Nautilus Strategy
  -> RiskEngine + hard risk controls -> ExecutionEngine -> exchange adapter
```

Signals carry direction, strength, confidence, source, model version and TTL.
They never carry order type, size, leverage, stops or execution instructions.

## Hard rules

1. Do not edit upstream `freqtrade/` or `nautilus_trader/` unless explicitly asked.
2. Agents never place trades, call trading APIs, bypass Nautilus risk controls,
   or turn signals into orders.
3. Real money follows the capital ladder (ADR-001 Iron Rule 5) and ADR-015:
   daily loss limit min(25 USDT, 5% of qualified day-open equity), 250 USDT
   peak-loss ceiling. Never bypass them.
4. No optimization before alpha is proven (Iron Rule 1). No new service,
   database, bus or framework before its phase (ADR-001 §6).
5. Research follows ADR-014 (Gates v2) and `docs/research/warnings.md` (W1–W10).
6. Every trading decision must be auditable and replayable.

## Keep the repo lean

The 2026-10-17 slim-down removed ~140k lines of versioned research copies and
open-ended verification work. Do not grow it back:

- Extend existing modules; do not copy file sets per protocol or version
  (`research_v{n}_*.py`, `*_v27` fixtures).
- Verification must serve a concrete item in project-status **Next Steps**.
  Do not build verifiers of verifiers or proofs nobody asked for.
- Do not add a progress document per increment. Rewrite
  `docs/project-status.md` in place (under ~80 lines); history lives in
  `git log` and `docs/history.md`.
- Anything removed is in tag `archive/pre-slim-2026-10-17`. Read single files
  with `git show archive/pre-slim-2026-10-17:<path>`; do not restore wholesale.

## Stop and ask before

- editing upstream source;
- adding a long-running service, database, message bus, framework or cloud dependency;
- changing the `SignalEvent v1` contract;
- letting agent output affect trading behavior;
- any step toward real money;
- opening a new research protocol or a verification track not in **Next Steps**.

## Repository map

| Path | Purpose |
|---|---|
| `apps/bridge/` | `SignalEvent v1`, SQLite/Postgres signal store, validators |
| `apps/strategies_nautilus/` | baseline strategy, signal consumer, backtest/paper/testnet runners, emergency flatten, live startup guard, promotion review |
| `apps/strategies_freqtrade/` | freqtrade `user_data`; new research signal exporters go here |
| `apps/agents/`, `apps/mcp_server/` | AgentAdvice store, review agent, MCP tools |
| `apps/ops/` | data backfill, catalog/alpha audits, live readiness, dashboard snapshot, Postgres sync |
| `apps/frontend/` | Next.js read-only dashboard |
| `infra/` | observability stack, Postgres init, testnet watchdog, CI template |
| `docs/` | ADRs (`decisions/`), runbooks, SourcePolicy retros (`retros/`), research conclusions (`research/`), status |
| `data/` | local data and evidence (gitignored) |
| `tests/` | mirrors `apps/` |

## Phases

| Phase | Goal | State |
|---|---|---|
| 0 | Skeleton and contracts | done |
| 1 | Data and backtesting loop | done |
| 2 | ML / research signal layer | no strategy has shown alpha |
| 3 | Hard risk and testnet | runtime built; canary paused, strict streak 0/14 |
| 4 | Agent research system | AgentAdvice store and review agent built |
| 5 | Frontend and monitoring | read-only dashboard and observability stack (current) |
| 6 | Small-money live trading | blocked (ADR-013 Draft) |

Do not jump phases without an explicit user request.

## Workflow

- **Start**: `git status --short --branch`. If clean, `git fetch origin` and
  `git pull --ff-only`. If dirty, inspect the local changes and do not
  overwrite, stash, reset or rebase them without asking.
- **Verify**: `uv run pytest` and `uv run ruff check apps tests`. Frontend:
  `npm run typecheck` in `apps/frontend`. Changes to trading logic, signals,
  data or risk need tests (reject invalid/expired/duplicate signals; risk
  allow/reduce/block; reproducible backtests).
- **New project-owned directory**: add a `README.md` with purpose, current
  phase, boundaries and next entrypoint.
- **Status**: update `docs/project-status.md` when phase, focus, blockers or
  next steps change.
- **Commit** after code or documentation changes unless told not to. Use a
  concise message. Never commit ignored data, secrets, local databases or
  upstream checkouts.
- **Push** to `origin main` after committing unless told not to. This is a
  standing authorization from the sole maintainer, so that checkouts and agent
  sessions stay aligned. Push from the checkout that made the commit. Bring
  other checkouts up to date with `git fetch && git reset --hard origin/main`.
  Never force-push, never use `--no-verify`, and never push another branch
  without asking.

## Final report

State the files changed, whether upstream code was touched, how the work was
verified, whether the live trading path is affected, and whether
`docs/project-status.md` was updated (and if not, why).
