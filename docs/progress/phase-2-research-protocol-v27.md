# Phase 2 Research Protocol v27

- **Status**: provider qualification complete; development PnL unopened.
- **Mechanisms**: DefiLlama all-chain daily fees, revenue, and holder revenue expansion.
- **Development**: 2020-01-01 through 2022-12-31; signals and PnL unopened.
- **Confirmation**: sealed.
- **Future blind**: sealed.
- **Trading effect**: none.

## Why this batch is independent

v27 does not retune DefiLlama TVL, DEX volume, or any rejected Cboe, OFR, FRED,
Wikipedia, Fear and Greed, or Coin Metrics identity. It asks whether rising
DeFi protocol cashflow, measured by DefiLlama aggregated daily fees and
revenue, precedes BTC risk-on demand.

The three locked series are all-chain `dailyFees`, `dailyRevenue`, and
`dailyHoldersRevenue`. Each rule buys BTCUSDT Spot only when the latest
completed daily amount minus the value five official observations earlier is
strictly positive; otherwise it is flat. There is no sign flip, lookback grid,
ensemble, chain substitution, or post-result reparameterization.

Fee history is a current reconstruction, not a vintage tape. Decisions wait
two calendar days after the UTC observation date. One current-history GET per
dataType was allowed; rows after 2022-12-31 are counted, not used for
development factors, signals, or PnL.

The frozen chart schema is an object whose `totalDataChart` is a list of
`[unix_seconds, amount]` pairs at UTC midnight. A schema mismatch rejects that
kind without retry.

## Provider qualification

From freeze `fd565b4`, each URL was opened once. All three series qualify on
1,096 unfilled development observations, 61 warmup rows, a one-day maximum
gap, and 1,321 ignored later rows.

## Gates and progression

Unchanged development gates. A development passer may only enter a separately
frozen 2023-2025 confirmation contract. Existing paper-shadow collectors,
SourcePolicy, testnet, live trading, and the future blind stay untouched.
