# Claude Project Instructions

Start every task by reading `docs/agent-reading-list.md`.

At task start, check `git status --short --branch`. If the working tree is clean, run `git fetch origin` and `git pull --ff-only` before editing. If it is dirty, inspect local changes first and do not overwrite them.

This repository follows these accepted ADRs:

- ADR-001 defines the long-term technology boundaries and five hard rules.
- ADR-002 defines the `SignalEvent v1` bridge protocol.
- ADR-003 defines the Phase 0/1 project skeleton, `apps/bridge` package layout, and SQLite-only Phase 1 persistence.

Do not edit upstream repositories unless explicitly instructed:

- `freqtrade/`
- `nautilus_trader/`

Use project-owned paths for new work:

- `apps/`
- `infra/`
- `docs/`
- `notebooks/`
- `data/`

When creating a new project-owned directory, add a `README.md` explaining its purpose, current phase, boundaries, and next implementation entrypoint.

Agents are research and development assistants. They must not place trades, bypass NautilusTrader risk controls, or turn signals into orders directly.

After implementing code or documentation changes, update `docs/project-status.md` if current progress, next steps, blockers, or phase status changed. Then create a git commit unless the user explicitly says not to. Use a concise, descriptive commit message, and never commit ignored data, secrets, local databases, or upstream source checkouts.

After committing, push to `origin` (default branch `main`) unless the user explicitly says not to. The sole maintainer needs `origin` kept in sync so multiple checkouts and agent sessions stay aligned; this standing authorization overrides the generic "ask before pushing" default. Push from the canonical checkout (home-frp); if a mirror checkout produced a parallel commit with a different SHA, align it with `git fetch && git reset --hard origin/main` after the push. Never force-push, never use `--no-verify`, never push a branch other than the one the user is working on without asking.
