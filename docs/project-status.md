# Project Status

- **Last updated**: 2026-10-20
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

Daily rounds [2026-10](research/round-2026-10.md) and
[2026-10b](research/round-2026-10b.md) rejected all seven identities (v54–v59);
lower costs do not rescue them. On 2026-10-18 the operator chose intraday
research: minute data, hour-scale holds,
[ADR-018](decisions/018-intraday-research.md) (Draft).

## Next Steps

1. Operator: accept or amend ADR-018 (costs §2.4, minimum horizon §2.1).
2. Then propose the first intraday round (≤ 3 identities). Each protocol: freeze
   a contract in `docs/research/contracts/`, one mechanism module, cross-check,
   run with `apps/research/`. Lessons in both daily rounds.
3. Only when a candidate passes: resume the Phase 3 canary per
   [runbook](runbook-first-testnet-canary.md) for that identity. Generate a new
   testnet Ed25519 API key first; the old key pair was deleted on 2026-10-18.

## Blocked / Deferred

- Live trading: blocked. ADR-013 and the first-live-day runbook are Draft; strict streak remains 0/14.
- Testnet canary paused since 2026-07-29 (`freqai_linear_v1` demoted to `paper_simulated`).
- The ten Gates-v1 survivors are closed unvalidated: their 2026-09..2027-01 blind
  will not complete, and their forward data was deleted on 2026-10-18.
- Real-account testnet joint collection and the egress-guard chain are archived; do not resume without a strategy that needs them.
- Online CI not enabled: credential lacks `workflow` scope; template in `infra/ci/`.
- Redis transport (ADR-010) and automated Postgres mirror (ADR-011) remain Draft.

## Running on the host

- Nothing. Shadow crons, the systemd research collectors, their `/opt`,
  `/var/lib` and `/etc` deployments, and all local research data were removed
  on 2026-10-18. Only code survives, in tag `archive/pre-slim-2026-10-17`.

## Latest Verification

- 2026-10-20 intraday harness (Codex-written, reviewed): 1m klines, 5m metrics,
  parquet cache, bar-level replay with execution lag, per-settlement funding,
  day-unit null. Daily null p-values equal the old algorithm; a real 2025 BTC 1m
  fetch verified checksums, no missing minutes, cache 4.8 s → 0.14 s; null
  ~0.12 s/trial at 3 years × 10 assets. `uv run pytest` 800 passed, 12 skipped.
- 2026-10-18 Nautilus: spot sell = flat on CASH accounts, notional sizing
  (`--trade-notional`), learning simulation matching research holdings,
  paper-runner instrument-mismatch fix; all Codex-reviewed with regression tests.
- 2026-10-18 research round: `apps/research/` + Codex-written mechanism modules
  (cross-checked against an independent reference: identical weights);
  `uv run pytest` 684 passed, 12 skipped; results in `docs/research/results/`.
- 2026-10-18 slim-down (tracked files 1703 → 198): `uv run pytest` 684 passed,
  12 skipped (Postgres tests need `TRADER_TEST_POSTGRES_DSN`); `ruff check apps tests
  notebooks infra` clean; frontend `npm run typecheck` and `npm run build` pass.
- 2026-10-18 local cleanup and dashboard trim: see `git log` and [history](history.md).

## References

- Agents: [AGENTS.md](../AGENTS.md). Decisions: [ADR index](decisions/README.md).
- Research: [summary](research/README.md), [warnings](research/warnings.md),
  [backlog](research/backlog.md), [ADR-014](decisions/014-research-program-v2.md),
  [ADR-018](decisions/018-intraday-research.md).
- Risk and testnet: [ADR-008](decisions/008-phase3-risk-runbook.md),
  [ADR-015](decisions/015-portfolio-risk-policy.md),
  [canary evidence](progress/phase-3-testnet-canary-evidence.md),
  [runbook](runbook.md).
