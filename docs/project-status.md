# Project Status

- **Last updated**: 2026-10-18
- **Current phase**: Phase 5 entry — read-only monitoring. Live trading still blocked.
- **Current objective**: Find one strategy with benchmark-relative alpha. Until
  one exists, engineering only maintains the core path (bridge → Nautilus →
  risk → execution) and the read-only dashboard.

Rewrite this file in place and keep it under ~80 lines. History is in
`git log` and [history](history.md); removed material is in tag
`archive/pre-slim-2026-10-17`.

## Current Focus

No strategy has alpha. Ten Gates-v1 survivors are statistically consistent
with luck and express one trade (long BTC in calm regimes); all five Gates-v2
protocols (v49–v53) were rejected. Their shadow collection was stopped on
2026-10-18. See [research summary](research/README.md).

Immediate focus:

1. Choose the next research direction with the operator before writing code.

## Next Steps

1. New research: one pre-registered protocol at a time under ADR-014 Gates v2,
   drawn from untried entries in [backlog](research/backlog.md) (B4 two-sided
   regime, B5 event/calendar, B6 OI/taker flow, B7 vol-targeted overlay).
   Reuse the archived factor panel (W10) before adding providers.
2. Only when a candidate passes: resume the Phase 3 canary per
   [runbook](runbook-first-testnet-canary.md) for that identity. Generate a new
   testnet Ed25519 API key first; the old key pair was deleted on 2026-10-18.

## Blocked / Deferred

- Live trading: blocked. ADR-013 and the first-live-day runbook are Draft; strict streak remains 0/14.
- Testnet canary paused since 2026-07-29 (`freqai_linear_v1` demoted to `paper_simulated`).
- The ten Gates-v1 survivors are closed unvalidated: their 2026-09..2027-01 blind
  will not complete. Partial forward data (to 2026-10-17) stays in `data/research-*`;
  keep it sealed if any of those protocols is ever revived.
- Real-account testnet joint collection and the egress-guard chain are archived; do not resume without a strategy that needs them.
- Online CI not enabled: credential lacks `workflow` scope; template in `infra/ci/`.
- Redis transport (ADR-010) and automated Postgres mirror (ADR-011) remain Draft.

## Running on the host

- Nothing from this repo is scheduled. The ten shadow crons were removed on
  2026-10-18; the removed lines are in `data/collector-deployments/crontab-removed-2026-10-18.txt`.
- Root-owned leftovers, all disabled: systemd `nishiki-research-v2/v5-collector`
  units, `/opt/nishiki-trader*`, `/var/lib/nishiki-trader`, `/etc/nishiki-trader`.

## Latest Verification

- 2026-10-18 slim-down (tracked files 1703 → 198): `uv run pytest` 684 passed,
  12 skipped (Postgres tests need `TRADER_TEST_POSTGRES_DSN`); `ruff check apps tests
  notebooks infra` clean; frontend `npm run typecheck` and `npm run build` pass.
- 2026-10-18 dashboard: Phase 6 panel now mirrors each report's own verdict instead of
  re-verifying it (~1.1k backend + ~2.6k test lines removed).
- 2026-10-18 local cleanup: removed ~15 GB of untracked egress/joint/testnet-observation
  evidence, `scratch/` and the repo-root key pair; `data/` is now 444 MB.

## References

- Agents: [AGENTS.md](../AGENTS.md). Decisions: [ADR index](decisions/README.md).
- Research: [summary](research/README.md), [warnings](research/warnings.md),
  [backlog](research/backlog.md), [ADR-014](decisions/014-research-program-v2.md).
- Risk and testnet: [ADR-008](decisions/008-phase3-risk-runbook.md),
  [ADR-015](decisions/015-portfolio-risk-policy.md),
  [canary evidence](progress/phase-3-testnet-canary-evidence.md),
  [runbook](runbook.md).
