# Agent Instructions

Before changing anything in this repository, read `docs/agent-reading-list.md` first.

Hard rules:

- Do not modify `freqtrade/` or `nautilus_trader/` upstream source unless the user explicitly asks for it.
- Project-owned code belongs under `apps/`, `infra/`, `docs/`, `notebooks/`, or `data/`.
- When creating a new project-owned directory, add a `README.md` explaining its purpose, current phase, boundaries, and next implementation entrypoint.
- NautilusTrader is the only execution engine.
- Freqtrade/FreqAI may only produce research signals.
- LLM agents must never enter the live order path.
- The `SignalEvent v1` protocol is the only allowed bridge from research signals into NautilusTrader.

When finishing a task, report:

- Files changed.
- Whether upstream code was touched.
- How the work was verified.
- Whether the change affects the live trading path.
- Whether `docs/project-status.md` was updated, and if not, why.

Commit rule:

- After implementing code or documentation changes, create a git commit unless the user explicitly says not to.
- Update `docs/project-status.md` before committing when the task changes current progress, next steps, blockers, or phase status.
- Use a concise, descriptive commit message that explains the intent of the change.
- Do not include ignored data, secrets, local databases, or upstream source checkouts in commits.
