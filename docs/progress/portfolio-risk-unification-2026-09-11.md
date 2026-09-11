# Portfolio risk unification — 2026-09-11

The operator delegated the risk decision. [ADR-015](../decisions/015-portfolio-risk-policy.md)
now replaces the former 50 USDT daily planning amount with
**min(25 USDT, 5% of qualified UTC day-open equity)**. Both observed and projected
loss checks are inclusive. The separate fixed 250 USDT peak-loss ceiling remains.

## Implemented result

- `portfolio_risk_policy.py` holds the policy ID, constants and validated Decimal
  calculation. Current plan defaults are revision 3; historical v1/v2 remain
  reproducible without changing their committed contracts.
- Portfolio preflight applies the effective limit to observed losses and the
  entire batch's pending/proposed entry-loss bound. Deterministic selection keeps
  checking the accumulated set and final batch.
- Synthetic Nautilus risk latching uses the same calculation. The new limits
  change the configuration fingerprint, so old-policy checkpoints fail restore.
- Downtime review retains the independent 5% diagnostic and evaluates
  `planning_daily` against the current effective limit. It reports the policy ID,
  absolute cap and `checkpoint_policy_qualified=false`; observations cannot
  qualify the checkpoint's strategy or authorize restart.

The six original evidence chains were revalidated to generate the v3 plan.
No new research identity, allocation approval or performance claim follows.
No future blind data was opened. The old 500/50%/50 reports stay historical.

## Account acceptance next

The selected September 11 testnet archive and initial observation are present
locally. They remain consistency references, not independent identity/baseline
evidence. Replaying the selected archive verifies its four full-account
observations, not a fresh connection or new business events.

The next required inputs are an independent testnet UID reference, all-asset
baseline with timestamp, and known faucet/reset history. The operator was asked
for availability and local paths, without requesting secret values. `/sapi`
permission evidence remains unavailable on testnet; the strict collector is not
bypassed. Supported permission evidence needs an explicit qualification design.

Once these exist, qualify full-asset native mapping, real business events,
downtime coverage and fresh-process adapter recovery. Existing observations have
zero business events. This change does not create testnet orders to manufacture
that evidence, and does not activate any execution runner.

## Verification

Focused policy/plan/preflight/simulation/downtime acceptance: **177 passed**.
Tests cover decreasing/increasing day-open equity, inclusive boundaries,
pending and selected-batch fee headroom, invalid percentages, legacy replay,
rebound/restart/midnight latch persistence and old-policy checkpoint refusal.
Full offline regression: **2,284 passed**, 12 Postgres integration tests
deselected because no dedicated integration DSN was supplied. Ruff, the research
family registry and whitespace checks pass. A separate process replayed all four
selected private archive collections (502 assets each), retaining every
unqualified identity/baseline/runtime flag. No new private network call occurred.

Changed code is project-owned. Upstream sources, credentials, account archives,
running services, SourcePolicy and live trading paths are untouched.


## Files changed

- `apps/ops/portfolio_execution_plan.py`
- `apps/strategies_nautilus/portfolio_risk_policy.py`
- `apps/strategies_nautilus/portfolio_preflight.py`
- `apps/strategies_nautilus/portfolio_simulation.py`
- `apps/strategies_nautilus/portfolio_downtime_risk.py`
- `apps/strategies_nautilus/README.md`
- `tests/ops/test_portfolio_execution_plan.py`
- `tests/strategies_nautilus/test_portfolio_preflight.py`
- `tests/strategies_nautilus/test_portfolio_simulation.py`
- `tests/strategies_nautilus/test_portfolio_downtime_risk.py`
- `tests/strategies_nautilus/test_portfolio_inventory.py`
- `docs/decisions/015-portfolio-risk-policy.md`
- `docs/progress/portfolio-execution-plan-2026-09-11-v3.json`
- `docs/progress/portfolio-risk-unification-2026-09-11.md`
- `docs/agent-reading-list.md`
- `docs/project-status.md`
