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
| Signal bridge, ML output, FreqAI integration | `docs/decisions/002-signal-bridge-protocol.md` |
| Upstream source updates or dependency drift | `docs/upstream-versions.md` |
| Project skeleton or directory layout | Future `docs/decisions/003-project-skeleton.md` |
| Backtest result format or reports | Future `docs/decisions/004-backtest-result-format.md` |
| Risk rules, testnet, or live trading | Future `docs/decisions/005-risk-and-emergency-rules.md` |
| Operations, restart, emergency handling | `docs/runbook.md` |
| Project skeleton, directory ownership, dev environment | `README.md`, `apps/README.md`, `infra/README.md` |
| Recent project context | Latest file under `docs/retros/` |

---

## Update Rule

When a new ADR, runbook, status file, or phase document becomes required context for agents, update this file instead of expanding `AGENTS.md` or `CLAUDE.md`.

`AGENTS.md` and `CLAUDE.md` are stable entrypoints. This file is the expandable reading index.
