# ADR-015: Unified portfolio risk policy

- **Status**: Accepted for planning and offline acceptance
- **Date**: 2026-09-11
- **Authority**: The operator delegated risk-policy selection while requesting the
  next project steps. This accepts the decision below, not deployment or trading.
- **Policy ID**: `portfolio-risk-v1-20260911`

## Decision

Keep the provisional initial capital at **500 USDT**. Replace the former 50 USDT
daily planning allowance with this inclusive entry-stop threshold:

```text
daily loss = qualified UTC day-open marked equity - current marked equity
daily limit = min(25 USDT, qualified UTC day-open marked equity × 0.05)
stop when daily loss >= daily limit
```

At day-open equities of 100, 400, 500 and 1,000 USDT, the limits are respectively
5, 20, 25 and 25 USDT. Capital growth does not automatically enlarge the absolute
risk budget. Capital decline tightens it. This is an operator-delegated budget
decision, not an optimization against strategy returns.

Retain the separate **250 USDT peak-equity loss ceiling**, fixed at 50% of the
initial planning capital. It never substitutes for the daily limit. ADR-001's
initial-capital survival requirement for the next capital tier is a separate
qualification criterion; neither rule means a 50% daily loss is acceptable.
The peak-loss ceiling must not grow automatically with peak equity.

For the currently supported dedicated spot BTC/USDT simulation, marked equity is
total USDT plus total BTC valued at the fresh bid, including locked balances.
Observed fees are already reflected in native balances. Pending BUY fees and
adverse limit-to-mark differences also consume prospective daily/peak headroom;
unfilled SELL proceeds do not finance BUY admission. These checks cannot guarantee
a maximum realized loss through price gaps, latency or emergency execution.

Reaching either bound latches the entry block. A rebound, UTC rollover or process
restart cannot clear it. Only fresh, reconciled, owned reductions remain eligible;
unknown account state blocks those too. No automatic reset or emergency order
submission is added. A future runtime needs the separately qualified emergency
and incident-review path before bootstrap.

## Evidence and recovery

Day-open equity must come from an independently qualified account baseline and
UTC history. The provisional 500 USDT is never substituted for observed equity.
All testnet faucet assets must be preserved. Unknown cash flows, resets, missing
valuation coverage or missing day-open evidence block qualification; deposits
are not profit and withdrawals are not silently classified as trading losses.

The synthetic fixture still initializes each day's baseline from its first test
quote. This is a test-only convenience, not a qualified real UTC baseline. Its
persistent stop latch remains set across that initialization. Real-account
mapping, price coverage, downtime history and baseline validation are still
required. The read-only downtime reviewer rejects cross-UTC-day histories and
cannot issue restart permission.

The policy's limits are part of the synthetic strategy configuration fingerprint.
Old checkpoints cannot load into a strategy configured with the new limits. No
existing checkpoint is migrated, rehashed or relabeled as qualified. Read-only
review can apply this policy to historical observations, but explicitly reports
`checkpoint_policy_qualified=false`.

## Versioning and scope

`portfolio-execution-plan-2026-09-11-v3.json` is the current offline plan. V1/V2
contracts and retained research results remain immutable. CLI `--revision 1/2`
and Python `preflight_limits(revision=1/2)` are explicit historical reproduction
paths. Current defaults use v3. The cohort, fixed sleeve sizes, funded-admission
priority and exposure caps remain unchanged. Prior basket PnL is not v3 evidence.

Implementation covers portfolio preflight, synthetic Nautilus risk latching and
the read-only downtime review. It does not alter historical research/backtest
parameters, legacy paper/testnet execution runners, SourcePolicy or schedules.
Legacy baseline day-reset behavior and testnet starting-balance telemetry are
not certified equivalent to this policy; those paths cannot bootstrap this
portfolio. Actual runtime policy reconciliation remains a qualification task.

ADR-001's 5% ceiling, SignalEvent v1 and Nautilus-only execution remain binding.
This ADR does not accept ADR-013, open Phase 6, promote an identity, authorize
orders, create a service or change the 14-day testnet requirement.
