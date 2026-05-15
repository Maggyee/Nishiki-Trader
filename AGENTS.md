# Agent Instructions

Before changing anything in this repository, read `docs/agent-reading-list.md` first.

At task start, check `git status --short --branch`. If the working tree is clean, run `git fetch origin` and `git pull --ff-only` before editing. If it is dirty, inspect local changes first and do not overwrite them.

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

Commit and push rule:

- After implementing code or documentation changes, create a git commit unless the user explicitly says not to.
- Update `docs/project-status.md` before committing when the task changes current progress, next steps, blockers, or phase status.
- Use a concise, descriptive commit message that explains the intent of the change.
- Do not include ignored data, secrets, local databases, or upstream source checkouts in commits.
- After committing, push to `origin` (default branch `main`) unless the user explicitly says not to. The sole maintainer needs `origin` kept in sync so multiple checkouts and agent sessions stay aligned; this standing authorization overrides the generic "ask before pushing" default.
- Pushes go from the canonical checkout only (the home machine / home-frp copy). If a mirror checkout has a parallel commit with a different SHA, align it after push with `git fetch && git reset --hard origin/main`.
- Never force-push, never push with `--no-verify`, never push to a branch other than the user's current working branch without asking.
