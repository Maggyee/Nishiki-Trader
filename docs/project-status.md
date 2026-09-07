# Project Status

- **Status file**: Active
- **Last updated**: 2026-09-07
- **Current phase**: Phase 5 entry — read-only monitoring; live trading still blocked.
- **Current objective**: Repair evidence and monitoring reliability before further research.
- **Source of truth**: Runtime status under `data/`; immutable research results and ADRs under `docs/`.

## Current Focus

The operator authorized the ordered reliability repairs from the 2026-09-07
project review. Batch 1 isolates Postgres integration tests and makes portfolio
input failures explicit. Batch 2 corrects collector qualification and runtime
state ownership. Batch 3 refreshes portfolio diagnostics and current guidance.

Batch 2 is deployed: all ten collectors use runtime-only status;
v40/v42/v46/v48 now count distinct dates with fresh observations, not invocations.
Strict collectors can recover hash-verified retained BTC captures without granting
qualification to failed historical attempts. Deployment pins the existing ten cron
entries to a clean pushed revision; schedules and research identities are unchanged.
All six strict collectors passed a real collection after deployment. Four v2
collectors start prospective counters without adopting legacy invocation totals.
Provider smoke checks exposed an old Cboe closure outside the factor window and
a missing June monthly-archive day; the follow-up limits gap checks to the
current factor window and recovers exact missing dates via verified daily files.

Batch 3 removes inferred leverage and zero-filled missing signal days, adds a
fail-closed ten-candidate read-only dashboard panel, and appends meta-analysis v2.
V2 separates 116 current PnL-opened identities from the legacy 108-identity null;
it reuses immutable v1 numbers explicitly, without claiming a numerical rerun.

## Milestones

- SignalEvent v1 bridge, Nautilus backtests, paper/testnet risk and audit paths exist.
- AgentAdvice and MCP wrappers are implemented; the review agent is deterministic.
- Phase 5 read-only frontend exists. No browser mutation or order controls.
- Protocols through v53 are recorded. Ten legacy candidates remain held at
  `paper_shadow`, `dry_run=True`; no policy changes are authorized by this repair.
- Gates v2/v2.1 protocols v49–v53 have 12 identities and zero survivors.
- The previous `freqai_linear_v1 / linear-mom-train20240105` policy remains
  `demote @ paper_simulated`, multiplier 0.1. Its testnet campaign is archived.

## Next Steps

1. Finish the follow-up deployment smoke check and retain its evidence summary.
2. Use current collector status and immutable attempt journals when reviewing
   forward evidence; never count run invocations as qualified days.
3. Review portfolio evidence against appropriate benchmarks and costs before
   considering a new research protocol or a separate promotion decision.

## Blocked / Deferred

- No live trading. `stop_before_testnet_resume` remains in force.
- Strict testnet continuity remains `current_qualified_streak_days=0/14`.
- ADR-013 and the first-live-day runbook remain Draft; no live runner is wired.
- Existing missing BTC intervals and failed collection attempts remain audit
  evidence. This repair cannot retroactively qualify them.
- The 2026-09..2027-01 future blind stays sealed; no future-blind PnL evaluation.
- Closed research identities may not be reopened or retuned. The external-index
  relief family remains saturated. New work requires a frozen independent identity.
- V12 remains a forward-data candidate with no recurring schedule authorized.
- No Redis/default Postgres migration, new Agent orchestration, or live-path changes.
- Full portfolio return/drawdown/leverage evaluation remains unavailable until
  verified Nautilus fills and account equity are attached for already-opened
  historical windows. Signals and policy multipliers cannot substitute for them.
- Historical BTC benchmark CSV is absent in this checkout; meta-analysis v2 is
  a registry-context refresh only. V1 remains unchanged.
- LLM agents never enter the order path. NautilusTrader is the only execution
  engine; `SignalEvent v1` is the only research-to-execution bridge.

## Latest Verification

- Pre-repair review: 672 targeted tests passed, one local-data-dependent monitor
  test failed. Registry check and Ruff passed.
- Batch 1: 1,631 offline tests passed; 12 Postgres integration tests are opt-in.
  Targeted isolation/monitor tests: 15 passed and 12 skipped without a test DSN.
- CI template is retained in `infra/ci/`; GitHub denied workflow creation because
  the current OAuth credential lacks `workflow` scope. Online CI is not enabled.
- Batch 2: 1,638 offline tests passed; 12 Postgres tests deselected. Historical
  BTC capture reconstruction found no hourly gaps for the six strict collectors.
  Six strict collectors passed real collection from pinned revision `f8c997a`.
- Batch 3: 1,649 offline tests passed, 12 Postgres tests deselected; Ruff and
  registry checks passed. Frontend typecheck and production build passed;
  dependency audit found three transitive vulnerabilities, fixed within existing
  dependency ranges; audit now reports zero. Final deployment smoke is next.

## References

- [Shadow collector runtime and deployment](../infra/research-shadow/README.md).
- [Research rules](decisions/014-research-program-v2.md) and [warnings](research-program-warnings.md).
- [Research registry](progress/research-mechanism-family-registry.json).
- [Historical meta-analysis v1](progress/research-program-meta-analysis-v1.md).
- [Current meta-analysis context v2](progress/research-program-meta-analysis-v2.md).
- [Archived testnet continuity](progress/phase-3-testnet-continuity-plan.md).
- [Full prior status archive](progress/project-status-archive-2026-09-07.md).
