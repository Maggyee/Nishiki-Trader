# Native received-asset fee acceptance — 2026-09-09

Status: **explicit synthetic accounting mode implemented**. This extends the
[venue-input adapter](portfolio-venue-adapter-2026-09-09.md) by exercising BTC BUY
fees through Nautilus's native fee and position-adjustment interfaces. It does
not enable live trading, change frozen order size, or authorize rounded exits.

## Native precision finding and implementation

NautilusTrader 1.226.0 already adjusts CurrencyPair positions for base-currency
commissions. However, it rounds those adjustments to the instrument's
`size_precision`. The existing test provider's six-place quantity precision
rounded a 0.001 BTC buy minus 0.00000150 BTC commission to **0.000999 BTC**,
while the native account correctly held **0.00099850 BTC**. The existing exact
reconciliation caught this discrepancy and refused to proceed.

The new `received_asset` fixture uses eight-place accounting precision, matching
BTC's native Money precision, while retaining the same numerical order step:
`0.00000100` still means **0.000001 BTC**, not an eight-place trading step.
No upstream code is changed. The fixture rejects insufficient native precision
at startup; it does not compensate for a rounded position with an invented ledger.

`ReceivedAssetFeeModel` uses the Nautilus FeeModel extension point to calculate
synthetic 15 bps BTC BUY and USDT SELL commissions. Native execution still owns
matching, fill events, balances and position adjustments. Native instrument
maker/taker quote-fee fields are zero **in this new fixture only**, so native
reservation code does not misclassify BTC fees as quote fees; the explicit fee
model still charges the actual commissions. The original quote-fee fixture and
all paper/testnet/live runners keep their original settings.

The strategy reconciles native OrderFilled history against cumulative native
order fills, native sleeve positions and settled account BTC. Fees must have the
expected currency, sign and bound. Duplicate native trade evidence, incomplete
fill history, sub-step fills or mismatched net positions halt admission. This
calculation verifies native state only; it never applies a fill, edits a position
or persists a second inventory ledger. Callback replay cannot double-charge fees.

## Explicit opt-in and conservative reservations

`check_batch` and `select_funded_batch` gained `allow_base_buy_fees=False`.
Only the new synthetic strategy mode opts in. BTC fees require an explicit base
commission quantum and native net-inventory reconciliation; BNB and potentially
BNB-paid fees remain unsupported. The response parser retains an explicitly
provided `baseCommissionPrecision` as `base_fee_quantum`; missing precision is
never inferred. The read-only venue CLI remains conservative and does not opt in.

Existing cash reservations retain their full quote fee buffer even though native
BUY settlement now deducts the fee in BTC. This is extra uncommitted headroom,
not a fabricated USDT debit. At 100,000 USDT/BTC, four unchanged 0.001 BTC buys
still reserve **400.60 USDT**. They settle to **100 USDT and 0.00399400 BTC**.
Each filled sleeve owns exactly **0.00099850 BTC**; the fifth sleeve stays flat.
No quantity resizing or new capital assumption is introduced.

Projected entry loss additionally accounts for commission rounding on each
possible minimum-step fill. With step 0.000001 BTC and commission quantum
0.00000001 BTC, a conservative one-satoshi-per-step bound gives at most 1 USDT
for a 0.001 BTC order at the synthetic limit. This covers arbitrary partitioning
into supported grid-aligned fills. The fixture fee hook and native reconciler
reject sub-step fills; that assumption must be requalified for an actual venue.
Daily/peak risk latches still use native settled balances and net BTC positions.

Fee mode is included in the checkpoint fingerprint. Warm strategy replacement
preserves it; changing fee modes or loading a checkpoint with the older fingerprint
fails closed. No checkpoint migration or automatic risk-latch reset is provided.
Cold restart without authoritative native state remains blocked.

## Dust is retained, never silently rounded away

A full 15 bps BUY leaves 0.00099850 BTC, whose remainder against the 0.000001
order step is **0.00000050 BTC per sleeve**. A full flat proposal therefore fails
`quantity_step`. The new read-only inventory diagnostic reports net quantity,
step remainder, whole-step quantity and exact-full-exit blockers. Whole-step
quantity is a diagnostic, **not an executable proposal or a resized order**.
All remaining BTC stays owned by its sleeve and included in account equity.
It is not netted with another sleeve, written off, swept, or used to claim flatness.

When actual partial fills and their rounded commissions leave an already-aligned
net quantity, the existing exact full-exit policy can reduce it. Acceptance uses
two native 0.000333 BTC partial fills, each charged 0.00000050 BTC. After cancel
acknowledgement the native net position is exactly 0.00066500 BTC. An unchanged
flat signal sells that entire quantity, leaving zero BTC and 499.80025 USDT.
This is synthetic accounting evidence, not a strategy return or promotion result.

## Reproduction

```bash
.venv/bin/python -m apps.strategies_nautilus.runners.portfolio_simulation_acceptance --fee-mode received_asset
.venv/bin/python -m apps.strategies_nautilus.runners.portfolio_simulation_acceptance
.venv/bin/pytest -q tests/strategies_nautilus/test_portfolio_inventory.py tests/strategies_nautilus/test_portfolio_venue.py tests/strategies_nautilus/test_portfolio_preflight.py tests/strategies_nautilus/test_portfolio_simulation.py
.venv/bin/pytest -q -m 'not network and not postgres'
```

The received-asset CLI uses only synthetic signals/quotes, a temporary checkpoint
and the native backtest engine. Its result is `passed` only when native net
inventory and the expected no-rounding full-exit refusal match. It also reports
`runtime_ready=false` and `performance_evidence=false`. Independent runs return
the same report. No credentials, private account API, live adapter or research
prices are read.

Verification: **19 new native inventory tests**, **55 venue-adapter tests** and
**1,907 full offline tests** passed. Twelve Postgres integration tests were
deselected because no dedicated DSN was supplied. Received-asset CLI smoke,
Ruff lint/changed-file formatting and the research registry check passed.
No upstream source or live trading path was modified.

## Remaining work

- Resolve the residual-inventory exit policy explicitly before promotion. The
  current no-resizing contract intentionally refuses off-grid full exits. Any
  policy to sell a whole-step portion must preserve the residual sleeve holding,
  risk exposure, audit and restart state, and must not silently redefine flat.
- Implement an authoritative collector and native account reconciliation for
  complete balances/orders, permissions, dynamic rules and effective references.
  Real Binance commission precision/payment mode and fill-grid guarantees remain
  unverified. BNB accounting is still unsupported.
- Complete durable native process recovery and uncertain-submit reconciliation.
  Reconcile the offline 50 USDT daily budget with the binding runtime 5% ADR before
  deployment. Existing SourcePolicy, schedules and sealed future PnL stay unchanged.
