# Claude Project Instructions

Start every task by reading `docs/agent-reading-list.md`.

This repository follows two accepted ADRs:

- ADR-001 defines the long-term technology boundaries and five hard rules.
- ADR-002 defines the `SignalEvent v1` bridge protocol.

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
