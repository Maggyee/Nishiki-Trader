# Phase 2 Research Protocol v29

- **Status**: provider-qualified; signals and PnL unopened.
- **Mechanisms**: English Wikipedia Federal_Reserve, Inflation, and Recession
  user-pageview relief.
- **Development**: 2020-01-01 through 2022-12-31.
- **Confirmation**: sealed.
- **Future blind**: sealed.
- **Trading effect**: none.

## Why this batch is independent

v29 does not retune v23 crypto-article attention expansion, DefiLlama
TVL/volume/fees/options, or Cboe volatility identities. It asks whether
falling public attention to U.S. macro-stress topics precedes BTC risk-on
demand.

The three locked articles are Federal_Reserve, Inflation, and Recession. Each
rule buys BTCUSDT Spot only when the latest completed daily user pageviews
minus the value five official observations earlier is strictly negative;
otherwise it is flat. There is no sign flip, lookback grid, ensemble, or
post-result reparameterization.

Pageview history is requested only through 2022-12-31 so confirmation
timestamps cannot appear in the body. Decisions wait two calendar days after
the UTC observation date. One GET per article is allowed.

## Gates and progression

Unchanged development gates. A development passer may only enter a separately
frozen 2023-2025 confirmation contract. Existing paper-shadow collectors,
SourcePolicy, testnet, live trading, and the future blind stay untouched.

## Provider qualification

All three articles qualified from freeze `4e15d2d`. Each series has 1,157
unfilled rows, 1,096 development observations from 2020-01-01 through
2022-12-31, 61 warmup rows, and a one-day maximum gap. Machine hashes live in
`docs/progress/phase-2-research-v29-provider-qualification.json`. Signals and
PnL remain unopened. Confirmation timestamps were not requested.
