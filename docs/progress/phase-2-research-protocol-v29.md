# Phase 2 Research Protocol v29

- **Status**: pre-registered; Wikimedia macro pageview JSON bodies sealed.
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
