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

1. Operator decision after [round 2026-10](research/round-2026-10.md): all three
   identities rejected. Learning simulation of v54 (backtest + local paper) done.

## Next Steps

1. Next research protocol, if any: freeze a contract under
   `docs/research/contracts/` and run it with `apps/research/` (one module per
   mechanism). Options and lessons in [round 2026-10](research/round-2026-10.md).
2. Only when a candidate passes: resume the Phase 3 canary per
   [runbook](runbook-first-testnet-canary.md) for that identity. Generate a new
   testnet Ed25519 API key first; the old key pair was deleted on 2026-10-18.

## Blocked / Deferred

- Live trading: blocked. ADR-013 and the first-live-day runbook are Draft; strict streak remains 0/14.
- Testnet canary paused since 2026-07-29 (`freqai_linear_v1` demoted to `paper_simulated`).
- The ten Gates-v1 survivors are closed unvalidated: their 2026-09..2027-01 blind
  will not complete, and their forward data was deleted on 2026-10-18.
- Real-account testnet joint collection and the egress-guard chain are archived; do not resume without a strategy that needs them.
- Online CI not enabled: credential lacks `workflow` scope; template in `infra/ci/`.
- Known issue, operator decision: a SELL signal on a spot CASH account with no
  holdings halts a Nautilus backtest (pre-existing). Fixing it means treating
  sell as flat on spot, which also changes testnet behaviour.
- Redis transport (ADR-010) and automated Postgres mirror (ADR-011) remain Draft.

## Running on the host

- Nothing. Shadow crons, the systemd research collectors, their `/opt`,
  `/var/lib` and `/etc` deployments, and all local research data were removed
  on 2026-10-18. Only code survives, in tag `archive/pre-slim-2026-10-17`.

## Latest Verification

- 2026-10-18 notional sizing (`--trade-notional`): Codex review found three
  issues, all fixed with regression tests; `uv run pytest` 719 passed, 12 skipped.
- 2026-10-18 learning simulation: 10 Nautilus backtests and a BTC paper session
  match the research holdings; paper-runner instrument-mismatch bug fixed
  (regression test); `uv run pytest` 712 passed, 12 skipped.
- 2026-10-18 research round: `apps/research/` + Codex-written mechanism modules
  (cross-checked against an independent reference: identical weights);
  `uv run pytest` 684 passed, 12 skipped; results in `docs/research/results/`.
- 2026-10-18 slim-down (tracked files 1703 → 198): `uv run pytest` 684 passed,
  12 skipped (Postgres tests need `TRADER_TEST_POSTGRES_DSN`); `ruff check apps tests
  notebooks infra` clean; frontend `npm run typecheck` and `npm run build` pass.
- 2026-10-18 dashboard: Phase 6 panel now mirrors each report's own verdict instead of
  re-verifying it (~1.1k backend + ~2.6k test lines removed).
- 2026-10-18 local cleanup: removed ~15 GB of egress/joint evidence, research
  shadow data, `scratch/`, the testnet key pair and its env file; `data/` is
  now only `frontend/` and `observability/`.

## References

- Agents: [AGENTS.md](../AGENTS.md). Decisions: [ADR index](decisions/README.md).
- Research: [summary](research/README.md), [warnings](research/warnings.md),
  [backlog](research/backlog.md), [ADR-014](decisions/014-research-program-v2.md).
- Risk and testnet: [ADR-008](decisions/008-phase3-risk-runbook.md),
  [ADR-015](decisions/015-portfolio-risk-policy.md),
  [canary evidence](progress/phase-3-testnet-canary-evidence.md),
  [runbook](runbook.md).
