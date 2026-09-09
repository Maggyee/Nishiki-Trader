# Explicit offline residual exit policy — 2026-09-09

Status: **synthetic Nautilus acceptance implemented**. The operator asked to
continue the residual-inventory engineering step after native base-fee accounting.
This policy is an explicit simulation opt-in; it is not an allocation, SourcePolicy
change, promotion or deployment. Historical v1/v2 contracts and acceptance records
remain immutable.

## Exit policy

`PortfolioSimulationStrategy` now accepts `exit_policy`:

| Policy | Valid flat signal with owned BTC |
| --- | --- |
| `exact_v1` (default) | Propose the entire net holding; off-grid exits still fail preflight. |
| `whole_steps_v1` (explicit opt-in) | Propose `net - net % quantity_step`, retaining the remainder in the same sleeve. |

Only the consumer sizes the reduction. SignalEvent v1 remains unchanged and still
contains no execution quantity. BUY remains fixed at 0.001 BTC. The selector does
not resize proposals: the explicitly sized reduction must pass the existing whole
batch preflight, then native Nautilus risk and execution. This changes exit behavior
only in the new opt-in simulation policy, not the frozen v2 admission algorithm.

- No increase to reach minimum quantity/notional; no cap to maximum quantity or
  notional; no order splitting. A positive whole-step proposal outside a limit
  is skipped, leaving the **entire** current native holding untouched.
- If net inventory is positive but less than one step, no order is constructed.
  The consumed signal records `residual_below_step`, never `already_flat`.
  Exactly zero inventory still records `already_flat`.
- Fresh rules, native account reconciliation, all effective filters, owned/free
  base, same-sleeve pending-order exclusion, portfolio caps and loss latches remain
  required. Pending cancellation retains reservations until native acknowledgement;
  late fills update inventory through Nautilus. Unfilled sales create no BUY credit.
- There is no automatic sweep, retry, cross-sleeve transfer, netting, write-off or
  new BUY top-up. A fresh signal after cancellation must revalidate against current
  native state. Residual inventory still consumes the sleeve's 0.001 BTC exposure
  cap, so even a 0.00000050 BTC remainder blocks another fixed 0.001 BTC BUY.
  Re-entry while such residuals remain is deliberately unresolved for deployment.

`portfolio_inventory.size_exit` is a pure sizing helper, not an execution engine
or ledger. Existing inventory diagnostics remain read-only and never authorize an
order by themselves. Native positions, account balances and complete fill/fee
evidence remain the only source for actual inventory and equity.

## Audit and recovery

Every eligible flat signal records `exit_sizing`: policy, requested native net
quantity, proposed quantity, `retained_if_filled`, and `prepared_quantity`. These
are durable with the signal and order intent before the first native submission.
Prepared quantity is zero for skipped proposals; prepared is not a claim that
the venue accepted or filled an order. The linked native order/event journal
supplies actual execution status. `retained_if_filled` is explicitly hypothetical:
after denial, cancellation or partial execution, use native holdings, not that
projection, for the actual retained amount.

Exit policy joins fee mode in the checkpoint fingerprint. Warm strategy restart
preserves policy, consumed signals, order reservations, risk latch and exact native
residual attribution. Changing policy or loading an older fingerprint is rejected;
there is no migration or latch reset. Full process restart without native cached
orders/account/positions still fails closed; it never rebuilds a ledger from the
sizing audit or resubmits uncertain orders.

## Synthetic evidence

At 100,000 USDT/BTC with native 15 bps received-asset fees:

- Four unchanged 0.001 BTC buys settle to 100 USDT and 0.00399400 BTC.
- Each sleeve sells 0.00099800 BTC and retains **0.00000050 BTC** in its original
  native position. After four sells, the account holds **498.60120 USDT and
  0.00000200 BTC**; the report correctly says `flat=false` after warm restart.
- A single-sleeve run ends at 499.65030 USDT plus 0.00000050 BTC, with marked
  equity 499.70030 USDT. Other sleeves remain zero; nothing is transferred.
- A SELL partially fills twice by 0.000333 BTC, including a late fill while cancel
  is pending. The remaining 0.000332 BTC order stays reserved until acknowledgement.
  A new flat signal after restart sells those remaining whole steps, retaining
  exactly 0.00000050 BTC.
- A 0.0001 BTC partial BUY, then cancellation, leaves 0.00009985 BTC. The proposed
  0.000099 BTC exit is below 10 USDT minimum notional, so the entire holding remains
  after restart; it is never rounded up or swept.
- Quote-fee mode also passes the explicit policy: already-aligned holdings sell
  exactly, ending at 498.80 USDT and zero BTC. The two original default smoke
  scenarios retain their original accounting and off-grid refusal behavior.

These are native accounting/lifecycle fixtures, not research performance evidence.
No historical prices, sealed future PnL, credentials or actual accounts were used.

## Reproduction and remaining work

```bash
.venv/bin/python -m apps.strategies_nautilus.runners.portfolio_simulation_acceptance --fee-mode received_asset --exit-policy whole_steps_v1
.venv/bin/python -m apps.strategies_nautilus.runners.portfolio_simulation_acceptance --exit-policy whole_steps_v1
.venv/bin/pytest -q tests/strategies_nautilus/test_portfolio_residual_exit.py
.venv/bin/pytest -q -m 'not network and not postgres'
```

The CLI uses only synthetic inputs and a temporary checkpoint, reporting
`runtime_ready=false` and `performance_evidence=false`. Both fee modes produce
repeatable reports. Focused verification: **22 new tests passed**, covering native
reductions, limits, small inventory, durable audit, partial/late fills, pending
reservations, signal replay, retained exposure, loss latches and restart boundaries.
Full offline verification: **1,929 tests passed**, with 12 Postgres integration
tests deselected because no dedicated DSN was supplied. Original default CLI
smokes, Ruff lint/format checks, the research family registry and `git diff --check`
also passed.

Next implement authoritative account/venue input reconciliation and complete native
process recovery. Real commission payment/precision and fill-grid guarantees,
permissions and effective price references remain unverified; BNB remains unsupported.
Reconcile the 50 USDT offline daily loss budget with the binding runtime 5% ADR
before deployment. Portfolio review and residual re-entry policy remain required
before promotion. No upstream source, collector schedule or live path changed.
