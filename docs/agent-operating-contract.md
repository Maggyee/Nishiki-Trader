# Agent Operating Contract

- **Status**: Active
- **Owner**: nishiki
- **Scope**: `/home/nishiki/projects/trader`
- **Purpose**: Give Codex, Claude, and future agents the same project boundaries before they edit or design anything.

This document is the shared operating contract for all agents working in this repository. If an agent has not read this file, it does not have enough context to make architecture or implementation decisions.

---

## 1. Project Mission

This project is a long-term personal quantitative trading system for crypto, initially focused on Binance and medium/low-frequency strategies.

System roles are fixed:

- `nautilus_trader`: the only execution, order, position, portfolio, and risk-management core.
- `freqtrade` / `FreqAI`: research, feature engineering, ML training, and signal generation.
- LLM agents: asynchronous research, review, reporting, replay analysis, and parameter suggestions.

The first goal is a repeatable research and backtesting loop. Live trading comes later and must be gated by testnet, hard risk controls, and review.

---

## 2. Required Reading Order

Every agent must read these files before making non-trivial changes:

1. `docs/agent-operating-contract.md`
2. `docs/project-status.md`
3. `docs/decisions/001-tech-stack.md`
4. `docs/decisions/002-signal-bridge-protocol.md`
5. The files directly relevant to the current task

For progress handoff, also run:

- `git status --short --branch`
- `git log --oneline --decorate -5`

If these documents conflict with a user request, follow the newest explicit user request, but state the conflict clearly before making risky changes.

---

## 3. Non-Negotiable Rules

- Do not modify `freqtrade/` or `nautilus_trader/` upstream source unless the user explicitly asks for it.
- Do not let LLM agents place trades, generate live orders, or call real trading APIs.
- Do not let `freqtrade` or `FreqAI` directly manage live orders or positions.
- Do not treat a research signal as an order.
- Do not bypass NautilusTrader strategy, portfolio, risk, or execution components.
- Do not add heavy infrastructure before the current phase needs it.
- Do not introduce new frameworks because they are fashionable.
- Every trading-related decision must be auditable, replayable, and explainable.
- The capital ladder (testnet → 100–500 USDT → 1,000 USDT → doubling only after 3 consecutive profitable months) and the 5% single-day-loss auto-kill switch defined in ADR-001 §2 Iron Rule 5 are binding at every phase that touches real money. Never bypass them.

---

## 4. Repository Ownership

| Path | Ownership | Rule |
|---|---|---|
| `freqtrade/` | Upstream source | Read-only by default |
| `nautilus_trader/` | Upstream source | Read-only by default |
| `apps/` | Project code | Main location for custom services and strategies |
| `infra/` | Project infrastructure | Docker, database, monitoring, n8n, deployment |
| `docs/` | Project documentation | ADRs, runbooks, operating contracts, retros |
| `notebooks/` | Research workspace | Experiments, analysis, manual investigation |
| `data/` | Local data | Historical data, cache, generated artifacts; normally gitignored |

If a required directory does not exist yet, create it only when the current task needs it.

---

## 5. Architecture Boundary

The only permitted trading-intent path is:

```text
freqtrade / FreqAI / research code
  -> SignalEvent v1
  -> NautilusTrader Strategy
  -> RiskEngine and hard risk controls
  -> ExecutionEngine
  -> Exchange adapter
```

`SignalEvent v1` is defined in `docs/decisions/002-signal-bridge-protocol.md`.

Signals may express direction, strength, confidence, source, model version, and expiry. Signals must not contain order type, order size, leverage, stop loss, take profit, or direct execution instructions.

LLM agents may write `AgentAdvice`, research notes, summaries, and candidate parameters. They may not write directly to the live signal stream unless a later ADR explicitly allows a controlled, reviewed workflow.

---

## 6. Development Phases

Agents must keep implementation aligned with the current phase. Do not jump phases without an explicit user request.

| Phase | Goal | Allowed emphasis |
|---|---|---|
| 0 | Project skeleton and contracts | Docs, directory layout, local config, minimal tooling |
| 1 | Data and backtesting loop | Binance data, Nautilus backtests, SQLite/files, CLI reports |
| 2 | ML signal layer | FreqAI or custom ML outputs converted to `SignalEvent v1` |
| 3 | Hard risk and testnet | Risk rules, Binance testnet/sandbox, restart/recovery checks |
| 4 | Agent research system | Async agents, reports, replay, advice database |
| 5 | Frontend and monitoring | Dashboard, logs, alerts, metrics |
| 6 | Small-money live trading | Strict capital ladder, rollback, emergency runbook |

Default current phase: Phase 0/1.

---

## 7. Implementation Defaults

Use conservative defaults unless the user says otherwise:

- Prefer Python for project-owned backend code.
- Prefer SQLite and local files during Phase 0/1.
- Add Postgres/TimescaleDB/pgvector only when the data model has stabilized.
- Add Redis only when cross-process signal transport is necessary.
- Add frontend only after backtest and risk-result schemas are stable.
- Keep services few and observable.
- Use NautilusTrader extension points instead of editing NautilusTrader source.
- Use Freqtrade/FreqAI extension points instead of editing Freqtrade source.

---

## 8. Testing and Verification

Any change touching trading logic, signals, data, or risk must include a verification path.

Minimum expectations:

- Contract/schema changes need validation tests or documented examples.
- Signal handling must reject invalid, expired, duplicate, or unauthorized signals.
- Risk logic must test block/reduce/allow decisions.
- Backtests must be reproducible from the same inputs.
- Agent outputs must be prevented from entering the live order path.

If tests cannot be run, say why and describe the remaining risk.

---

## 9. Definition of Done

Every agent should close work with:

- What changed.
- Which files changed.
- Whether `freqtrade/` or `nautilus_trader/` was touched.
- How the work was verified.
- Whether the live trading path is affected.
- Any follow-up ADR or runbook that should be created.
- Whether `docs/project-status.md` was updated, and if not, why progress state did not change.
- The git commit created for the change, unless the user explicitly asked not to commit.

For review tasks, findings come first and should focus on bugs, behavioral risk, missing tests, and architecture violations.

Commit discipline:

- After implementing code or documentation changes, commit them with a concise message describing the intent.
- Update `docs/project-status.md` before committing when the task changes current phase, completed work, blockers, or next steps.
- Do not commit generated data, secrets, local databases, logs, virtual environments, or upstream source checkouts.
- If verification fails, either fix the issue before committing or state the failure clearly in the final report.

---

## 10. Escalation Rules

Stop and ask the user before:

- Editing upstream source.
- Adding a new long-running service.
- Introducing a new database, message bus, framework, or cloud dependency.
- Changing the `SignalEvent v1` contract.
- Allowing any agent-generated output to affect live trading behavior.
- Moving from research/backtest/testnet to real-money trading.

When in doubt, preserve the boundary: research can suggest, NautilusTrader decides, risk controls gate, execution is audited.
